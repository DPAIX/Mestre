"""Preparação de serviços simulada; não instala nem inicia programas reais."""
from contextlib import ExitStack
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preparacao_autonoma as prep
import configuracao_assistente as config
import integracoes_9stack as stack
import iniciar_servicos_locais as ollama
import configurar_ia_local as modelos


class ServicosPreparacaoTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        raiz=Path(self.tmp.name).resolve();codigo=raiz/'codigo';codigo.mkdir()
        self.ctx=prep.Caminhos(codigo,codigo,raiz/'externo'/'.env',raiz/'externo'/'dados',
            raiz/'externo'/'preparacao',raiz/'externo'/'backups',codigo/'manifesto_instalacao.json')
        self.pilhas=ExitStack();self.addCleanup(self.pilhas.close)
        self.pilhas.enter_context(patch.dict(os.environ,{'OLLAMA_HABILITADO':'1',
            'OLLAMA_INICIAR_SERVICO':'1','OLLAMA_URL':'http://127.0.0.1:11434'},clear=True))
        self.node=self.pilhas.enter_context(patch.object(config,'_preparar_node',return_value='Node conferido.'))
        self.validar_node=self.pilhas.enter_context(patch.object(stack,'_node',return_value=Path('/fixture/node.exe')))
        self.instalar=self.pilhas.enter_context(patch.object(config,'_instalar_se_pendente',return_value='Pacote conferido.'))
        self.executar=self.pilhas.enter_context(patch.object(stack,'executar_9stack',return_value='Abertura solicitada.'))
        self.prontidao=self.pilhas.enter_context(patch.object(prep,'_aguardar_gateway_http',return_value=True))
        self.garantir=self.pilhas.enter_context(patch.object(ollama,'garantir_ollama',
            return_value={'ok':False,'iniciado':False,'mensagem':'Porta ocupada; nenhum segundo servidor.'}))
        self.instalar_ollama=self.pilhas.enter_context(patch.object(prep,'_instalar_ollama_ausente',return_value=False))
        self.motor=prep.Preparador(self.ctx)

    def itens(self):return {i['id']:i for i in self.motor.snapshot()['itens']}

    def test_node_pendente_nao_vira_pronto_nem_executa_npm(self):
        self.node.return_value='Node.js pendente. Instale o LTS.'
        self.validar_node.side_effect=RuntimeError('fixture sem versão')
        self.motor._servicos()
        self.assertEqual(self.itens()['node']['estado'],'pendente')
        self.instalar.assert_not_called();self.executar.assert_not_called()
        self.garantir.assert_called_once()
        self.assertIn('node_instalacao',[p['servico'] for p in self.motor.snapshot()['pendencias']])

    def test_falha_9remote_nao_oculta_inicio_do_9router(self):
        def instalar(servico):
            if servico=='9remote':raise RuntimeError('fixture segredo não público')
            return 'Pacote esperado presente.'
        self.instalar.side_effect=instalar
        self.motor._servicos()
        self.executar.assert_called_once_with('9router','iniciar',confirmado=True)
        self.assertEqual(self.itens()['gateway_servico']['estado'],'http_responde')
        self.assertEqual(self.itens()['9remote']['estado'],'pendente')
        self.assertNotIn('segredo',str(self.motor.snapshot()))
        self.garantir.assert_called_once()

    def test_falha_9router_nao_impede_interface_9remote(self):
        def executar(servico,*args,**kw):
            if servico=='9router':raise OSError('fixture')
            return 'Interface solicitada sem túnel.'
        self.executar.side_effect=executar
        self.motor._servicos()
        self.assertEqual(self.itens()['gateway_servico']['estado'],'pendente')
        self.assertEqual(self.itens()['9remote']['estado'],'interface_solicitada')
        self.assertEqual(self.executar.call_args.args,('9remote','abrir'))

    def test_retomar_nao_abre_9remote_de_novo_e_nunca_pede_tunel(self):
        self.motor._servicos();self.motor._servicos()
        remotos=[c for c in self.executar.call_args_list if c.args[0]=='9remote']
        self.assertEqual(len(remotos),1)
        self.assertEqual(remotos[0].args,('9remote','abrir'))
        self.assertEqual(self.itens()['9remote']['estado'],'interface_solicitada')
        self.assertIn('Nenhuma nova abertura',self.itens()['9remote']['detalhe'])

    def test_porta_ocupada_nao_instala_ollama_nem_declara_geracao_pronta(self):
        self.motor._servicos()
        self.instalar_ollama.assert_not_called()
        self.assertEqual(self.itens()['ollama']['estado'],'pendente')
        self.assertEqual(self.itens()['gateway_servico']['estado'],'http_responde')

    def test_servico_cold_start_aguarda_http_antes_de_continuar(self):
        ordem=[]
        self.executar.side_effect=lambda servico,*a,**kw:ordem.append(servico) or 'Solicitado.'
        self.prontidao.side_effect=lambda:ordem.append('aguardar') or False
        self.motor._servicos()
        self.assertEqual(ordem,['9router','aguardar','9remote'])
        self.assertEqual(self.itens()['gateway_servico']['estado'],'pendente')
        self.assertIn('25 segundos',self.itens()['gateway_servico']['detalhe'])

    def test_ollama_ausente_instala_uma_vez_e_revalida_inicio(self):
        self.garantir.side_effect=[{'ok':False,'mensagem':'Ollama não foi encontrado no PC. Instale-o para usar os modelos locais.'},
            {'ok':False,'mensagem':'Porta ocupada após instalar; nenhum segundo servidor.'}]
        self.instalar_ollama.return_value=True
        self.motor._servicos()
        self.instalar_ollama.assert_called_once_with(self.ctx)
        self.assertEqual(self.garantir.call_count,2)
        self.assertEqual(self.itens()['ollama']['estado'],'pendente')

    def test_politica_manual_impede_instalar_ollama(self):
        os.environ['OLLAMA_INICIAR_SERVICO']='0'
        self.garantir.return_value={'ok':False,'mensagem':'Ollama não foi encontrado no PC.'}
        self.motor._servicos();self.instalar_ollama.assert_not_called()

    def test_erro_ollama_nao_vaza_excecao_nem_aborta_outras_etapas(self):
        self.garantir.side_effect=OSError('fixture-segredo')
        self.motor._servicos()
        self.assertEqual(self.itens()['ollama']['estado'],'pendente')
        self.assertIn('gateway_servico',self.itens())
        self.assertNotIn('fixture-segredo',str(self.motor.snapshot()))

    def test_catalogo_sem_modelo_local_nao_declara_modelo_selecionado(self):
        self.garantir.return_value={'ok':True,'mensagem':'Metadados prontos.'}
        with patch.object(modelos,'listar_catalogo',return_value=[{'nome':'cloud:latest','nuvem':True}]), \
             patch.object(modelos,'usar_existente',return_value=None) as usar:
            self.motor._servicos()
        usar.assert_called_once()
        self.assertEqual(self.itens()['modelos']['estado'],'pendente')


class InstalacaoOllamaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.ctx=SimpleNamespace(codigo=self.raiz,arquivo_env=self.raiz/'externo'/'.env',dados=self.raiz/'externo'/'dados')
        self.pilhas=ExitStack();self.addCleanup(self.pilhas.close)
        self.pilhas.enter_context(patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_INICIAR_SERVICO':'1',
            'OLLAMA_NO_CLOUD':'1','OLLAMA_MODELS':'fixture-pesos','OPENAI_API_KEY':'fixture-segredo',
            'PYTHONPATH':'fixture-segredo','NODE_OPTIONS':'fixture-segredo'},clear=True))
        self.pilhas.enter_context(patch.object(prep.sys,'platform','win32'))
        self.exe=self.pilhas.enter_context(patch.object(ollama,'_executavel_ollama',return_value=None))
        self.which=self.pilhas.enter_context(patch.object(prep.shutil,'which',return_value=str(self.raiz/'winget.exe')))
        self.run=self.pilhas.enter_context(patch.object(prep.subprocess,'run',return_value=SimpleNamespace(returncode=0)))

    def test_politicas_ou_plataforma_impedem_instalacao_sem_sondar(self):
        for campo in ('OLLAMA_HABILITADO','OLLAMA_INICIAR_SERVICO'):
            with self.subTest(campo=campo),patch.dict(os.environ,{campo:'0'}):
                self.assertFalse(prep._instalar_ollama_ausente(self.ctx))
        with patch.object(prep.sys,'platform','linux'):
            self.assertFalse(prep._instalar_ollama_ausente(self.ctx))
        self.exe.assert_not_called();self.which.assert_not_called();self.run.assert_not_called()

    def test_executavel_existente_nao_reinstala(self):
        self.exe.return_value=self.raiz/'ollama.exe'
        self.assertTrue(prep._instalar_ollama_ausente(self.ctx))
        self.run.assert_not_called();self.which.assert_not_called()

    def test_ausencia_winget_permanece_pendente(self):
        self.which.return_value=None
        self.assertFalse(prep._instalar_ollama_ausente(self.ctx));self.run.assert_not_called()

    def test_comando_oficial_fixo_sem_segredos_e_confirma_executavel(self):
        instalado=self.raiz/'Ollama'/'ollama.exe'
        self.exe.side_effect=[None,instalado]
        self.assertTrue(prep._instalar_ollama_ausente(self.ctx))
        self.run.assert_called_once()
        comando=self.run.call_args.args[0];opcoes=self.run.call_args.kwargs
        self.assertIn('Ollama.Ollama',comando);self.assertIn('--silent',comando)
        self.assertNotIn('pull',comando);self.assertIs(opcoes['shell'],False)
        self.assertEqual(opcoes['timeout'],600)
        self.assertEqual(opcoes['env']['OLLAMA_NO_CLOUD'],'1')
        self.assertEqual(opcoes['env']['OLLAMA_MODELS'],'fixture-pesos')
        self.assertNotIn('fixture-segredo',repr(opcoes))
        self.assertEqual(opcoes['stdout'],subprocess.PIPE)
        self.assertTrue(os.environ['PATH'].startswith(str(instalado.parent)))

    def test_sucesso_winget_sem_executavel_nao_significa_pronto(self):
        self.assertFalse(prep._instalar_ollama_ausente(self.ctx))
        self.assertEqual(self.exe.call_count,2)

    def test_falha_winget_nao_repete(self):
        self.run.return_value.returncode=1
        self.assertFalse(prep._instalar_ollama_ausente(self.ctx));self.run.assert_called_once()
        self.assertEqual(self.exe.call_count,1)

    def test_endpoint_remoto_invalido_nao_instala(self):
        with patch.dict(os.environ,{'OLLAMA_URL':'http://192.168.1.1:11434'}):
            with self.assertRaises(ValueError):prep._instalar_ollama_ausente(self.ctx)
        self.exe.assert_not_called();self.run.assert_not_called()


