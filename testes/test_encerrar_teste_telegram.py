"""Identidade e interrupção da sonda com processos inteiramente simulados."""
from copy import deepcopy
from contextlib import redirect_stdout
import hashlib
import io
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import encerrar_teste_telegram as app


def comando(programa=None):
    return 'exec(' + repr(app._SONDA if programa is None else programa) + ')'


class CorrespondenciaSonda(unittest.TestCase):
    def test_programa_conhecido_e_somente_espacos_sao_aceitos(self):
        self.assertTrue(app._codigo_corresponde(comando()))
        self.assertTrue(app._codigo_corresponde('\n' + comando() + '  \n'))

    def test_caminho_windows_com_barras_e_caixa_equivalentes_e_aceito(self):
        fonte = app._SONDA.replace("Path('F:/MeuControlePC_v2/.env')", "Path(r'f:\\MEUCONTROLEPC_V2\\.env')")
        self.assertTrue(app._codigo_corresponde(comando(fonte)))

    def test_outro_caminho_de_configuracao_nao_e_aceito(self):
        self.assertFalse(app._codigo_corresponde(comando(app._SONDA.replace('F:/MeuControlePC_v2/.env', 'C:/outro/.env'))))

    def test_codigo_extra_antes_depois_ou_dentro_nao_e_aceito(self):
        for valor in (comando() + ';print(123)', 'print(123);' + comando(),
                      comando(app._SONDA + '\nprint(123)'), 'exec(' + repr(app._SONDA) + ', {})',
                      app._SONDA, '__import__(\'os\').remove(\'fixture\')'):
            with self.subTest(valor=valor[:30]):
                self.assertFalse(app._codigo_corresponde(valor))

    def test_entrada_invalida_grande_ou_nao_string_e_recusada(self):
        for valor in (None, [], '', 'x' * 8193, 'exec(', 'exec(123)', 'eval(' + repr(app._SONDA) + ')'):
            self.assertFalse(app._codigo_corresponde(valor))

    def test_formato_exato_publicado_tem_hash_conhecido(self):
        escapado = app._SONDA.replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n')
        codigo = "exec('" + escapado + "')"
        self.assertEqual(hashlib.sha256(codigo.encode()).hexdigest(), app._HASH_ORIGINAL)
        self.assertEqual(len(codigo), 1446)


class ErroProcesso(Exception):
    pass


class ProcessoAusente(ErroProcesso):
    pass


class AcessoNegado(ErroProcesso):
    pass


