"""Diagnóstico de dono da porta com metadados fictícios; sem processos Windows."""
from __future__ import annotations
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import iniciar_servicos_locais as servicos


class DiagnosticoPortaOllama(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.powershell=self.raiz/'System32'/'WindowsPowerShell'/'v1.0'/'powershell.exe'
        self.powershell.parent.mkdir(parents=True);self.powershell.write_bytes(b'fixture')
        p=patch.dict(os.environ,{'SYSTEMROOT':str(self.raiz),'OLLAMA_HABILITADO':'1',
            'OLLAMA_MODELS':str(self.raiz/'Models'),'OPENAI_API_KEY':'fixture_segredo_privado',
            'HTTPS_PROXY':'http://fixture_segredo_privado.invalid','PYTHONPATH':'fixture_segredo_privado'},clear=True)
        p.start();self.addCleanup(p.stop)
        p=patch.object(servicos,'_WINDOWS',True);p.start();self.addCleanup(p.stop)
        p=patch.object(servicos,'consultar',return_value={'ok':False,'categoria':'timeout'});self.api=p.start();self.addCleanup(p.stop)
        p=patch.object(servicos.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"listeners":[]}'))
        self.run=p.start();self.addCleanup(p.stop)
        p=patch.object(servicos.subprocess,'Popen');self.iniciar=p.start();self.addCleanup(p.stop)

    def listeners(self,itens):
        self.run.return_value=SimpleNamespace(returncode=0,stdout=json.dumps({'listeners':itens}))

    def test_api_pronta_nao_executa_powershell_nem_inicia_processo(self):
        self.api.return_value={'ok':True,'dados':{'version':'fixture'}}
        d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'api_pronta');self.assertIs(d['api_responde'],True)
        self.api.assert_called_once_with(servicos.URL_PADRAO,'/api/version',timeout=3)
        self.run.assert_not_called();self.iniciar.assert_not_called()

    def test_dono_ollama_e_identificado_sem_autorizar_reinicio(self):
        self.listeners([{'pid':4321,'nome':'ollama'}])
        d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'ocupada_ollama')
        self.assertEqual(d['processos'],[{'pid':4321,'nome':'ollama.exe','tipo':'ollama'}])
        self.assertEqual(d['acao_recomendada'],'conferir_ollama_existente')
        self.assertFalse(d['reparo_automatico']);self.iniciar.assert_not_called()

    def test_consulta_windows_e_limitada_ao_endpoint_local_e_sem_segredos(self):
        self.listeners([{'pid':11,'nome':'node'}])
        d=servicos.diagnosticar_porta_ollama('http://[::1]:11435',sondar_api=False)
        self.assertEqual(d['estado'],'ocupada_outro');self.assertEqual(d['porta'],11435)
        self.api.assert_not_called();self.run.assert_called_once()
        args,kw=self.run.call_args
        self.assertEqual(args[0][0],str(self.powershell));self.assertEqual(args[0][1:4],['-NoProfile','-NonInteractive','-Command'])
        script=args[0][4]
        self.assertIn('LocalPort -eq 11435',script);self.assertIn("'::1'",script)
        self.assertNotIn('CommandLine',script);self.assertNotIn('ExecutablePath',script)
        self.assertEqual(kw['timeout'],4);self.assertIs(kw['shell'],False)
        self.assertEqual(kw['stderr'],subprocess.DEVNULL);self.assertEqual(kw['stdin'],subprocess.DEVNULL)
        self.assertNotIn('fixture_segredo_privado',repr(self.run.call_args))
        self.assertNotIn('fixture_segredo_privado',repr(d));self.iniciar.assert_not_called()

    def test_nome_arbitrario_e_omitido_mantendo_so_pid_e_rotulo(self):
        self.listeners([{'pid':987,'nome':'fixture_segredo_privado'}])
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['processos'],[{'pid':987,'nome':'outro processo','tipo':'outro'}])
        self.assertNotIn('fixture_segredo_privado',repr(d))

    def test_pid_sem_nome_nao_e_tratado_como_ollama(self):
        self.listeners([{'pid':65,'nome':None}])
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'ocupada_nao_identificada')
        self.assertEqual(d['processos'][0]['tipo'],'nao_identificado')

    def test_sem_listener_e_amostra_nao_prova_api_ou_porta_livre(self):
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'sem_escuta_identificada');self.assertIsNone(d['api_responde'])
        self.assertEqual(d['processos'],[]);self.assertFalse(d['reparo_automatico'])
        self.api.assert_not_called();self.iniciar.assert_not_called()

    def test_timeout_ou_erro_windows_nao_expoe_erro_bruto(self):
        for erro in (OSError('fixture_segredo_privado'),subprocess.TimeoutExpired(['fixture_segredo_privado'],4)):
            with self.subTest(erro=type(erro).__name__):
                self.run.side_effect=erro
                d=servicos.diagnosticar_porta_ollama(sondar_api=False)
                self.assertEqual(d['estado'],'indeterminada');self.assertNotIn('fixture_segredo_privado',repr(d))
                self.assertFalse(d['reparo_automatico'])
        self.iniciar.assert_not_called()

    def test_schema_pid_e_tamanho_invalidos_nao_revelam_stdout(self):
        casos=['{nao json','{"listeners":[],"privado":"fixture_segredo_privado"}',
            json.dumps({'listeners':[{'pid':True,'nome':'ollama'}]}),
            json.dumps({'listeners':[{'pid':-1,'nome':'ollama'}]}),
            json.dumps({'listeners':[{'pid':1,'nome':'ollama','commandline':'fixture_segredo_privado'}]}),
            'fixture_segredo_privado'*600]
        for bruto in casos:
            with self.subTest(bruto=bruto[:20]):
                self.run.return_value=SimpleNamespace(returncode=0,stdout=bruto)
                d=servicos.diagnosticar_porta_ollama(sondar_api=False)
                self.assertEqual(d['estado'],'indeterminada');self.assertNotIn('fixture_segredo_privado',repr(d))
        self.iniciar.assert_not_called()

    def test_pid_duplicado_e_emitido_uma_vez(self):
        self.listeners([{'pid':12,'nome':'ollama'},{'pid':12,'nome':'ollama'}])
        self.assertEqual(len(servicos.diagnosticar_porta_ollama(sondar_api=False)['processos']),1)

    def test_executavel_windows_ausente_nao_procura_scripts_no_path(self):
        self.powershell.unlink()
        d=servicos.diagnosticar_porta_ollama(sondar_api=False)
        self.assertEqual(d['estado'],'indeterminada');self.run.assert_not_called()

    def test_endpoint_remoto_invalido_ou_flag_invalida_nao_executam_sondas(self):
        for url in ('http://example.invalid:11434','http://10.0.0.1:11434','http://usuario:fixture_segredo_privado@127.0.0.1:11434'):
            with self.subTest(url=url):
                d=servicos.diagnosticar_porta_ollama(url)
                self.assertEqual(d['estado'],'endereco_invalido');self.assertNotIn('fixture_segredo_privado',repr(d))
        with self.assertRaises(ValueError):servicos.diagnosticar_porta_ollama(sondar_api=1)
        self.api.assert_not_called();self.run.assert_not_called();self.iniciar.assert_not_called()

    def test_outro_sistema_nao_diagnostica_como_se_fosse_pc_windows(self):
        with patch.object(servicos,'_WINDOWS',False):
            d=servicos.diagnosticar_porta_ollama()
        self.assertEqual(d['estado'],'plataforma_nao_suportada')
        self.api.assert_not_called();self.run.assert_not_called()

    def test_inicio_com_porta_ocupada_identifica_sem_repetir_api_ou_servidor(self):
        self.listeners([{'pid':4321,'nome':'ollama'}])
        with patch.object(servicos,'_porta_ocupada',return_value=True):
            d=servicos.garantir_ollama()
        self.assertEqual(set(d),{'ok','iniciado','mensagem'})
        self.assertFalse(d['ok']);self.assertFalse(d['iniciado'])
        self.assertIn('PID 4321',d['mensagem']);self.assertIn('Nenhum segundo servidor',d['mensagem'])
        self.api.assert_called_once();self.run.assert_called_once();self.iniciar.assert_not_called()

    def test_politica_zero_impede_diagnostico_e_inicio_automatico(self):
        with patch.dict(os.environ,{'OLLAMA_INICIAR_SERVICO':'0'}),patch.object(servicos,'_porta_ocupada') as porta:
            d=servicos.garantir_ollama()
        self.assertFalse(d['iniciado']);porta.assert_not_called();self.run.assert_not_called();self.iniciar.assert_not_called()