class ProntidaoGatewayTeste(unittest.TestCase):
    def setUp(self):
        self.pilhas=ExitStack();self.addCleanup(self.pilhas.close)
        self.build=self.pilhas.enter_context(patch.object(prep.urllib.request,'build_opener'))
        self.opener=self.build.return_value
        self.relogio=[0.]
        self.pilhas.enter_context(patch.object(prep.time,'monotonic',side_effect=lambda:self.relogio[0]))
        self.sleep=self.pilhas.enter_context(patch.object(prep.time,'sleep',side_effect=lambda n:self.relogio.__setitem__(0,self.relogio[0]+n)))
        self.pilhas.enter_context(patch.dict(os.environ,{'NINE_ROUTER_API_KEY':'fixture-segredo',
            'HTTP_PROXY':'http://fixture-segredo.invalid:99','NINE_ROUTER_URL':'http://127.0.0.1:20128/v1'},clear=True))

    def resposta(self,status=200):
        resposta=MagicMock();resposta.__enter__.return_value.status=status
        return resposta

    def test_http_pronto_sem_ler_corpo_ou_repassar_chave_proxy(self):
        resposta=self.resposta();self.opener.open.return_value=resposta
        self.assertTrue(prep._aguardar_gateway_http())
        self.opener.open.assert_called_once()
        pedido=self.opener.open.call_args.args[0]
        self.assertEqual(pedido.full_url,'http://127.0.0.1:20128/v1/models')
        self.assertEqual(pedido.get_method(),'GET');self.assertIsNone(pedido.data)
        self.assertEqual(pedido.header_items(),[('Accept','application/json')])
        self.assertNotIn('fixture-segredo',repr(pedido.header_items()))
        resposta.__enter__.return_value.read.assert_not_called()
        self.assertEqual(self.build.call_args.args[0].proxies,{})
        self.assertIsInstance(self.build.call_args.args[1],prep._SemRedirecionamento)
        self.sleep.assert_not_called()

    def test_primeira_recusa_pode_ser_seguida_de_http_pronto(self):
        self.opener.open.side_effect=[urllib.error.URLError('fixture recusado'),self.resposta()]
        self.assertTrue(prep._aguardar_gateway_http())
        self.assertEqual(self.opener.open.call_count,2);self.sleep.assert_called_once_with(.8)

    def test_401_e_403_significam_http_pronto_sem_credencial(self):
        for codigo in (401,403):
            self.opener.open.reset_mock()
            erro=urllib.error.HTTPError('http://fixture',codigo,'fixture',{},None)
            self.opener.open.side_effect=erro
            with self.subTest(codigo=codigo):
                self.assertTrue(prep._aguardar_gateway_http())
                self.opener.open.assert_called_once()

    def test_redirect_e_recusado_sem_seguir_local_ou_remoto(self):
        self.opener.open.side_effect=urllib.error.HTTPError('http://fixture',302,'fixture',
            {'Location':'https://fixture-segredo.invalid'},None)
        self.assertFalse(prep._aguardar_gateway_http());self.opener.open.assert_called_once()
        self.sleep.assert_not_called()
        self.assertIsNone(prep._SemRedirecionamento().redirect_request(None,None,302,'',{},'https://fixture.invalid'))

    def test_recusas_imediatas_respeitam_teto_25_segundos_32_leituras(self):
        self.opener.open.side_effect=urllib.error.URLError('fixture recusado')
        self.assertFalse(prep._aguardar_gateway_http())
        self.assertLessEqual(self.opener.open.call_count,32)
        self.assertLessEqual(self.relogio[0],25)
        self.assertTrue(all(0<c.kwargs['timeout']<=2 for c in self.opener.open.call_args_list))

    def test_timeouts_de_conexao_tambem_contam_no_prazo_total(self):
        def recusar(*a,**kw):
            self.relogio[0]+=kw['timeout'];raise TimeoutError('fixture')
        self.opener.open.side_effect=recusar
        self.assertFalse(prep._aguardar_gateway_http())
        self.assertLess(self.opener.open.call_count,15);self.assertLessEqual(self.relogio[0],25)

    def test_url_remota_credencial_query_ou_dns_nao_abrem_rede(self):
        for url in ('http://localhost:20128/v1','https://example.invalid/v1',
                    'http://usuario:fixture@127.0.0.1:20128/v1','http://127.0.0.1:20128/v1?fixture=1'):
            with self.subTest(url=url):self.assertFalse(prep._aguardar_gateway_http(url))
        self.build.assert_not_called();self.opener.open.assert_not_called()


if __name__=='__main__':unittest.main()
