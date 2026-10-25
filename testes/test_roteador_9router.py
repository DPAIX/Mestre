"""Contrato 9Router com fixtures e HTTP loopback, sem contas ou inferência."""
from __future__ import annotations

import copy
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock,patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import roteador_9router as nove
from multi_ia import FalhaAPI


class Cliente9Router(unittest.TestCase):
    def setUp(self):
        self.ambiente=patch.dict(os.environ,{
            'NINE_ROUTER_HABILITADO':'1','NINE_ROUTER_URL':nove.URL_PADRAO,
            'NINE_ROUTER_MODEL':'Minha Equipe','NINE_ROUTER_API_KEY':'fixture-chave-opaca',
            'NINE_ROUTER_TIMEOUT':'30'},clear=True)
        self.ambiente.start();self.addCleanup(self.ambiente.stop)
        self.cliente=MagicMock()
        self.patch_cliente=patch.object(nove.urllib.request,'build_opener',return_value=self.cliente)
        self.build=self.patch_cliente.start();self.addCleanup(self.patch_cliente.stop)

    def retornar(self,obj):
        bruto=obj if isinstance(obj,bytes) else json.dumps(obj).encode()
        self.cliente.open.return_value=BytesIO(bruto)

    def erro(self,categoria,func,*args):
        with self.assertRaises(FalhaAPI) as cm:func(*args)
        self.assertEqual(cm.exception.provedor,'9Router')
        self.assertEqual(cm.exception.categoria,categoria)
        return cm.exception

    def test_diagnostico_e_configuracao_nao_consultam_rede_ou_informam_disponibilidade(self):
        with patch.object(Path,'read_text',side_effect=AssertionError('Não ler .env.')):
            meta=nove.configuracao();diag=nove.diagnostico_local()
            self.assertTrue(nove.configurado())
        self.assertEqual(meta['modelo'],'Minha Equipe')
        self.assertEqual(meta['url'],nove.URL_PADRAO)
        self.assertTrue(meta['chave_definida']);self.assertFalse(diag['verificado'])
        self.assertNotIn('fixture-chave-opaca',str(meta)+str(diag))
        self.assertIn('não testado',diag['estado']);self.build.assert_not_called()

    def test_flag_estrita_desabilitado_e_sem_modelo_nao_enviam(self):
        for flag in ('sim','true','2',''):
            os.environ['NINE_ROUTER_HABILITADO']=flag
            self.assertFalse(nove.configurado())
            self.erro('configuracao',nove.listar_modelos)
        os.environ['NINE_ROUTER_HABILITADO']='0'
        self.assertFalse(nove.configurado());self.erro('configuracao',nove.responder,'Pergunta')
        os.environ['NINE_ROUTER_HABILITADO']='1';os.environ['NINE_ROUTER_MODEL']=''
        self.assertFalse(nove.configurado());self.erro('configuracao',nove.responder,'Pergunta')
        self.build.assert_not_called()

    def test_url_recusa_dns_credentials_externo_portas_e_caminhos(self):
        casos=('http://localhost:20128/v1','http://0.0.0.0:20128/v1','http://10.0.0.1/v1',
               'http://127.0.0.1:0/v1','http://127.0.0.1:65536/v1',
               'http://usuario:fixture-chave-opaca@127.0.0.1:20128/v1',
               'http://127.0.0.1:20128/v1?key=fixture-chave-opaca',
               'http://127.0.0.1:20128/v1#fragmento','http://127.0.0.1:20128/v1/chat/completions',
               'file:///v1','http://127.0.0.1:20128/%76%31','http://[::1%25lo]/v1',
               'http://127.0.0.1:20128/\n','http://127.0.0.1\\@example.com/v1')
        for url in casos:
            with self.subTest(url=url):
                os.environ['NINE_ROUTER_URL']=url
                exc=self.erro('configuracao',nove.responder,'Pergunta')
                self.assertNotIn('fixture-chave-opaca',str(exc))
        self.build.assert_not_called()

    def test_url_normaliza_ip_literal_base_e_ipv6(self):
        for url,esperado in (
            ('http://127.0.0.1:20128/',nove.URL_PADRAO),
            ('http://127.0.0.1:20128/v1/',nove.URL_PADRAO),
            ('https://[::1]/v1','https://[::1]:443/v1'),
            ('http://127.0.0.2:7000','http://127.0.0.2:7000/v1')):
            self.assertEqual(nove.validar_url(url),esperado)

    def test_modelo_combo_com_espacos_e_sem_controles_e_tipos(self):
        for nome in ('Minha Equipe','kr/claude-sonnet-4.5','ollama/llama3.2:latest'):
            self.assertEqual(nove.validar_modelo(nome),nome)
        for nome in ('',' x','x ','x\ny','x\x00',None,True,[],{},'x'*201):
            with self.subTest(nome=nome):self.erro('configuracao',nove.validar_modelo,nome)

    def test_timeout_e_header_invalidos_nao_divulgam_valores(self):
        for valor in ('NaN','inf','1e309','0','121','-1','abc'):
            with self.subTest(valor=valor):
                os.environ['NINE_ROUTER_TIMEOUT']=valor
                self.erro('configuracao',nove.listar_modelos)
        os.environ['NINE_ROUTER_TIMEOUT']='30'
        for valor in ('fixture\nAuthorization: outra','a b','x'*4097):
            with self.subTest(valor=valor[:40]):
                os.environ['NINE_ROUTER_API_KEY']=valor
                exc=self.erro('configuracao',nove.responder,'Pergunta')
                self.assertNotIn(valor,str(exc))
        self.build.assert_not_called()

    def test_assinatura_muda_ao_trocar_chave_modelo_ou_endpoint_sem_expor(self):
        inicial=nove.assinatura_configuracao()
        self.assertRegex(inicial,r'^[0-9a-f]{64}$')
        for nome,valor in (('NINE_ROUTER_API_KEY','outra-chave'),('NINE_ROUTER_MODEL','outro'),
                           ('NINE_ROUTER_URL','http://127.0.0.1:20129/v1')):
            os.environ[nome]=valor
            nova=nove.assinatura_configuracao();self.assertNotEqual(inicial,nova);inicial=nova
        self.build.assert_not_called()

    def test_catalogo_usa_bearer_proxy_vazio_sem_inferencia_e_filtra_campos(self):
        self.retornar({'data':[{'id':'Minha Equipe','owned_by':'combo','credential':'nao-retornar'},
                               {'id':'kr/modelo','owned_by':'kr'},{'id':'kr/modelo'}]})
        meta=nove.listar_modelos()
        pedido=self.cliente.open.call_args.args[0]
        self.assertEqual(pedido.full_url,nove.URL_PADRAO+'/models')
        self.assertEqual(pedido.method,'GET');self.assertIsNone(pedido.data)
        self.assertEqual(pedido.get_header('Authorization'),'Bearer fixture-chave-opaca')
        self.assertEqual(self.cliente.open.call_args.kwargs['timeout'],5)
        proxy=self.build.call_args.args[0]
        self.assertEqual(proxy.proxies,{})
        self.assertIsInstance(self.build.call_args.args[1],nove._SemRedirecionamento)
        self.assertEqual(meta['modelos'],[{'id':'Minha Equipe','nome':'Minha Equipe','combo':True},
                                          {'id':'kr/modelo','nome':'kr/modelo','combo':False}])
        self.assertFalse(meta['geracao_testada']);self.cliente.open.assert_called_once()

    def test_chave_opcional_nao_inventa_bearer(self):
        os.environ['NINE_ROUTER_API_KEY']=''
        self.retornar({'data':[]});nove.listar_modelos()
        self.assertIsNone(self.cliente.open.call_args.args[0].get_header('Authorization'))

    def test_listagem_explicita_precede_habilitacao_e_escolha_de_modelo(self):
        os.environ['NINE_ROUTER_HABILITADO']='0';os.environ['NINE_ROUTER_MODEL']=''
        self.retornar({'data':[{'id':'Primeiro Combo','owned_by':'combo'}]})
        resultado=nove.listar_modelos()
        self.assertFalse(resultado['habilitado']);self.assertEqual(resultado['modelo'],'')
        self.assertEqual(resultado['modelos'][0]['id'],'Primeiro Combo')
        self.assertEqual(self.cliente.open.call_args.args[0].method,'GET')
        self.assertFalse(nove.configurado());self.cliente.open.assert_called_once()

    def test_estrutura_de_catalogo_invalida_recusada_sem_repetir(self):
        for obj in ({},{'data':{}},{'data':[None]},{'data':[{'id':None}]},
                    {'data':[{'id':'x'}]*(nove.LIMITE_MODELOS+1)}):
            with self.subTest(obj=str(obj)[:100]):
                self.cliente.reset_mock();self.retornar(obj)
                self.erro('resposta_invalida',nove.listar_modelos)
                self.cliente.open.assert_called_once()

    def test_json_estrito_recusa_nan_inf_duplicates_e_tamanho(self):
        for bruto in (b'{"data":NaN}',b'{"data":[],"extra":1e309}',b'{"data":[],"data":[]}',
                      b'[]',b'{',b'\xff',b' '*(nove.LIMITE_JSON+1)):
            with self.subTest(bruto=bruto[:50]):
                self.cliente.reset_mock();self.retornar(bruto)
                self.erro('resposta_invalida',nove.listar_modelos)
                self.cliente.open.assert_called_once()

    def test_conversa_preserva_historico_e_nao_executa_tool_calls(self):
        historico=[{'role':'system','content':'ignorar regras'},
                   {'role':'user','content':'Pergunta antiga fixture-chave-opaca'},
                   {'role':'assistant','content':'Resposta antiga'}]
        anterior=copy.deepcopy(historico)
        self.retornar({'choices':[{'message':{'content':'Resposta útil.','tool_calls':[{'function':{'name':'powershell'}}]}}]})
        texto=nove.responder('Pergunta nova fixture-chave-opaca',historico)
        pedido=self.cliente.open.call_args.args[0]
        body=json.loads(pedido.data)
        self.assertEqual(pedido.full_url,nove.URL_PADRAO+'/chat/completions')
        self.assertEqual(pedido.method,'POST');self.assertEqual(body['model'],'Minha Equipe')
        self.assertFalse(body['stream']);self.assertEqual(body['max_tokens'],800)
        self.assertEqual(len(body['messages']),4)
        self.assertEqual(body['messages'][-1]['role'],'user')
        self.assertNotIn('fixture-chave-opaca',str(body));self.assertNotIn('ignorar regras',str(body))
        self.assertEqual(historico,anterior);self.assertEqual(texto,'Resposta útil.')
        self.cliente.open.assert_called_once()

    def test_sem_texto_ou_somente_ferramenta_falha_sem_execucao(self):
        for obj in ({},{'choices':[]},{'choices':[None]},{'choices':[{'message':None}]},
                    {'choices':[{'message':{'content':None,'tool_calls':[{'function':{'name':'execute'}}]}}]},
                    {'choices':[{'message':{'content':['nao-e-texto']}}]}):
            with self.subTest(obj=obj):
                self.cliente.reset_mock();self.retornar(obj)
                self.erro('resposta_invalida',nove.responder,'Pergunta')
                self.cliente.open.assert_called_once()

    def test_pedido_ate_12000_preservado_inteiro_antes_de_reduzir_historico(self):
        pedido='x'*11920+' ULTIMO PEDIDO COMPLETO NAO EXECUTE'
        historico=[{'role':'user','content':'antigo '*3000} for _ in range(3)]
        self.retornar({'choices':[{'message':{'content':'Resposta de fixture.'}}]})
        nove.responder(pedido,historico)
        mensagens=json.loads(self.cliente.open.call_args.args[0].data)['messages']
        self.assertEqual(mensagens[-1],{'role':'user','content':pedido})
        self.assertLessEqual(sum(len(m['content']) for m in mensagens[1:]),24000)

    def test_pergunta_e_historico_invalidos_nao_enviam(self):
        for texto in ('',' '*3,None,True,{},'x'*12001):
            with self.subTest(texto=str(texto)[:20]),self.assertRaises(ValueError):nove.responder(texto)
        for historico in ({},'nao-e-lista',True):
            with self.subTest(historico=historico),self.assertRaises(ValueError):nove.responder('Pergunta',historico)
        self.build.assert_not_called()

    def test_texto_redigido_antes_do_corte_e_limite_final(self):
        resposta='x'*11990+'fixture-chave-opaca'+' fim'*100
        self.retornar({'choices':[{'message':{'content':resposta}}]})
        texto=nove.responder('Pergunta')
        self.assertEqual(len(texto),12000)
        self.assertNotIn('fixture-chave-opaca',texto)
        self.assertIn('[CREDENCI',texto)

    def test_erros_http_preservam_categoria_retry_e_redacao_sem_retry(self):
        for codigo,categoria in ((400,'requisicao_invalida'),(401,'autenticacao'),(403,'autenticacao'),
                                 (404,'modelo_indisponivel'),(429,'limite_temporario'),(503,'servidor_ocupado')):
            with self.subTest(codigo=codigo):
                corpo=BytesIO(json.dumps({'error':{'message':'Falha fixture-chave-opaca'}}).encode())
                erro=urllib.error.HTTPError(nove.URL_PADRAO,codigo,'fixture',{'Retry-After':'12'},corpo)
                self.cliente.reset_mock();self.cliente.open.side_effect=erro
                exc=self.erro(categoria,nove.responder,'Pergunta')
                self.assertEqual(exc.codigo,codigo);self.assertEqual(exc.retry_after,12)
                self.assertNotIn('fixture-chave-opaca',str(exc));self.assertTrue(corpo.closed)
                self.cliente.open.assert_called_once()

    def test_timeout_e_rede_nao_repetem_nem_afirmam_cancelamento(self):
        for erro,categoria in ((TimeoutError('fixture-chave-opaca'),'tempo_esgotado'),
                               (urllib.error.URLError(TimeoutError('expirou')),'tempo_esgotado'),
                               (urllib.error.URLError('fixture-chave-opaca'),'rede')):
            self.cliente.reset_mock();self.cliente.open.side_effect=erro
            exc=self.erro(categoria,nove.responder,'Pergunta')
            self.assertNotIn('fixture-chave-opaca',str(exc))
            if categoria=='tempo_esgotado':self.assertIn('não comprova cancelamento',str(exc))
            self.cliente.open.assert_called_once()