@unittest.skipUnless(os.name=='nt','A opção nativa SO_EXCLUSIVEADDRUSE é específica de Windows.')
class VinculoExclusivoWindowsNativo(unittest.TestCase):
    """Somente sockets efêmeros próprios em loopback; nenhum aplicativo real."""
    def conferir(self,familia,host):
        try:
            escuta=socket.socket(familia,socket.SOCK_STREAM,socket.IPPROTO_TCP)
        except OSError:
            if familia==socket.AF_INET6:self.skipTest('IPv6 não disponível neste Windows.')
            raise
        with escuta:
            escuta.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
            if familia==socket.AF_INET6:escuta.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
            escuta.bind((host,0));escuta.listen(1)
            porta=escuta.getsockname()[1]
            url='http://'+('['+host+']' if familia==socket.AF_INET6 else host)+':'+str(porta)
            partes=servicos.urlsplit(servicos.validar_url(url))
            self.assertFalse(servicos._vinculo_exclusivo_disponivel(partes))
        self.assertTrue(servicos._vinculo_exclusivo_disponivel(partes))

    def test_ipv4_ocupada_e_disponivel_apos_fechar_o_socket_proprio(self):
        self.conferir(socket.AF_INET,'127.0.0.1')

    def test_ipv6_ocupada_e_disponivel_apos_fechar_o_socket_proprio(self):
        self.conferir(socket.AF_INET6,'::1')


