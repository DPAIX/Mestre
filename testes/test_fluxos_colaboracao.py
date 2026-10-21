"""Fluxo HTTP completo com servidor local que simula o protocolo Ollama."""
import http.client
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from io import BytesIO
from zipfile import ZipFile
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import assistente_pc as app
import colaboracao_chats as central
import servicos_chat as servicos
from multi_ia import Roteador
from equipe_ia import consultar_equipe


class OllamaSimulado(BaseHTTPRequestHandler):
    pedidos=[]
    def log_message(self,*args):pass
    def do_POST(self):
        obj=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.pedidos.append(obj)
        corpo=json.dumps({'message':{'content':'Resposta simulada '+str(len(self.pedidos))}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(corpo)));self.end_headers();self.wfile.write(corpo)


class FluxosColaboracao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.p.start();self.addCleanup(self.p.stop)
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':10},'habitos_saude':{}})
        OllamaSimulado.pedidos=[]
        self.local=ThreadingHTTPServer(('127.0.0.1',0),OllamaSimulado)
        threading.Thread(target=self.local.serve_forever,daemon=True).start()
        self.addCleanup(self.local.server_close);self.addCleanup(self.local.shutdown)
        self.env=patch.dict(os.environ,{'PAINEL_PORTA':'0','GEMINI_API_KEY':'','GOOGLE_API_KEY':'','OPENAI_API_KEY':'','ANTHROPIC_API_KEY':'','EXA_API_KEY':'',
            'OLLAMA_HABILITADO':'1','OLLAMA_URL':f'http://127.0.0.1:{self.local.server_port}','OLLAMA_MODEL':'modelo-teste'})
        self.env.start();self.addCleanup(self.env.stop)
        self.roteador=Roteador();self.r=patch.object(app,'ROTEADOR',self.roteador);self.r.start();self.addCleanup(self.r.stop)
        self.painel=app.iniciar_painel();self.addCleanup(self.painel.server_close);self.addCleanup(self.painel.shutdown)
        self.port=self.painel.server_port

    def req(self,body=None,path='/api/acao',token=True):
        conn=http.client.HTTPConnection('127.0.0.1',self.port,timeout=8)
        self.addCleanup(conn.close)
        headers={'Content-Type':'application/json','Origin':f'http://127.0.0.1:{self.port}'}
        if token:headers['X-Painel-Token']=app.TOKEN_PAINEL
        conn.request('GET' if body is None else 'POST',path,json.dumps(body).encode() if body is not None else None,headers)
        resposta=conn.getresponse();data=resposta.read()
        return resposta.status,data if path=='/api/contexto' and resposta.status==200 else json.loads(data)

    def test_multiturno_isola_chats_com_fluxo_http_real(self):
        self.assertEqual(self.req({'acao':'chat_criar','titulo':'Primeiro','provedor':'Ollama'})[0],200)
        primeiro=central.obter_chat_ativo('painel')['id']
        segredo='contexto-'+uuid.uuid4().hex
        self.assertEqual(self.req({'acao':'pergunta','texto':segredo})[0],200)
        self.assertEqual(self.req({'acao':'pergunta','texto':'Continue a resposta anterior'})[0],200)
        payload=OllamaSimulado.pedidos[-1]['messages']
        self.assertTrue(any(m['content']==segredo for m in payload))
        self.assertEqual(self.req({'acao':'chat_criar','titulo':'Segundo','provedor':'Ollama'})[0],200)
        self.assertEqual(self.req({'acao':'pergunta','texto':'Outra conversa'})[0],200)
        self.assertFalse(any(m['content']==segredo for m in OllamaSimulado.pedidos[-1]['messages']))
        self.req({'acao':'chat_selecionar','id':primeiro})
        estado=self.req(path='/api/estado')[1]['colaboracao']
        self.assertEqual(len(estado['chat_ativo']['mensagens']),4)

    def test_equipe_exige_confirmacao_e_guarda_proposta(self):
        status,_=self.req({'acao':'equipe_ia','texto':'Criar teste'})
        self.assertEqual(status,400);self.assertEqual(OllamaSimulado.pedidos,[])
        status,res=self.req({'acao':'equipe_ia','texto':'Criar teste','confirmacao':'CONSULTAR EQUIPE'})
        self.assertEqual(status,200,res)
        self.assertEqual(len(OllamaSimulado.pedidos),1)
        self.assertEqual(len(central.estado_central('painel')['contribuicoes']),1)

    def test_exporte_nao_contem_historico_ou_arquivos_privados(self):
        privado='privado-'+uuid.uuid4().hex
        central.registrar_troca('painel',privado,'resposta','Ollama')
        (nucleo.DADOS/'nao_exportar.txt').write_text(privado)
        status,data=self.req(path='/api/contexto')
        self.assertEqual(status,200)
        with ZipFile(BytesIO(data)) as z:
            self.assertIn('prompts/chatgpt.md',z.namelist())
            self.assertFalse(any(n.startswith('dados/') for n in z.namelist()))
            self.assertFalse(any(privado.encode() in z.read(n) for n in z.namelist()))
        self.assertEqual(self.req(path='/api/contexto',token=False)[0],403)

    def test_verifica_conexao_ollama_sem_provar_saldo(self):
        status,res=self.req({'acao':'conexoes_ia','provedor':'Ollama','confirmacao':'TESTAR CONEXOES'})
        self.assertEqual(status,200,res)
        self.assertEqual(len(OllamaSimulado.pedidos),1)
        self.assertIn('não representa medição do saldo',res['mensagem'])

    def test_contribuicao_e_tarefa_funcionam_sem_ia(self):
        self.assertEqual(self.req({'acao':'tarefa_projeto','titulo':'Teste','descricao':'Revisar rota','papel':'revisao'})[0],200)
        tarefa=central.estado_central('painel')['tarefas'][0]['id']
        texto="__import__('pathlib').Path('EXECUCAO_INDEVIDA').touch()"
        self.assertEqual(self.req({'acao':'contribuicao_importar','origem':'Chat web','titulo':'Proposta','texto':texto,'tarefa_id':tarefa})[0],200)
        proposta=central.estado_central('painel')['contribuicoes'][0]
        self.assertEqual(self.req({'acao':'contribuicao_status','id':proposta['id'],'status':'aceita'})[0],200)
        self.assertFalse((nucleo.BASE/'EXECUCAO_INDEVIDA').exists())
        self.assertEqual(OllamaSimulado.pedidos,[])

    def test_troca_chat_durante_consulta_nao_mistura_respostas(self):
        a=central.criar_chat('ctx','A','Ollama')
        b=central.criar_chat('ctx','B','Ollama')
        central.selecionar_chat('ctx',a['id'])
        fake=MagicMock()
        def responder(*args,**kwargs):
            central.selecionar_chat('ctx',b['id']);return 'resposta-A','Ollama'
        fake.responder.side_effect=responder
        servicos.conversar('pergunta-A','ctx',fake)
        self.assertEqual(central.historico_chat('ctx',a['id'])[-1]['content'],'resposta-A')
        self.assertEqual(central.historico_chat('ctx',b['id']),[])

    def test_equipe_falha_parcial_nao_repete_chamadas(self):
        fake=MagicMock()
        fake.estado_local.return_value={n:{'configurado':True,'em_pausa':False} for n in ('Gemini','Claude')}
        def responder(*args,**kwargs):
            if kwargs['provedor']=='Claude':raise RuntimeError('indisponível')
            return 'proposta de implementação','Gemini'
        fake.responder.side_effect=responder
        resultado=consultar_equipe('Objetivo',fake,['Gemini','Claude'],confirmacao='CONSULTAR EQUIPE')
        self.assertEqual([r['ok'] for r in resultado['resultados']],[True,False])
        self.assertEqual(fake.responder.call_count,2)


if __name__=='__main__':unittest.main()
