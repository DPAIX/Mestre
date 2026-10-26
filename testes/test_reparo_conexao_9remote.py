"""Reparo com processos, portas e janelas simulados; nenhum produto é aberto."""
from copy import deepcopy
from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import reparar_conexao_9remote as reparo


class ErroProcesso(Exception):
    pass


class ProcessoAusente(ErroProcesso):
    pass


class AcessoNegado(ErroProcesso):
    pass


class ReparoProcessos(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.raiz = Path(tmp.name).resolve()
        self.node = self.raiz / 'runtime' / 'node.exe'
        self.node.parent.mkdir()
        self.node.write_bytes(b'fixture, not executable')
        self.pacote = self.raiz / 'gerenciado' / '9remote'
        (self.pacote / 'dist').mkdir(parents=True)
        self.estados = {}
        self.eventos = []
        self.handles = {}
        self.adicionar(31001, 'cli')
        self.adicionar(31002, 'servidor')
        self.psutil = SimpleNamespace(Error=ErroProcesso, NoSuchProcess=ProcessoAusente,
            AccessDenied=AcessoNegado, CONN_LISTEN='LISTEN',
            process_iter=Mock(side_effect=self.listar), Process=Mock(side_effect=self.processo),
            net_connections=Mock(side_effect=self.conexoes))
        for nome, valor in (('_WINDOWS', True), ('_psutil', Mock(return_value=self.psutil)),
                ('_ProcessoWindows', Mock(side_effect=self.abrir)), ('_conferir_porta_livre', Mock())):
            p = patch.object(reparo, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def adicionar(self, pid, tipo='outro', *, exe=None, argv=None, sid='S-1-5-21-100'):
        if argv is None:
            argv = ([str(self.node), str(self.pacote / 'dist' / 'cli.cjs'), 'ui', '--start']
                if tipo == 'cli' else [str(self.node), str(self.pacote / 'dist' / 'server.cjs')]
                if tipo == 'servidor' else [str(self.node), str(self.raiz / 'outro.cjs')])
        self.estados[pid] = {'pid': pid, 'name': 'node.exe', 'exe': str(exe or self.node),
            'argv': argv, 'criado': 1800000000.125, 'filetime': '133000000000000000', 'sid': sid}

    def processo(self, pid):
        if pid not in self.estados:
            raise ProcessoAusente()
        e = self.estados[pid]
        return SimpleNamespace(pid=pid, name=lambda: e['name'], exe=lambda: e['exe'],
            cmdline=lambda: list(e['argv']), create_time=lambda: e['criado'])

    def listar(self):
        return [self.processo(pid) for pid in list(self.estados)]

    def conexoes(self, **kw):
        self.assertEqual(kw, {'kind': 'tcp'})
        return [SimpleNamespace(laddr=('127.0.0.1', 2208), status='LISTEN', pid=31002)] if 31002 in self.estados else []

    def abrir(self, pid):
        e = self.estados[pid]
        identidade = {'pid': pid, 'exe': e['exe'], 'criado': e['filetime'],
            'owner_sid': e['sid'], 'atual_sid': 'S-1-5-21-100'}
        h = Mock()
        h.identidade.return_value = identidade
        h.aguardar.side_effect = lambda segundos: pid not in self.estados
        def parar():
            self.eventos.append(pid)
            self.estados.pop(pid, None)
        h.parar.side_effect = parar
        self.handles[pid] = h
        return h

    def parar(self, **kw):
        return reparo.parar_host(self.node, self.pacote, **kw)

    def test_controladores_param_antes_do_servidor_e_handles_sao_fechados(self):
        self.adicionar(31003, 'cli', argv=[str(self.node), str(self.pacote / 'dist' / 'cli.cjs'), 'start'])
        self.assertEqual(self.parar(), 3)
        self.assertEqual(self.eventos[-1], 31002)
        self.assertEqual(set(self.eventos[:2]), {31001, 31003})
        for h in self.handles.values():
            h.parar.assert_called_once_with()
            h.close.assert_called_once_with()
        reparo._conferir_porta_livre.assert_called_once_with(self.psutil)

    def test_outro_node_mesmo_executavel_e_outra_instalacao_sao_preservados(self):
        self.adicionar(31003)
        self.adicionar(31004, 'cli', exe=self.raiz / 'outro_node.exe')
        self.assertEqual(self.parar(), 2)
        self.assertEqual(set(self.estados), {31003, 31004})
        self.assertEqual(set(self.handles), {31001, 31002})

    def test_outro_executavel_node_nao_tem_argumentos_privados_lidos(self):
        outro = SimpleNamespace(pid=31003, name=lambda: 'node.exe',
            exe=lambda: str(self.raiz / 'outro_node.exe'),
            cmdline=Mock(side_effect=AcessoNegado('privado')))
        self.psutil.process_iter.side_effect = lambda: [*self.listar(), outro]
        self.assertEqual(self.parar(), 2)
        outro.cmdline.assert_not_called()

    def test_dono_estranho_da_porta_impede_toda_parada(self):
        self.psutil.net_connections.side_effect = lambda **kw: [SimpleNamespace(laddr=('::1', 2208), status='LISTEN', pid=9999)]
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])
        for h in self.handles.values():
            h.close.assert_called_once()
        reparo._conferir_porta_livre.assert_not_called()

    def test_dono_ausente_da_porta_nao_e_interpretado_como_porta_livre(self):
        self.psutil.net_connections.side_effect = lambda **kw: [SimpleNamespace(laddr=('127.0.0.1', 2208), status='LISTEN', pid=None)]
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])

    def test_outro_usuario_fecha_handle_sem_encerrar_nenhum_processo(self):
        self.estados[31002]['sid'] = 'S-1-5-21-200'
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])
        for h in self.handles.values():
            h.close.assert_called_once()

    def test_pid_reutilizado_entre_snapshot_e_handle_e_recusado(self):
        original = self.psutil.Process.side_effect
        def reutilizado(pid):
            self.estados[pid]['criado'] += 1
            return original(pid)
        self.psutil.Process.side_effect = reutilizado
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])
        self.handles[31001].close.assert_called_once()

    def test_um_tick_alterado_no_handle_impede_toda_parada(self):
        original = reparo._ProcessoWindows.side_effect
        def abrir(pid):
            h = original(pid)
            identidade = deepcopy(h.identidade.return_value)
            h.identidade.side_effect = [identidade, {**identidade, 'criado': '133000000000000001'}]
            return h
        reparo._ProcessoWindows.side_effect = abrir
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])
        for h in self.handles.values():
            h.close.assert_called_once()

    def test_argumentos_mutados_sao_revalidados_antes_de_qualquer_parada(self):
        original = reparo._listar_metadados
        chamadas = []
        def listar(*args):
            chamadas.append(1)
            if len(chamadas) == 2:
                self.estados[31001]['argv'] = [str(self.node), str(self.raiz / 'outro.cjs')]
            return original(*args)
        with patch.object(reparo, '_listar_metadados', side_effect=listar):
            with self.assertRaises(reparo.FalhaReparo):
                self.parar()
        self.assertEqual(self.eventos, [])

    def test_iniciador_novo_entre_captura_e_parada_e_preservado(self):
        original = reparo._listar_metadados
        chamadas = []
        def listar(*args):
            chamadas.append(1)
            if len(chamadas) == 2:
                self.adicionar(31003, 'cli')
            return original(*args)
        with patch.object(reparo, '_listar_metadados', side_effect=listar):
            with self.assertRaises(reparo.FalhaReparo):
                self.parar()
        self.assertEqual(self.eventos, [])
        self.assertIn(31003, self.estados)

    def test_timeout_de_parada_nao_repete_terminate_nem_confirma_porta(self):
        original = reparo._ProcessoWindows.side_effect
        def abrir(pid):
            h = original(pid)
            h.aguardar.side_effect = lambda segundos: False
            return h
        reparo._ProcessoWindows.side_effect = abrir
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [31001])
        self.handles[31002].parar.assert_not_called()
        for h in self.handles.values():
            h.close.assert_called_once()
        reparo._conferir_porta_livre.assert_not_called()

    def test_tempo_esgotado_antes_da_parada_nao_encerra(self):
        with patch.object(reparo.time, 'monotonic', side_effect=[1, 20]):
            with self.assertRaises(reparo.FalhaReparo):
                self.parar(timeout=12)
        self.assertEqual(self.eventos, [])

    def test_erro_na_identificacao_nao_expoe_detalhe_privado(self):
        reparo._ProcessoWindows.side_effect = OSError('fixture-chave-privada')
        with self.assertRaises(reparo.FalhaReparo) as erro:
            self.parar()
        self.assertNotIn('fixture-chave', str(erro.exception))
        self.assertEqual(self.eventos, [])

    def test_sem_processos_ainda_exige_prova_da_porta_livre(self):
        self.estados.clear()
        self.assertEqual(self.parar(), 0)
        reparo._ProcessoWindows.assert_not_called()
        reparo._conferir_porta_livre.assert_called_once_with(self.psutil)

    def test_argv_managed_com_flags_extras_ou_caminhos_relativos_nao_encerra(self):
        self.estados[31001]['argv'].append('--extra')
        with self.assertRaises(reparo.FalhaReparo):
            self.parar()
        self.assertEqual(self.eventos, [])
        reparo._ProcessoWindows.assert_not_called()
        self.assertIsNone(reparo._tipo_argumentos(['node.exe', 'dist/cli.cjs', 'ui'], self.node, self.pacote))

    def test_fora_windows_nunca_enumera_processos(self):
        with patch.object(reparo, '_WINDOWS', False), self.assertRaises(reparo.FalhaReparo):
            self.parar()
        reparo._psutil.assert_not_called()

    def test_prazos_invalidos_nao_enumera_processos(self):
        for valor in (True, 0, 31, float('nan'), float('inf'), '12'):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                self.parar(timeout=valor)
        reparo._psutil.assert_not_called()