class SondagemPortaOllamaWindows(unittest.TestCase):
    """Reproduz TCP inconclusivo sem abrir portas ou iniciar serviços reais."""
    def setUp(self):
        self.patches=[]
        def aplicar(alvo,nome,**kw):
            p=patch.object(alvo,nome,**kw);self.patches.append(p)
            return p.start()
        self.addCleanup(lambda:[p.stop() for p in reversed(self.patches)])
        aplicar(servicos,'_WINDOWS',new=True)
        aplicar(servicos.socket,'SO_EXCLUSIVEADDRUSE',new=-5,create=True)
        self.conectar=aplicar(servicos.socket,'create_connection',side_effect=TimeoutError('fixture_privada'))
        self.socket=aplicar(servicos.socket,'socket')
        self.prova=self.socket.return_value.__enter__.return_value
        self.iniciar=aplicar(servicos.subprocess,'Popen')

    def test_conexao_tcp_confirmada_nao_tenta_bind(self):
        self.conectar.side_effect=None
        self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.conectar.return_value.__exit__.assert_called_once()
        self.socket.assert_not_called();self.iniciar.assert_not_called()

    def test_recusa_tcp_explicita_preserva_resultado_sem_sonda_extra(self):
        self.conectar.side_effect=ConnectionRefusedError()
        self.assertFalse(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.socket.assert_not_called();self.iniciar.assert_not_called()

    def test_timeout_com_bind_exclusivo_livre_nao_e_confundido_com_escuta(self):
        self.assertFalse(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.socket.assert_called_once_with(servicos.socket.AF_INET,servicos.socket.SOCK_STREAM,servicos.socket.IPPROTO_TCP)
        self.prova.setsockopt.assert_called_once_with(servicos.socket.SOL_SOCKET,-5,1)
        self.prova.bind.assert_called_once_with(('127.0.0.1',11434))
        self.prova.listen.assert_not_called()
        self.socket.return_value.__exit__.assert_called_once();self.iniciar.assert_not_called()

    def test_permissao_na_conexao_so_libera_inicio_quando_bind_exclusivo_confirma(self):
        self.conectar.side_effect=PermissionError('fixture_privada')
        self.assertFalse(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.prova.bind.assert_called_once_with(('127.0.0.1',11434))
        self.socket.return_value.__exit__.assert_called_once();self.iniciar.assert_not_called()

    def test_bind_ocupado_ou_negado_nao_prova_porta_livre_e_libera_socket(self):
        for erro in (OSError(10048,'fixture_privada'),PermissionError(10013,'fixture_privada')):
            with self.subTest(codigo=erro.errno):
                self.socket.reset_mock();self.prova.bind.side_effect=erro
                self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
                self.socket.return_value.__exit__.assert_called_once()
                self.prova.listen.assert_not_called()
        self.iniciar.assert_not_called()

    def test_socket_sem_opcao_exclusiva_nao_pode_confirmar_disponibilidade(self):
        with patch.object(servicos.socket,'SO_EXCLUSIVEADDRUSE',None):
            self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.socket.assert_not_called();self.iniciar.assert_not_called()

    def test_falha_na_opcao_exclusiva_nao_usa_reuseaddr_nem_bind(self):
        self.prova.setsockopt.side_effect=OSError('fixture_privada')
        self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.prova.bind.assert_not_called();self.prova.listen.assert_not_called()
        self.socket.return_value.__exit__.assert_called_once();self.iniciar.assert_not_called()

    def test_falha_ao_criar_socket_continua_indeterminada(self):
        self.socket.side_effect=OSError('fixture_privada')
        self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.iniciar.assert_not_called()

    def test_ipv6_prova_exclusiva_so_no_endpoint_e_familia_selecionados(self):
        self.assertFalse(servicos._porta_ocupada('http://[::1]:11435'))
        self.socket.assert_called_once_with(servicos.socket.AF_INET6,servicos.socket.SOCK_STREAM,servicos.socket.IPPROTO_TCP)
        self.assertEqual(self.prova.setsockopt.call_count,2)
        self.prova.setsockopt.assert_any_call(servicos.socket.SOL_SOCKET,-5,1)
        self.prova.setsockopt.assert_any_call(servicos.socket.IPPROTO_IPV6,servicos.socket.IPV6_V6ONLY,1)
        self.prova.bind.assert_called_once_with(('::1',11435))
        self.prova.listen.assert_not_called();self.socket.return_value.__exit__.assert_called_once()

    def test_fora_do_windows_timeout_nao_autoriza_bind_ou_inicio(self):
        with patch.object(servicos,'_WINDOWS',False):
            self.assertTrue(servicos._porta_ocupada(servicos.URL_PADRAO))
        self.socket.assert_not_called();self.iniciar.assert_not_called()

    def test_url_remota_credencial_e_nome_dns_nao_chegam_a_sockets(self):
        for url in ('http://example.invalid:11434','http://localhost:11434',
                'http://usuario:fixture_privada@127.0.0.1:11434','http://10.0.0.1:11434'):
            with self.subTest(url=url),self.assertRaises(ValueError):servicos._porta_ocupada(url)
        self.conectar.assert_not_called();self.socket.assert_not_called();self.iniciar.assert_not_called()

    def test_bind_e_liberado_antes_de_tentar_um_unico_servidor(self):
        eventos=[]
        self.socket.return_value.__exit__.side_effect=lambda *_:eventos.append('liberou_bind')
        self.iniciar.side_effect=lambda *_args,**_kw:eventos.append('iniciou') or MagicMock()
        ambiente={'OLLAMA_HABILITADO':'1','OLLAMA_INICIAR_SERVICO':'1','OLLAMA_NO_CLOUD':'1'}
        with patch.dict(os.environ,ambiente,clear=True), \
                patch.object(servicos,'_responde',side_effect=[False,True]) as api, \
                patch.object(servicos,'_executavel_ollama',return_value=Path(sys.executable)), \
                patch.object(servicos,'diagnosticar_porta_ollama') as diagnostico:
            resultado=servicos.garantir_ollama()
        self.assertTrue(resultado['ok']);self.assertTrue(resultado['iniciado'])
        self.assertEqual(eventos,['liberou_bind','iniciou'])
        self.iniciar.assert_called_once();diagnostico.assert_not_called();self.assertEqual(api.call_count,2)
        self.assertEqual(self.iniciar.call_args.args[0],[str(Path(sys.executable)),'serve'])
        self.assertEqual(self.iniciar.call_args.kwargs['env']['OLLAMA_NO_CLOUD'],'1')

    def test_bind_negado_mantem_instancia_e_nao_repete_api_ou_popen(self):
        self.prova.bind.side_effect=PermissionError('fixture_privada')
        with patch.dict(os.environ,{'OLLAMA_HABILITADO':'1'},clear=True), \
                patch.object(servicos,'_responde',return_value=False) as api, \
                patch.object(servicos,'diagnosticar_porta_ollama',return_value={'mensagem':'Nenhuma escuta identificada.'}) as diagnostico:
            resultado=servicos.garantir_ollama()
        self.assertFalse(resultado['ok']);self.assertFalse(resultado['iniciado'])
        self.assertIn('porta não pôde ser confirmada livre',resultado['mensagem'])
        self.assertNotIn('fixture_privada',repr(resultado))
        api.assert_called_once();diagnostico.assert_called_once();self.iniciar.assert_not_called()


if __name__=='__main__':unittest.main()