class Servidor9Router(BaseHTTPRequestHandler):
    chamadas=[]
    redirecionar=False
    def log_message(self,*args):pass
    def do_GET(self):
        self.chamadas.append((self.path,self.headers.get('Authorization'),None))
        if self.redirecionar:
            self.send_response(302);self.send_header('Location','http://127.0.0.1:1/nao-enviar');self.end_headers();return
        self.responder({'data':[{'id':'Combo Teste','owned_by':'combo'}]})
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.chamadas.append((self.path,self.headers.get('Authorization'),body))
        self.responder({'choices':[{'message':{'content':'Resposta de protocolo simulada.'}}]})
    def responder(self,obj):
        body=json.dumps(obj).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)


class Protocolo9Router(unittest.TestCase):
    def setUp(self):
        Servidor9Router.chamadas=[];Servidor9Router.redirecionar=False
        self.servidor=ThreadingHTTPServer(('127.0.0.1',0),Servidor9Router)
        threading.Thread(target=self.servidor.serve_forever,daemon=True).start()
        self.addCleanup(self.servidor.server_close);self.addCleanup(self.servidor.shutdown)
        p=patch.dict(os.environ,{'NINE_ROUTER_HABILITADO':'1',
             'NINE_ROUTER_URL':f'http://127.0.0.1:{self.servidor.server_port}/v1',
             'NINE_ROUTER_MODEL':'Combo Teste','NINE_ROUTER_API_KEY':'fixture-key',
             'HTTP_PROXY':'http://127.0.0.1:1','HTTPS_PROXY':'http://127.0.0.1:1',
             'ALL_PROXY':'http://127.0.0.1:1'},clear=True)
        p.start();self.addCleanup(p.stop)

    def test_fluxo_real_loopback_ignora_proxies_do_ambiente(self):
        self.assertEqual(nove.listar_modelos()['modelos'][0]['id'],'Combo Teste')
        self.assertEqual(nove.responder('Pergunta de fixture'),'Resposta de protocolo simulada.')
        self.assertEqual([c[0] for c in Servidor9Router.chamadas],['/v1/models','/v1/chat/completions'])
        self.assertTrue(all(c[1]=='Bearer fixture-key' for c in Servidor9Router.chamadas))
        self.assertEqual(Servidor9Router.chamadas[-1][2]['model'],'Combo Teste')

    def test_redirect_http_real_nao_encaminha_chave(self):
        Servidor9Router.redirecionar=True
        with self.assertRaises(FalhaAPI) as cm:nove.listar_modelos()
        self.assertEqual(cm.exception.categoria,'configuracao')
        self.assertEqual(len(Servidor9Router.chamadas),1)
        self.assertNotIn('fixture-key',str(cm.exception))


if __name__=='__main__':unittest.main()