class FluxoReparo(unittest.TestCase):
    def setUp(self):
        self.pacote = Path(__file__).resolve().parent / 'pacote_fixture'
        self.node = Path(__file__).resolve().parent / 'node.exe'
        self.eventos = []
        self.plano = {'estado': 'original', 'versao': '3.0.43'}
        self.aplicado = {'estado': 'aplicada', 'versao': '3.0.43'}
        self.env = {'PATH': 'fixture'}
        lock = patch.object(reparo.correcao, 'manutencao', side_effect=nullcontext, create=True)
        self.lock = lock.start()
        self.addCleanup(lock.stop)
        for nome, valor in (('_WINDOWS', True), ('_pacote', Mock(return_value=self.pacote)),
                ('_ambiente', Mock(return_value=self.env)), ('_node', Mock(return_value=self.node)),
                ('parar_host', Mock(side_effect=lambda *a: self.marcar('parar', 2))),
                ('_iniciar_host', Mock(side_effect=lambda *a: self.marcar('iniciar', None)))):
            p = patch.object(reparo, nome, valor)
            p.start()
            self.addCleanup(p.stop)
        for nome, valor in (('planejar_correcao', Mock(side_effect=lambda *a: self.marcar('planejar', self.plano))),
                ('aplicar_correcao', Mock(side_effect=lambda *a: self.marcar('aplicar', self.aplicado))),
                ('reverter_correcao', Mock(side_effect=lambda *a: self.marcar('reverter', self.plano)))):
            p = patch.object(reparo.correcao, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def marcar(self, evento, retorno):
        self.eventos.append(evento)
        return retorno

    def test_plano_nao_executa_node_parada_patch_ou_janela(self):
        self.assertFalse(reparo.reparar_conexao()['iniciado'])
        self.assertEqual(self.eventos, ['planejar'])
        reparo._node.assert_not_called()

    def test_hashes_conferidos_antes_de_parar_e_patch_antes_de_iniciar(self):
        r = reparo.reparar_conexao(aplicar=True, iniciar=True)
        self.assertEqual(self.eventos, ['planejar', 'parar', 'aplicar', 'iniciar'])
        self.assertEqual(r['processos_encerrados'], 2)
        self.assertEqual(r['painel'], reparo.PAINEL)
        self.lock.assert_called_once_with()

    def test_reversao_nao_executa_bundle_antigo(self):
        self.assertFalse(reparo.reparar_conexao(reverter=True)['iniciado'])
        self.assertEqual(self.eventos, ['planejar', 'parar', 'reverter'])
        reparo._iniciar_host.assert_not_called()

    def test_hash_desconhecido_nunca_para_processos(self):
        reparo.correcao.planejar_correcao.side_effect = RuntimeError('fixture')
        with self.assertRaises(RuntimeError):
            reparo.reparar_conexao(aplicar=True, iniciar=True)
        reparo.parar_host.assert_not_called()
        reparo.correcao.aplicar_correcao.assert_not_called()

    def test_falha_de_parada_nao_troca_arquivos_nem_abre_janela(self):
        reparo.parar_host.side_effect = reparo.FalhaReparo('fixture')
        with self.assertRaises(reparo.FalhaReparo):
            reparo.reparar_conexao(aplicar=True, iniciar=True)
        reparo.correcao.aplicar_correcao.assert_not_called()
        reparo._iniciar_host.assert_not_called()

    def test_falha_do_patch_nao_inicia_original(self):
        reparo.correcao.aplicar_correcao.side_effect = RuntimeError('fixture')
        with self.assertRaises(RuntimeError):
            reparo.reparar_conexao(aplicar=True, iniciar=True)
        reparo._iniciar_host.assert_not_called()

    def test_flags_ambiguas_nao_leem_pacote(self):
        for kw in ({'iniciar': True}, {'aplicar': True, 'reverter': True}, {'reverter': True, 'iniciar': True}, {'aplicar': 1}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                reparo.reparar_conexao(**kw)
        reparo._pacote.assert_not_called()


class ExecucaoIsolada(unittest.TestCase):
    def test_ambiente_remove_segredos_overrides_node_e_proxy(self):
        fixture = {'PATH': 'runtime', 'LOCALAPPDATA': 'fixture', 'GEMINI_API_KEY': 'private',
            'NODE_OPTIONS': '--require private', 'HTTPS_PROXY': 'private', 'NREMOTE_HOME': 'private'}
        with patch.dict(os.environ, fixture, clear=True):
            self.assertEqual(reparo._ambiente(), {'PATH': 'runtime', 'LOCALAPPDATA': 'fixture'})

    def test_node_valida_executavel_e_versao_com_ambiente_filtrado(self):
        with tempfile.TemporaryDirectory() as d:
            node = Path(d).resolve() / 'node.exe'
            node.write_bytes(b'fixture')
            r = SimpleNamespace(returncode=0, stdout='v22.20.0\n')
            with patch.object(reparo.shutil, 'which', return_value=str(node)), patch.object(reparo.subprocess, 'run', return_value=r) as executar:
                self.assertEqual(reparo._node({'PATH': d}), node)
                self.assertEqual(executar.call_args.args[0], [str(node), '--version'])
                self.assertEqual(executar.call_args.kwargs['env'], {'PATH': d})
                self.assertFalse(executar.call_args.kwargs['shell'])
                r.stdout = 'v20.1.0'
                with self.assertRaises(reparo.FalhaReparo):
                    reparo._node({'PATH': d})

    def test_janela_apenas_ui_start_e_browser_apos_saude_e_identidade(self):
        node = Path(__file__).resolve().parent / 'node.exe'
        pacote = Path(__file__).resolve().parent / 'fixture'
        processo = Mock(pid=31001)
        processo.poll.return_value = None
        with patch.object(reparo.subprocess, 'Popen', return_value=processo) as abrir, patch.object(reparo, '_saude_local', return_value=True), patch.object(reparo, '_host_lancado_identificado', return_value=True), patch.object(reparo.webbrowser, 'open') as browser:
            reparo._iniciar_host(node, pacote, {'PATH': 'fixture'})
        self.assertEqual(abrir.call_args.args[0], [str(node), str(pacote / 'dist' / 'cli.cjs'), 'ui', '--start'])
        self.assertTrue(abrir.call_args.kwargs['close_fds'])
        self.assertFalse(abrir.call_args.kwargs['shell'])
        self.assertEqual(abrir.call_args.kwargs['cwd'], str(pacote.parents[1]))
        browser.assert_called_once_with(reparo.PAINEL, new=2)

    def test_saude_sem_identidade_nao_abre_browser(self):
        processo = Mock(pid=31001)
        processo.poll.return_value = None
        with patch.object(reparo.subprocess, 'Popen', return_value=processo), patch.object(reparo, '_saude_local', return_value=True), patch.object(reparo, '_host_lancado_identificado', return_value=False), patch.object(reparo.webbrowser, 'open') as browser:
            with self.assertRaises(reparo.FalhaReparo):
                reparo._iniciar_host(Path('/fixture/node.exe'), Path('/fixture/pacote'), {})
        browser.assert_not_called()

    def test_timeout_de_inicio_nao_presume_host_funcionando(self):
        processo = Mock(pid=31001)
        processo.poll.return_value = None
        with patch.object(reparo.subprocess, 'Popen', return_value=processo), patch.object(reparo, '_saude_local', return_value=False), patch.object(reparo.time, 'monotonic', side_effect=[1, 2, 30]), patch.object(reparo.time, 'sleep'), patch.object(reparo.webbrowser, 'open') as browser:
            with self.assertRaises(reparo.FalhaReparo):
                reparo._iniciar_host(Path('/fixture/node.exe'), Path('/fixture/pacote'), {})
        browser.assert_not_called()

    def test_saude_le_somente_rota_local_sem_proxy(self):
        resposta = Mock(status=200)
        resposta.__enter__ = Mock(return_value=resposta)
        resposta.__exit__ = Mock(return_value=False)
        opener = Mock()
        opener.open.return_value = resposta
        with patch.object(reparo.urllib.request, 'ProxyHandler') as proxy, patch.object(reparo.urllib.request, 'build_opener', return_value=opener):
            self.assertTrue(reparo._saude_local())
        proxy.assert_called_once_with({})
        opener.open.assert_called_once_with('http://127.0.0.1:2208/api/health', timeout=1)
        resposta.read.assert_not_called()


class ProvaPorta(unittest.TestCase):
    def test_bind_exclusivo_em_ambos_loopbacks_e_sockets_fechados(self):
        ipv4, ipv6 = Mock(), Mock()
        with patch.object(reparo, '_donos_porta', return_value=set()), patch.object(reparo.socket, 'socket', side_effect=[ipv4, ipv6]), patch.object(reparo.socket, 'SO_EXCLUSIVEADDRUSE', 999, create=True):
            reparo._conferir_porta_livre(Mock())
        ipv4.setsockopt.assert_called_once_with(reparo.socket.SOL_SOCKET, 999, 1)
        ipv6.setsockopt.assert_any_call(reparo.socket.SOL_SOCKET, 999, 1)
        ipv6.setsockopt.assert_any_call(reparo.socket.IPPROTO_IPV6, reparo.socket.IPV6_V6ONLY, 1)
        ipv4.bind.assert_called_once_with(('127.0.0.1', 2208))
        ipv6.bind.assert_called_once_with(('::1', 2208))
        ipv4.close.assert_called_once()
        ipv6.close.assert_called_once()

    def test_bind_inconclusivo_fecha_todos_sem_declarar_porta_livre(self):
        ipv4, ipv6 = Mock(), Mock()
        ipv6.bind.side_effect = OSError('fixture-private')
        with patch.object(reparo, '_donos_porta', return_value=set()), patch.object(reparo.socket, 'socket', side_effect=[ipv4, ipv6]), patch.object(reparo.socket, 'SO_EXCLUSIVEADDRUSE', 999, create=True):
            with self.assertRaises(reparo.FalhaReparo) as erro:
                reparo._conferir_porta_livre(Mock())
        self.assertNotIn('fixture-private', str(erro.exception))
        ipv4.close.assert_called_once()
        ipv6.close.assert_called_once()

    def test_listener_detectado_impede_ate_o_bind(self):
        with patch.object(reparo, '_donos_porta', return_value={9999}), patch.object(reparo.socket, 'socket') as abrir:
            with self.assertRaises(reparo.FalhaReparo):
                reparo._conferir_porta_livre(Mock())
        abrir.assert_not_called()


if __name__ == '__main__':
    unittest.main()
