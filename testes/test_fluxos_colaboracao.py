"""Fluxo HTTP completo com servidor local que simula o protocolo Ollama."""
import http.client
import base64
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
    exibicoes=[]
    modelos=['qwen3.5:4b','gemma4:31b-cloud']
    def log_message(self,*args):pass
    def do_GET(self):
        corpo=json.dumps({'models':[{'name':nome} for nome in self.modelos]}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(corpo)));self.end_headers();self.wfile.write(corpo)
    def do_POST(self):
        obj=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        if self.path=='/api/show':
            self.exibicoes.append(obj)
            corpo=json.dumps({'details':{'family':'llama','parameter_size':'7.2B','quantization_level':'Q4_K_M'},
                              'capabilities':['completion','tools'],'model_info':{'llama.context_length':32768},
                              'template':'NAO_EXIBIR_TEMPLATE','system':'NAO_EXIBIR_SISTEMA'}).encode()
        else:
            self.pedidos.append(obj)
            corpo=json.dumps({'message':{'content':'Resposta simulada '+str(len(self.pedidos))}}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(corpo)));self.end_headers();self.wfile.write(corpo)


class FluxosColaboracao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.p=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.p.start();self.addCleanup(self.p.stop)
        self.pedidos=patch.object(app,'PEDIDOS_PAINEL',{});self.pedidos.start();self.addCleanup(self.pedidos.stop)
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':10},'habitos_saude':{}})
        OllamaSimulado.pedidos=[]
        OllamaSimulado.exibicoes=[]
        OllamaSimulado.modelos=['qwen3.5:4b','gemma4:31b-cloud']
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

    def test_pedido_natural_pc_so_executa_apos_confirmar_nonce_uma_vez(self):
        with patch.object(app,'executar',return_value='VS Code solicitado') as executar:
            status,res=self.req({'acao':'pergunta','texto':'abra o VS Code'})
            self.assertEqual(status,200,res);executar.assert_not_called()
            self.assertEqual(OllamaSimulado.pedidos,[])
            pedido=res['pedido']['id']
            status,res=self.req({'acao':'pedido_confirmar','id':pedido,'comando':'calc','campos':{'comando':'calc'}})
            self.assertEqual(status,200,res)
            executar.assert_called_once_with('vscode_pc')
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':pedido})[0],400)

    def test_cancelar_expirar_e_negar_token_nao_executam_pedido(self):
        with patch.object(app,'executar') as executar:
            pedido=self.req({'acao':'pergunta','texto':'abra a calculadora'})[1]['pedido']['id']
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':pedido},token=False)[0],403)
            self.assertEqual(self.req({'acao':'pedido_cancelar','id':pedido})[0],200)
            outro=self.req({'acao':'pergunta','texto':'abra a calculadora'})[1]['pedido']['id']
            app.PEDIDOS_PAINEL[outro]['expira']=0
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':outro})[0],400)
            executar.assert_not_called()

    def test_nonce_natural_vinculado_a_conversa_origem(self):
        with patch.object(app,'executar',return_value='Calculadora solicitada') as executar:
            origem=central.obter_chat_ativo('painel')['id']
            pedido=self.req({'acao':'pergunta','texto':'abra a calculadora'})[1]['pedido']['id']
            central.criar_chat('painel','Outro')
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':pedido})[0],400)
            executar.assert_not_called()
            central.selecionar_chat('painel',origem)
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':pedido})[0],200)
            executar.assert_called_once()

    def test_consulta_natural_real_sem_ia_e_acao_ia_flexivel_confirmada(self):
        with patch.object(app.ROTEADOR,'responder') as ia:
            status,res=self.req({'acao':'pergunta','texto':'qual meu saldo?'})
            self.assertEqual(status,200,res);self.assertIn('10.00',res['mensagem'])
            ia.assert_not_called()
            ia.return_value=(json.dumps({'resposta':'Posso registrar.','acao':'financeiro',
                                        'campos':{'tipo':'saida','valor':'2.50','descricao':'café'}}),'Ollama')
            status,res=self.req({'acao':'pergunta','texto':'Poderia lançar aquele café de dois reais e cinquenta?'})
            self.assertEqual(status,200,res);self.assertIn('pedido',res)
            self.assertEqual(nucleo.vida()['financeiro']['saldo'],10)
            self.assertEqual(self.req({'acao':'pedido_confirmar','id':res['pedido']['id']})[0],200)
            self.assertEqual(nucleo.vida()['financeiro']['saldo'],7.5)
            self.assertEqual(ia.call_count,1)
            self.assertIn('ÚLTIMA MENSAGEM',ia.call_args.args[0])

    def test_ia_acao_invalida_e_parametros_ausentes_nao_mudam_dados(self):
        antes=nucleo.vida()
        respostas=[{'resposta':'Preciso do valor e da descrição.','acao':'nenhuma','campos':{}},
                   {'resposta':'executar','acao':'shell','campos':{'cmd':'comando arbitrário'}}]
        with patch.object(app.ROTEADOR,'responder',side_effect=[(json.dumps(r),'Ollama') for r in respostas]):
            for texto in ('Registre um gasto','Aplique esta sugestão importada'):
                status,res=self.req({'acao':'pergunta','texto':texto})
                self.assertEqual(status,200,res);self.assertNotIn('pedido',res)
        self.assertEqual(nucleo.vida(),antes)

    def test_concluir_por_conversa_nao_reabre_atividade_ja_concluida(self):
        dados=nucleo.vida();dados['rotina']=[{'id':'r1','atividade':'Estudar','status':'Concluído'}]
        nucleo.gravar_json('gestao_vida.json',dados)
        status,res=self.req({'acao':'pergunta','texto':'conclua r1'})
        self.assertEqual(status,200,res)
        status,res=self.req({'acao':'pedido_confirmar','id':res['pedido']['id']})
        self.assertEqual(status,200,res)
        self.assertIn('já está concluída',res['mensagem'])
        self.assertEqual(nucleo.vida()['rotina'][0]['status'],'Concluído')

    def test_captura_natural_so_e_obtida_apos_confirmacao(self):
        # Sequência binária fictícia cujo base64 coincide com um padrão textual
        # de credencial; a imagem interna não pode ser corrompida pela redação.
        codificado='AAAAAIza'+'A'*24
        with patch.object(app,'captura',side_effect=lambda:BytesIO(base64.b64decode(codificado))) as foto:
            pedido=self.req({'acao':'pergunta','texto':'capture a tela'})[1]['pedido']['id'];foto.assert_not_called()
            status,res=self.req({'acao':'pedido_confirmar','id':pedido})
            self.assertEqual(status,200,res);foto.assert_called_once()
            self.assertEqual(res['imagem'],'data:image/png;base64,'+codificado)

    def test_modelo_padrao_salva_aplica_sem_gerar_e_libera_apenas_ollama(self):
        base=Path(self.tmp.name)/'instalacao';base.mkdir()
        env=base/'.env';env.write_text('OUTRA_CONFIG=preservada\nOLLAMA_MODEL=ausente\n',encoding='utf8')
        self.roteador.registrar_falha(__import__('multi_ia').FalhaAPI('Ollama',404,'ausente','modelo_indisponivel'))
        self.roteador.registrar_falha(__import__('multi_ia').FalhaAPI('OpenAI',429,'cota','sem_creditos'))
        with patch.object(nucleo,'BASE',base):
            status,res=self.req({'acao':'modelo_padrao','modelo':'qwen3.5:4b'})
        self.assertEqual(status,200,res);self.assertEqual(OllamaSimulado.pedidos,[])
        self.assertIn('OUTRA_CONFIG=preservada',env.read_text())
        self.assertIn('OLLAMA_MODEL=qwen3.5:4b',env.read_text())
        self.assertNotIn('Ollama',self.roteador.bloqueados);self.assertIn('OpenAI',self.roteador.bloqueados)
        self.assertEqual(central.obter_chat_ativo('painel')['provedor'],'Ollama')
        self.assertEqual(self.req({'acao':'pergunta','texto':'Olá, vamos conversar?'})[0],200)
        self.assertEqual(OllamaSimulado.pedidos[-1]['model'],'qwen3.5:4b')

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

    def test_catalogo_autenticado_nao_gera_respostas(self):
        with patch.object(app.ROTEADOR,'catalogo_ollama',wraps=app.ROTEADOR.catalogo_ollama) as catalogo:
            self.assertEqual(self.req(path='/api/modelos_ollama',token=False)[0],403)
            catalogo.assert_not_called()
            status,res=self.req(path='/api/modelos_ollama')
        self.assertEqual(status,200,res)
        self.assertEqual([(m['nome'],m['nuvem']) for m in res['modelos']],
                         [('qwen3.5:4b',False),('gemma4:31b-cloud',True)])
        self.assertEqual([m['familia'] for m in res['modelos']],['Qwen','Gemma'])
        self.assertEqual(OllamaSimulado.pedidos,[])

    def test_mistral_llama_qwen_preparados_sem_duplicar_com_geracao_real_do_protocolo(self):
        OllamaSimulado.modelos=['mistral:latest','llama3.2:latest','qwen3.8:27b']
        modelos=['mistral','llama3.2','qwen3.8:27b']
        status,res=self.req({'acao':'chats_modelos_ollama','modelos':modelos})
        self.assertEqual(status,200,res)
        self.assertEqual(OllamaSimulado.pedidos,[])
        estado=central.estado_central('painel')
        originais={c['modelo_ollama']:c['id'] for c in estado['chats']}
        self.assertEqual(set(originais),set(OllamaSimulado.modelos))
        self.assertEqual(estado['chat_ativo']['modelo_ollama'],'mistral:latest')
        self.req({'acao':'chats_modelos_ollama','modelos':modelos})
        self.assertEqual(len(central.listar_chats('painel')),3)
        for nome,chat_id in originais.items():
            self.req({'acao':'chat_selecionar','id':chat_id})
            self.assertEqual(self.req({'acao':'pergunta','texto':'Pergunta para '+nome})[0],200)
            self.assertEqual(OllamaSimulado.pedidos[-1]['model'],nome)
            self.assertEqual(len(central.historico_chat('painel',chat_id)),2)

    def test_detalhes_autenticados_sem_inferencia_nem_prompts(self):
        url='/api/modelo_ollama?nome=mistral%3Alatest'
        self.assertEqual(self.req(path=url,token=False)[0],403)
        self.assertEqual(OllamaSimulado.exibicoes,[])
        status,res=self.req(path=url)
        self.assertEqual(status,200,res)
        self.assertEqual(res['contexto_maximo'],32768)
        self.assertEqual(res['capacidades'],['completion','tools'])
        self.assertNotIn('NAO_EXIBIR',json.dumps(res))
        self.assertEqual(OllamaSimulado.pedidos,[])
        self.assertEqual(self.req(path='/api/modelo_ollama?nome=mistral&nome=outro')[0],400)

    def test_teste_modelo_exige_confirmacao_uma_chamada_sem_historico(self):
        central.registrar_troca('painel','HISTORICO_PRIVADO','resposta','Ollama')
        self.assertEqual(self.req({'acao':'modelo_testar','modelo':'qwen3.5:4b'})[0],400)
        self.assertEqual(OllamaSimulado.pedidos,[])
        status,res=self.req({'acao':'modelo_testar','modelo':'qwen3.5:4b','confirmacao':'TESTAR MODELO'})
        self.assertEqual(status,200,res)
        self.assertEqual(len(OllamaSimulado.pedidos),1)
        self.assertEqual(OllamaSimulado.pedidos[0]['model'],'qwen3.5:4b')
        self.assertNotIn('HISTORICO_PRIVADO',json.dumps(OllamaSimulado.pedidos))
        self.assertIn('não mede saldo',res['mensagem'])
        self.assertEqual(len(central.historico_chat('painel')),2)

    def test_modelo_por_conversa_e_historico_sem_mudar_padrao(self):
        a=central.criar_chat('painel','Código')
        status,res=self.req({'acao':'chat_modelo','id':a['id'],'modelo':'qwen3.5:4b'})
        self.assertEqual(status,200,res)
        self.assertEqual(self.req({'acao':'pergunta','texto':'Plano local'})[0],200)
        self.assertEqual(OllamaSimulado.pedidos[-1]['model'],'qwen3.5:4b')
        b=central.criar_chat('painel','Revisão')
        self.assertEqual(self.req({'acao':'chat_modelo','id':b['id'],'modelo':'gemma4:31b-cloud'})[0],200)
        self.req({'acao':'pergunta','texto':'Revisar proposta'})
        self.assertEqual(OllamaSimulado.pedidos[-1]['model'],'gemma4:31b-cloud')
        self.assertFalse(any(m['content']=='Plano local' for m in OllamaSimulado.pedidos[-1]['messages']))
        self.req({'acao':'chat_selecionar','id':a['id']})
        self.req({'acao':'pergunta','texto':'Continue'})
        self.assertEqual(OllamaSimulado.pedidos[-1]['model'],'qwen3.5:4b')
        self.assertTrue(any(m['content']=='Plano local' for m in OllamaSimulado.pedidos[-1]['messages']))
        self.assertEqual(central.obter_chat_ativo('painel')['mensagens'][-1]['modelo_ollama'],'qwen3.5:4b')
        self.assertNotEqual(os.environ.get('OLLAMA_MODEL'),'qwen3.5:4b')

    def test_modelo_ausente_ou_chat_alheio_nao_altera_chat(self):
        ativo=central.obter_chat_ativo('painel')
        self.assertEqual(self.req({'acao':'chat_modelo','modelo':'ausente:4b'})[0],400)
        self.assertEqual(central.obter_chat_ativo('painel'),ativo)
        outro=central.criar_chat('telegram:outro','Privado')
        with patch.object(app.ROTEADOR,'catalogo_ollama') as catalogo:
            self.assertEqual(self.req({'acao':'chat_modelo','id':outro['id'],'modelo':'qwen3.5:4b'})[0],400)
            catalogo.assert_not_called()
        self.assertEqual(OllamaSimulado.pedidos,[])

    def test_equipe_dois_modelos_ollama_uma_chamada_cada(self):
        status,res=self.req({'acao':'equipe_ia','texto':'Revisar atividade','provedores':['Ollama'],
                             'modelos_ollama':['qwen3.5:4b','gemma4:31b-cloud'],
                             'confirmacao':'CONSULTAR EQUIPE'})
        self.assertEqual(status,200,res)
        self.assertEqual(sorted(p['model'] for p in OllamaSimulado.pedidos),['gemma4:31b-cloud','qwen3.5:4b'])
        origens={p['origem'] for p in central.estado_central('painel')['contribuicoes']}
        self.assertEqual(origens,{'Ollama / qwen3.5:4b','Ollama / gemma4:31b-cloud'})

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