class EncerramentoTeste(unittest.TestCase):
    def setUp(self):
        temporario = tempfile.TemporaryDirectory()
        self.addCleanup(temporario.cleanup)
        self.raiz = Path(temporario.name).resolve()
        self.python = self.raiz / '.venv' / 'Scripts' / 'python.exe'
        self.python.parent.mkdir(parents=True)
        self.python.write_bytes(b'fixture, not executable')
        self.estados = {}
        self.handles = {}
        self.eventos = []
        self.adicionar(32001)
        self.psutil = SimpleNamespace(Error=ErroProcesso, NoSuchProcess=ProcessoAusente,
            AccessDenied=AcessoNegado, process_iter=Mock(side_effect=self.listar),
            Process=Mock(side_effect=self.processo))
        for nome, valor in (('_WINDOWS', True), ('_python_atual', Mock(return_value=self.python)),
                ('_psutil', Mock(return_value=self.psutil)), ('_ProcessoWindows', Mock(side_effect=self.abrir))):
            p = patch.object(app, nome, valor)
            p.start()
            self.addCleanup(p.stop)

    def adicionar(self, pid, *, codigo=None, exe=None, argv=None, sid='S-1-5-21-100'):
        self.estados[pid] = {'pid': pid, 'exe': str(exe or self.python), 'name': 'python.exe',
            'argv': list(argv or [str(self.python), '-c', comando(codigo)]),
            'criado': 1800000000.125, 'filetime': '134444736001250000', 'sid': sid, 'cwd': str(self.raiz)}

    def processo(self, pid):
        if pid not in self.estados:
            raise ProcessoAusente()
        estado = self.estados[pid]
        return SimpleNamespace(pid=pid, name=lambda: estado['name'], exe=lambda: estado['exe'],
            cmdline=lambda: list(estado['argv']), create_time=lambda: estado['criado'], cwd=lambda: estado['cwd'])

    def listar(self):
        return [self.processo(pid) for pid in self.estados]

    def abrir(self, pid):
        estado = self.estados[pid]
        self.eventos.append(('abrir', pid))
        h = Mock()
        h.identidade.return_value = {'pid': pid, 'exe': estado['exe'], 'criado': estado['filetime'],
            'owner_sid': estado['sid'], 'atual_sid': 'S-1-5-21-100'}
        h.aguardar.side_effect = lambda segundos: pid not in self.estados
        def parar():
            self.eventos.append(('parar', pid))
            self.estados.pop(pid)
        h.parar.side_effect = parar
        self.handles[pid] = h
        return h

    def encerrar(self, **kwargs):
        return app.encerrar_teste(confirmado=True, **kwargs)

    def test_encerra_apenas_sonda_conhecida_e_fecha_handle(self):
        resultado = self.encerrar()
        self.assertEqual(resultado, {'estado': 'encerrado', 'sondas_encerradas': 1})
        self.handles[32001].parar.assert_called_once_with()
        self.handles[32001].close.assert_called_once_with()

    def test_bot_e_outros_programas_python_do_mesmo_exe_sao_preservados(self):
        self.adicionar(32002, argv=[str(self.python), str(self.raiz / 'assistente_pc.py')])
        self.adicionar(32003, codigo="print('fixture')")
        self.adicionar(32004, exe=self.raiz / 'outro-python.exe')
        self.assertEqual(self.encerrar()['sondas_encerradas'], 1)
        self.assertEqual(set(self.estados), {32002, 32003, 32004})
        self.assertEqual(set(self.handles), {32001})

    def test_nenhuma_sonda_e_noop_sem_handles(self):
        self.estados.clear()
        self.assertEqual(self.encerrar(), {'estado': 'nenhuma_sonda_identificada', 'sondas_encerradas': 0})
        app._ProcessoWindows.assert_not_called()

    def test_argv_relativo_publicado_com_cwd_correto_e_aceito(self):
        self.estados[32001]['argv'][0] = r'.\.venv\Scripts\python.exe'
        self.assertEqual(self.encerrar()['sondas_encerradas'], 1)

    def test_argv_relativo_publicado_com_cwd_errado_e_preservado(self):
        self.estados[32001]['argv'][0] = r'.\.venv\Scripts\python.exe'
        self.estados[32001]['cwd'] = str(self.raiz / 'outra')
        self.assertEqual(self.encerrar()['sondas_encerradas'], 0)
        app._ProcessoWindows.assert_not_called()

    def test_argv_relativo_nao_publicado_e_preservado(self):
        self.estados[32001]['argv'][0] = 'python.exe'
        self.assertEqual(self.encerrar()['sondas_encerradas'], 0)
        app._ProcessoWindows.assert_not_called()

    def test_cwd_mudou_depois_do_handle_aborta(self):
        self.estados[32001]['argv'][0] = r'.\.venv\Scripts\python.exe'
        original = self.psutil.Process.side_effect
        def mudou(pid):
            self.estados[pid]['cwd'] = str(self.raiz / 'outra')
            return original(pid)
        self.psutil.Process.side_effect = mudou
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_not_called()

    def test_todos_handles_sao_abertos_antes_da_primeira_parada(self):
        self.adicionar(32002)
        self.assertEqual(self.encerrar()['sondas_encerradas'], 2)
        self.assertEqual(self.eventos[:2], [('abrir', 32001), ('abrir', 32002)])

    def test_outro_proprietario_aborta_antes_de_toda_parada(self):
        self.adicionar(32002, sid='S-1-5-21-200')
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.assertFalse(any(x[0] == 'parar' for x in self.eventos))
        for h in self.handles.values():
            h.close.assert_called_once()

    def test_pid_reutilizado_entre_snapshot_e_captura_aborta(self):
        original = self.psutil.Process.side_effect
        def mudou(pid):
            self.estados[pid]['criado'] += 1
            return original(pid)
        self.psutil.Process.side_effect = mudou
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_not_called()
        self.handles[32001].close.assert_called_once()

    def test_filetime_diferente_do_snapshot_aborta(self):
        self.estados[32001]['filetime'] = '134444736011250000'
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_not_called()

    def test_tick_nativo_mutado_na_revalidacao_aborta(self):
        abrir = app._ProcessoWindows.side_effect
        def mudou(pid):
            h = abrir(pid)
            identidade = deepcopy(h.identidade.return_value)
            h.identidade.side_effect = [identidade, {**identidade, 'criado': '134444736001250001'}]
            return h
        app._ProcessoWindows.side_effect = mudou
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_not_called()

    def test_argv_mudado_apos_captura_aborta(self):
        original = self.psutil.Process.side_effect
        def mudou(pid):
            self.estados[pid]['argv'] = [str(self.python), '-c', "print('outro')"]
            return original(pid)
        self.psutil.Process.side_effect = mudou
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_not_called()

    def test_lista_nova_antes_da_parada_nao_encerra_ninguem(self):
        listar = app._listar
        chamadas = []
        def mudou(*args):
            chamadas.append(1)
            if len(chamadas) == 2:
                self.adicionar(32002)
            return listar(*args)
        with patch.object(app, '_listar', side_effect=mudou):
            with self.assertRaises(app.FalhaEncerrarTeste):
                self.encerrar()
        self.handles[32001].parar.assert_not_called()

    def test_timeout_nao_repete_terminate(self):
        abrir = app._ProcessoWindows.side_effect
        def aguardar(pid):
            h = abrir(pid)
            h.aguardar.side_effect = lambda segundos: False
            return h
        app._ProcessoWindows.side_effect = aguardar
        with self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        self.handles[32001].parar.assert_called_once()
        self.handles[32001].close.assert_called_once()

    def test_total_esgotado_nao_para(self):
        with patch.object(app.time, 'monotonic', side_effect=[1, 20]):
            with self.assertRaises(app.FalhaEncerrarTeste):
                self.encerrar()
        app._ProcessoWindows.assert_not_called()

    def test_revalidacao_lenta_nao_dispara_parada_fora_do_prazo(self):
        relogio = [0]
        chamadas = []
        original = app._revalidar_alvo
        def lento(*args):
            chamadas.append(1)
            original(*args)
            if len(chamadas) == 3:
                relogio[0] = 15
        with patch.object(app.time, 'monotonic', side_effect=lambda: relogio[0]), \
                patch.object(app, '_revalidar_alvo', side_effect=lento):
            with self.assertRaises(app.FalhaEncerrarTeste):
                self.encerrar()
        self.handles[32001].parar.assert_not_called()
        self.handles[32001].close.assert_called_once()

    def test_sem_confirmacao_nao_inspeciona_processos(self):
        with self.assertRaises(PermissionError):
            app.encerrar_teste()
        app._psutil.assert_not_called()

    def test_fora_windows_nao_inspeciona_processos(self):
        with patch.object(app, '_WINDOWS', False), self.assertRaises(app.FalhaEncerrarTeste):
            self.encerrar()
        app._psutil.assert_not_called()

    def test_prazos_invalidos_nao_inspecionam_processos(self):
        for prazo in (True, 0, 11, float('inf'), float('nan'), '10'):
            with self.assertRaises(ValueError):
                self.encerrar(timeout=prazo)
        app._psutil.assert_not_called()

    def test_erro_privado_nao_e_impresso(self):
        app._ProcessoWindows.side_effect = OSError('fixture-token-private-url')
        saida = io.StringIO()
        with redirect_stdout(saida):
            self.assertEqual(app.main(['--confirmar']), 1)
        self.assertNotIn('fixture-token', saida.getvalue())
        self.assertNotIn('32001', saida.getvalue())


if __name__ == '__main__':
    unittest.main()
