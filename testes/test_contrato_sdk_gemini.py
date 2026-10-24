"""Contrato real do SDK com transporte HTTP fictício, nunca com a conta Google."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gemini_interactions as api

try:
    import httpx
    from google import genai
    SDK=True
except ImportError:SDK=False


@unittest.skipUnless(SDK,'Contrato exige google-genai>=2.9; instalado na matriz CI.')
class ContratoSDKGemini(unittest.TestCase):
    def setUp(self):
        self.req=[];self.status=200;self.excecao=None;self.resposta={'id':'fixture-interaction','status':'completed','steps':[{'type':'model_output','content':[{'type':'text','text':'OK'}]}]}
        # OpenSSL no Windows/Python 3.14 precisa dos diretórios do sistema
        # mesmo com HTTP fictício. Remover SYSTEMROOT pode impedir criar SSL.
        ambiente={n:v for n,v in os.environ.items() if n.upper() in {
            'SYSTEMROOT','WINDIR','SYSTEMDRIVE','PROGRAMDATA','USERPROFILE',
            'APPDATA','LOCALAPPDATA','TEMP','TMP'}}
        ambiente.update(GEMINI_API_KEY='fixture-chave',GEMINI_MODEL='gemini-3.8-flash')
        p=patch.dict(os.environ,ambiente,clear=True);p.start();self.addCleanup(p.stop)
        def transporte(req):
            self.req.append({'rota':req.url.path,'metodo':req.method,'body':json.loads(req.content) if req.content else None})
            if self.excecao:raise self.excecao
            return httpx.Response(self.status,json=self.resposta,request=req)
        fabrica=httpx.Client
        def cliente_ficticio(*args,**kwargs):
            kwargs['transport']=httpx.MockTransport(transporte)
            return fabrica(*args,**kwargs)
        p=patch.object(httpx,'Client',side_effect=cliente_ficticio);p.start();self.addCleanup(p.stop)

    def test_interactions_serializa_historico_e_store_false(self):
        self.assertEqual(api.responder('Pedido atual',[{'role':'assistant','content':'Resposta anterior'}]),'OK')
        self.assertEqual(len(self.req),1)
        body=self.req[0]['body'];self.assertIs(body['store'],False)
        self.assertEqual(body['input'][0]['type'],'model_output')
        self.assertEqual(body['input'][-1]['content'][0]['text'],'Pedido atual')
        self.assertEqual(self.req[0]['rota'],'/v1beta/interactions')

    def test_agente_serializa_background_store_e_sandbox_sem_rede(self):
        self.resposta.update(status='in_progress',environment_id='fixture-environment')
        tarefa=api.criar_tarefa('Proponha uma arquitetura.',confirmado=True)
        body=self.req[0]['body'];self.assertTrue(body['store']);self.assertTrue(body['background'])
        self.assertEqual(body['environment'],{'type':'remote','network':'disabled'})
        self.assertEqual(tarefa['ambiente_id'],'fixture-environment')

    def test_continuacao_envia_apenas_ids_explicitos_e_novo_pedido(self):
        api.criar_tarefa('Continue a proposta.',anterior={'remote_id':'fixture-anterior','ambiente_id':'fixture-environment'},confirmado=True)
        body=self.req[0]['body'];self.assertEqual(body['previous_interaction_id'],'fixture-anterior')
        self.assertEqual(body['environment']['environment_id'],'fixture-environment')
        self.assertNotIn('sources',body['environment'])

    def test_cancelamento_usa_endpoint_da_interacao(self):
        self.resposta['status']='cancelled'
        self.assertEqual(api.cancelar_tarefa('fixture-interaction',confirmado=True)['estado'],'cancelled')
        self.assertEqual(self.req[0]['rota'],'/v1beta/interactions/fixture-interaction/cancel')

    def test_sdk_nao_repete_criacao_429(self):
        self.status=429;self.resposta={'error':{'code':429,'message':'quota fixture-chave','status':'RESOURCE_EXHAUSTED'}}
        with self.assertRaises(Exception) as erro:api.criar_tarefa('Uma tarefa.',confirmado=True)
        self.assertEqual(len(self.req),1);self.assertNotIn('fixture-chave',str(erro.exception))

    def test_sdk_nao_repete_criacao_com_timeout_do_transporte(self):
        self.excecao=httpx.ReadTimeout('fixture-chave timed out')
        from multi_ia import FalhaAPI
        with self.assertRaises(FalhaAPI) as erro:api.criar_tarefa('Tarefa única.',confirmado=True)
        self.assertEqual(len(self.req),1)
        self.assertEqual(erro.exception.categoria,'tempo_esgotado')
        self.assertNotIn('fixture-chave',str(erro.exception))

    def test_perfil_usa_agents_create_oficial_sem_chave_no_sandbox(self):
        self.resposta={'id':'meucontrolepc-fixture'}
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(api.criar_perfil('meucontrolepc-fixture','Analise propostas.',confirmado=True),'meucontrolepc-fixture')
        self.assertEqual(self.req[0]['rota'],'/v1beta/agents')
        body=self.req[0]['body'];self.assertEqual(body['base_environment'],{'type':'remote','network':'disabled'})
        self.assertNotIn('fixture-chave',json.dumps(body))


if __name__=='__main__':unittest.main()
