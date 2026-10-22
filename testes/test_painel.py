import json
import os
import re
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError
from urllib.request import Request,urlopen
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import assistente_pc as app

class PainelTeste(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.data_patch=patch.object(nucleo,'DADOS',Path(cls.tmp.name));cls.data_patch.start()
        # Function imports still refer to the original nucleo globals, patched above.
        nucleo.gravar_json('gestao_vida.json',{'rotina':[{'id':'r1','status':'Pendente','atividade':'Teste'}],
            'financeiro':{'saldo':10,'custo_unitario_ru':6},'habitos_saude':{}})
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.port_patch=patch.dict(os.environ,{'PAINEL_PORTA':str(cls.port)});cls.port_patch.start()
        cls.servidor=app.iniciar_painel()
        cls.url='http://127.0.0.1:'+str(cls.port)
    @classmethod
    def tearDownClass(cls):
        cls.servidor.shutdown();cls.servidor.server_close()
        cls.port_patch.stop();cls.data_patch.stop();cls.tmp.cleanup()
    def test_html_sem_tokens_antigos(self):
        with urlopen(self.url+'/') as resposta:
            html=resposta.read().decode('utf-8')
            self.assertIn('MeuControlePC',html)
            self.assertNotIn('__PAINEL_TOKEN__',html)
            self.assertNotIn('sk-proj-',html)
    def test_sem_token_bloqueado(self):
        with self.assertRaises(HTTPError) as exc:urlopen(self.url+'/api/estado')
        with exc.exception as resposta:self.assertEqual(resposta.code,403)
    def test_estado_autorizado(self):
        req=Request(self.url+'/api/estado',headers={'X-Painel-Token':app.TOKEN_PAINEL})
        with urlopen(req) as resposta:
            obj=json.loads(resposta.read())
        self.assertIn('resumo',obj)
    def test_post_origem_obrigatoria(self):
        req=Request(self.url+'/api/acao',data=b'{"acao":"agua"}',headers={'X-Painel-Token':app.TOKEN_PAINEL,'Content-Type':'application/json'},method='POST')
        with self.assertRaises(HTTPError) as exc:urlopen(req)
        with exc.exception as resposta:self.assertEqual(resposta.code,403)
    def test_post_real(self):
        req=Request(self.url+'/api/acao',data=b'{"acao":"agua"}',
            headers={'X-Painel-Token':app.TOKEN_PAINEL,'Content-Type':'application/json','Origin':self.url},method='POST')
        with urlopen(req) as resposta:obj=json.load(resposta)
        self.assertTrue(obj['ok'])
        self.assertIn('Água:',obj['mensagem'])

    def test_equipe_http_autenticada_idempotente_e_snapshot(self):
        from idempotencia_painel import ControleAcoes
        modelos=['qwen3.8:27b','mistral:latest','llama3.2:latest','qwen3.5:4b']
        roteador=MagicMock()
        roteador.catalogo_ollama.return_value={'habilitado':True,'modelos':[{'nome':m,'nuvem':False} for m in modelos]}
        roteador.status.return_value={}
        chat=app.CENTRAL.obter_chat_ativo('painel')
        corpo=json.dumps({'acao':'chat_equipe','ativo':True,'id':chat['id']}).encode('utf-8')
        headers={'X-Painel-Token':app.TOKEN_PAINEL,'Content-Type':'application/json','Origin':self.url,
                 'X-Idempotency-Key':'equipe-http-fixture-0123456789','X-Estado-Versao':'0'}
        with patch.object(app,'ROTEADOR',roteador),patch.object(app,'CONTROLE_PAINEL',ControleAcoes()):
            req=Request(self.url+'/api/acao',data=corpo,headers={**headers,'X-Painel-Token':'inválido'},method='POST')
            with self.assertRaises(HTTPError) as erro:urlopen(req)
            with erro.exception as resposta:self.assertEqual(resposta.code,403)
            roteador.catalogo_ollama.assert_not_called()
            for _ in range(2):
                with urlopen(Request(self.url+'/api/acao',data=corpo,headers=headers,method='POST')) as resposta:
                    self.assertTrue(json.load(resposta)['ok'])
            roteador.catalogo_ollama.assert_called_once_with()
            roteador.responder.assert_not_called()
            with urlopen(Request(self.url+'/api/estado',headers={'X-Painel-Token':app.TOKEN_PAINEL})) as resposta:
                ativo=json.load(resposta)['colaboracao']['chat_ativo']
            self.assertTrue(ativo['equipe_paralela'])
            self.assertEqual(ativo['equipe_modelos'],modelos)

if __name__=='__main__':unittest.main()

# Novas rotas v2.1 testadas separadamente para não criar nenhum reinício real.
class PainelEvolucaoTeste(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.p=patch.object(nucleo,'DADOS',Path(cls.tmp.name));cls.p.start()
        for nome,conteudo in [('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':0},'habitos_saude':{}}),('minhas_macros.json',{}),('base_auto_aprendizado.json',{})]:
            nucleo.gravar_json(nome,conteudo)
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));cls.port=s.getsockname()[1]
        cls.env=patch.dict(os.environ,{'PAINEL_PORTA':str(cls.port)});cls.env.start()
        cls.server=app.iniciar_painel();cls.url=f'http://127.0.0.1:{cls.port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.env.stop();cls.p.stop();cls.tmp.cleanup()
    def post(self,params):
        data=json.dumps(params).encode('utf-8')
        req=Request(self.url+'/api/acao',data=data,headers={'X-Painel-Token':app.TOKEN_PAINEL,'Content-Type':'application/json','Origin':self.url},method='POST')
        with urlopen(req) as r:return json.load(r)
    def test_nova_analise(self):
        v=self.post({'acao':'autoanalise'})
        self.assertTrue(v['ok'])
        self.assertIn('Autoanálise',v['mensagem'])
    def test_reinicio_win_nao_habilitado(self):
        with patch.dict(os.environ,{'REINICIO_WINDOWS_HABILITADO':'0'}),patch('reinicio_seguro.os.name','nt'),patch('reinicio_seguro.subprocess.run') as run:
            with self.assertRaises(HTTPError) as e:self.post({'acao':'reiniciar_windows','confirmacao':'REINICIAR WINDOWS'})
            with e.exception as resposta:self.assertEqual(resposta.code,400)
            run.assert_not_called()
    def test_reinicio_win_sem_frase(self):
        with self.assertRaises(HTTPError) as e:self.post({'acao':'reiniciar_windows','confirmacao':'sim'})
        with e.exception as resposta:self.assertEqual(resposta.code,400)
    def test_melhorias_sem_frase(self):
        with self.assertRaises(HTTPError) as e:self.post({'acao':'melhorias','confirmacao':'sim'})
        with e.exception as resposta:self.assertEqual(resposta.code,400)
