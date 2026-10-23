"""Callbacks e confirmações simulados, sem conexão ao Telegram ou Windows."""
import os
import tempfile
import nucleo
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app


class TelegramConfirmacoes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.data_patch=patch.object(nucleo,'DADOS',Path(self.tmp.name));self.data_patch.start();self.addCleanup(self.data_patch.stop)
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':0},'habitos_saude':{}})
        self.bot=MagicMock()
        self.bot.message_handler.side_effect=lambda **kwargs:lambda fn:fn
        def registrar_callback(**kwargs):
            def registrar(fn):
                self.callback=fn
                return fn
            return registrar
        self.bot.callback_query_handler.side_effect=registrar_callback
        self.env=patch.dict(os.environ,{'TELEGRAM_TOKEN':'fixture-local','TELEGRAM_ALLOWED_USER_IDS':'1,2'})
        self.env.start();self.addCleanup(self.env.stop)
        self.bot_patch=patch.object(app,'BOT',None);self.bot_patch.start();self.addCleanup(self.bot_patch.stop)
        modulo=SimpleNamespace(TeleBot=MagicMock(return_value=self.bot))
        with patch.dict(sys.modules,{'telebot':modulo}),patch('configurar_telegram.validar_token',return_value=True):
            app.configurar_bot()
        self.pendentes=patch.object(app,'PENDENTES',{})
        self.pendentes.start();self.addCleanup(self.pendentes.stop)
        self.windows=patch.object(app,'CONFIRMACOES_WINDOWS',{})
        self.windows.start();self.addCleanup(self.windows.stop)

    def chamada(self,usuario=1,chat=10,tipo='ok'):
        return SimpleNamespace(id='callback',data=tipo+':pedido',from_user=SimpleNamespace(id=usuario),
                               message=SimpleNamespace(chat=SimpleNamespace(id=chat)))

    def criar_pedido(self):
        app.PENDENTES['pedido']={'user':1,'chat':10,'acao':'desktop','expira':time.monotonic()+90}

    def test_outro_dono_nao_consumira_confirmacao(self):
        self.criar_pedido()
        with patch.object(app,'executar',return_value='Solicitado') as executar:
            self.callback(self.chamada(usuario=2))
            executar.assert_not_called()
            self.assertIn('pedido',app.PENDENTES)
            self.callback(self.chamada())
            executar.assert_called_once_with('desktop')
            self.assertNotIn('pedido',app.PENDENTES)

    def test_chat_incorreto_nao_cancela_pedido(self):
        self.criar_pedido()
        with patch.object(app,'executar') as executar:
            self.callback(self.chamada(chat=20,tipo='cancelar'))
            self.assertIn('pedido',app.PENDENTES)
            self.callback(self.chamada(tipo='cancelar'))
            self.assertNotIn('pedido',app.PENDENTES)
            executar.assert_not_called()

    def test_confirmacao_nao_pode_ser_reutilizada(self):
        self.criar_pedido()
        with patch.object(app,'executar',return_value='Solicitado') as executar:
            self.callback(self.chamada())
            self.callback(self.chamada())
            executar.assert_called_once_with('desktop')

    def test_nao_autorizado_nao_consume_nem_executa(self):
        self.criar_pedido()
        with patch.object(app,'executar') as executar:
            self.callback(self.chamada(usuario=3))
            self.assertIn('pedido',app.PENDENTES)
            executar.assert_not_called()

    def test_equipe_paralela_telegram_autorizada_consulta_catalogo_e_conversa_com_quatro_modelos(self):
        modelos=['qwen3.8:27b','mistral:latest','llama3.2:latest','qwen3.5:4b']
        roteador=MagicMock()
        roteador.catalogo_ollama.return_value={'habilitado':True,'modelos':[{'nome':m,'nuvem':False} for m in modelos]}
        roteador.responder.side_effect=lambda texto,**opcoes:('Olá de '+opcoes['modelo_ollama'],'Ollama')
        with patch.object(app,'ROTEADOR',roteador):
            app.tratar_pedido(self.mensagem('/chat equipe paralelo',usuario=3))
            roteador.catalogo_ollama.assert_not_called()
            app.tratar_pedido(self.mensagem('/chat equipe paralelo',topico=4))
            roteador.catalogo_ollama.assert_called_once_with()
            roteador.responder.assert_not_called()
            app.tratar_pedido(self.mensagem('Explique planejamento semanal',topico=4))
            self.assertEqual(roteador.responder.call_count,4)
            self.assertEqual({c.kwargs['modelo_ollama'] for c in roteador.responder.call_args_list},set(modelos))
            self.assertTrue(all(c.kwargs['provedor']=='Ollama' for c in roteador.responder.call_args_list))
            app.tratar_pedido(self.mensagem('/chat equipe off',topico=4))
            self.assertFalse(app.CENTRAL.obter_chat_ativo('1:10:4')['equipe_paralela'])

    def test_codigo_windows_invalido_preserva_confirmacao(self):
        app.CONFIRMACOES_WINDOWS[1]={'chat':10,'codigo':'123456','expira':time.monotonic()+90}
        mensagem=SimpleNamespace(chat=SimpleNamespace(id=10),from_user=SimpleNamespace(id=1),text='/confirmar_windows inválido')
        with patch.object(app,'reiniciar_windows',return_value='Simulado') as reiniciar:
            app.tratar_pedido(mensagem)
            reiniciar.assert_not_called()
            self.assertIn(1,app.CONFIRMACOES_WINDOWS)
            mensagem.text='/confirmar_windows 123456'
            app.tratar_pedido(mensagem)
            self.assertNotIn(1,app.CONFIRMACOES_WINDOWS)
            app.tratar_pedido(mensagem)
            reiniciar.assert_called_once_with()


    def mensagem(self,texto,usuario=1,chat=10,topico=None):
        return SimpleNamespace(chat=SimpleNamespace(id=chat),from_user=SimpleNamespace(id=usuario),text=texto,message_thread_id=topico)

    def test_chats_telegram_continuos_e_topicos_isolados(self):
        app.tratar_pedido(self.mensagem('/chat novo Projeto',topico=4))
        app.tratar_pedido(self.mensagem('/chat provedor Ollama',topico=4))
        app.tratar_pedido(self.mensagem('/chat modo on',topico=4))
        with patch.object(app.ROTEADOR,'responder',return_value=('Resposta simulada','Ollama')) as responder:
            app.tratar_pedido(self.mensagem('Minha pergunta',topico=4))
            self.assertEqual(responder.call_args.kwargs['provedor'],'Ollama')
            self.assertEqual(responder.call_args.kwargs['historico'],[])
            app.tratar_pedido(self.mensagem('Continuação',topico=4))
            self.assertEqual(len(responder.call_args.kwargs['historico']),2)
            app.CENTRAL.configurar_chat('1:10:5',app.CENTRAL.obter_chat_ativo('1:10:5')['id'],equipe_politica='manual')
            app.tratar_pedido(self.mensagem('/ia Outro tópico',topico=5))
            self.assertEqual(responder.call_args.kwargs['historico'],[])

    def test_conversa_comum_padrao_e_pedido_pc_confirmado_por_texto(self):
        catalogo=patch.object(app.ROTEADOR,'catalogo_ollama',return_value={'habilitado':True,'modelos':[{'nome':'llama3.2:latest','nuvem':False}]})
        catalogo.start();self.addCleanup(catalogo.stop)
        with patch.object(app.ROTEADOR,'responder',return_value=('Olá, como posso ajudar?','Ollama')) as ia,\
                patch.object(app,'executar',return_value='VS Code solicitado') as executar,patch.object(app,'inline',return_value=None):
            app.tratar_pedido(self.mensagem('Olá, me ajude a organizar o dia'))
            ia.assert_called_once()
            app.tratar_pedido(self.mensagem('abra o VS Code'))
            executar.assert_not_called()
            app.tratar_pedido(self.mensagem('sim',usuario=3));executar.assert_not_called()
            app.tratar_pedido(self.mensagem('sim',chat=11));executar.assert_not_called()
            app.tratar_pedido(self.mensagem('sim'))
            executar.assert_called_once_with('vscode_pc')
            app.tratar_pedido(self.mensagem('/chat modo off'))
            antes=ia.call_count
            app.tratar_pedido(self.mensagem('Vamos conversar mais'))
            self.assertEqual(ia.call_count,antes)

    def test_cancelamento_natural_e_confirmacao_outro_dono_nao_executam(self):
        with patch.object(app,'executar') as executar,patch.object(app,'inline',return_value=None),\
                patch.object(app.ROTEADOR,'responder',return_value=('Não há pedido seu para confirmar.','Ollama')):
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            app.tratar_pedido(self.mensagem('sim',usuario=2))
            executar.assert_not_called()
            app.tratar_pedido(self.mensagem('cancele'))
            self.assertFalse(app.PENDENTES);executar.assert_not_called()

    def test_pedido_natural_nao_executa_em_outra_conversa_telegram(self):
        with patch.object(app,'executar') as executar,patch.object(app,'inline',return_value=None):
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            token=next(iter(app.PENDENTES));app.tratar_pedido(self.mensagem('/chat novo Outra'))
            chamada=self.chamada();chamada.data='ok:'+token;self.callback(chamada)
            executar.assert_not_called()
            self.assertIn('outra conversa',self.bot.send_message.call_args.args[1])

    def test_novo_chat_nao_autorizado_nao_grava(self):
        app.tratar_pedido(self.mensagem('/chat novo Invasor',usuario=3))
        self.assertFalse((Path(self.tmp.name)/'colaboracao_chats.json').exists())

    def test_modelos_ollama_listagem_selecao_e_envio(self):
        catalogo={'modelos':[{'nome':'qwen3.5:4b','nuvem':False},
                             {'nome':'gemma4:31b-cloud','nuvem':True}],
                  'padrao':'qwen2.5:3b','habilitado':True}
        with patch.object(app.ROTEADOR,'catalogo_ollama',return_value=catalogo) as listar,\
                patch.object(app.ROTEADOR,'responder',return_value=('Resposta','Ollama')) as responder:
            app.tratar_pedido(self.mensagem('/modelos ollama',usuario=3))
            listar.assert_not_called()
            app.tratar_pedido(self.mensagem('/modelos ollama'))
            self.assertIn('gemma4:31b-cloud',self.bot.send_message.call_args.args[1])
            responder.assert_not_called()
            app.tratar_pedido(self.mensagem('/chat modelo qwen3.5:4b'))
            app.tratar_pedido(self.mensagem('/ia Explique o projeto'))
            self.assertEqual(responder.call_args.kwargs['modelo_ollama'],'qwen3.5:4b')
            app.tratar_pedido(self.mensagem('/chat modelo padrao'))
            app.tratar_pedido(self.mensagem('/ia Pergunta padrão'))
            self.assertNotIn('modelo_ollama',responder.call_args.kwargs)

    def test_modelos_preparar_e_testar_exige_autorizacao_e_confirmacao(self):
        catalogo={'modelos':[{'nome':'mistral:latest','nuvem':False},{'nome':'llama3.2:latest','nuvem':False}],
                  'padrao':'mistral:latest','habilitado':True}
        with patch.object(app.ROTEADOR,'catalogo_ollama',return_value=catalogo) as listar,\
                patch.object(app.ROTEADOR,'responder',return_value=('OK','Ollama')) as responder,\
                patch.object(app,'inline',return_value=None):
            app.tratar_pedido(self.mensagem('/modelos preparar mistral,llama3.2',usuario=3))
            listar.assert_not_called()
            app.tratar_pedido(self.mensagem('/modelos preparar mistral,llama3.2'))
            responder.assert_not_called()
            app.tratar_pedido(self.mensagem('/modelos testar mistral'))
            responder.assert_not_called()
            token=next(iter(app.PENDENTES));chamada=self.chamada();chamada.data='ok:'+token
            self.callback(chamada);self.callback(chamada)
            responder.assert_called_once_with('Responda somente OK.',provedor='Ollama',modelo_ollama='mistral:latest')

    def test_modelos_detalhes_nao_consulta_se_nao_autorizado(self):
        detalhes={'nome':'mistral','familia':'llama','parametros':'7.2B','quantizacao':'Q4_K_M',
                  'capacidades':['completion','tools'],'contexto_maximo':32768,'nuvem':False}
        with patch.object(app.ROTEADOR,'detalhes_ollama',return_value=detalhes) as consultar:
            app.tratar_pedido(self.mensagem('/modelos detalhes mistral',usuario=3))
            consultar.assert_not_called()
            app.tratar_pedido(self.mensagem('/modelos detalhes mistral'))
            consultar.assert_called_once_with('mistral')
            self.assertIn('32768',self.bot.send_message.call_args.args[1])
            self.assertIn('não é a janela ativa',self.bot.send_message.call_args.args[1])

    def test_equipe_modelos_telegram_confirma_nomes_e_objetivo(self):
        with patch.object(app,'inline',return_value=None),patch.object(app.SERVICOS,'executar_acao',return_value='Propostas') as executar:
            app.tratar_pedido(self.mensagem('/equipe modelos qwen3.5:4b,gemma4:31b-cloud | Revisar rotina'))
            executar.assert_not_called()
            token=next(iter(app.PENDENTES))
            chamada=self.chamada();chamada.data='ok:'+token
            self.callback(chamada)
            dados=executar.call_args.args[1]
            self.assertEqual(dados['modelos_ollama'],['qwen3.5:4b','gemma4:31b-cloud'])
            self.assertEqual(dados['provedores'],['Ollama'])
            self.assertEqual(dados['texto'],'Revisar rotina')

    def test_equipe_telegram_aguarda_confirmacao_e_nao_repete(self):
        with patch.object(app,'inline',return_value=None),patch.object(app.SERVICOS,'executar_acao',return_value='Propostas registradas') as executar:
            app.tratar_pedido(self.mensagem('/equipe Revisar função'))
            executar.assert_not_called()
            token=next(iter(app.PENDENTES))
            chamada=self.chamada();chamada.data='ok:'+token
            self.callback(chamada);self.callback(chamada)
            executar.assert_called_once()
            self.assertEqual(executar.call_args.args[0],'equipe_ia')
            self.assertEqual(executar.call_args.args[1]['confirmacao'],'CONSULTAR EQUIPE')

    def test_perfil_cpu_exige_dono_confirmacao_e_nao_repete(self):
        with patch.object(app,'inline',return_value=None),patch.object(app.SERVICOS,'executar_acao',return_value='Perfil aplicado') as executar:
            app.tratar_pedido(self.mensagem('/modelos perfil cpu',usuario=3))
            self.assertFalse(app.PENDENTES)
            app.tratar_pedido(self.mensagem('/modelos perfil cpu',topico=4))
            executar.assert_not_called()
            token=next(iter(app.PENDENTES))
            chamada=self.chamada(usuario=2);chamada.data='ok:'+token
            self.callback(chamada)
            executar.assert_not_called()
            self.assertIn(token,app.PENDENTES)
            chamada.from_user.id=1
            self.callback(chamada);self.callback(chamada)
            executar.assert_called_once()
            acao,dados,contexto,_=executar.call_args.args
            self.assertEqual(acao,'ollama_perfil')
            self.assertEqual(contexto,'1:10:4')
            self.assertEqual(dados['confirmacao'],'CONFIGURAR CPU')
            self.assertEqual(dados['perfil'],'cpu')
            self.assertEqual(dados['chat_id'],app.CENTRAL.obter_chat_ativo(contexto)['id'])

    def test_perfil_expirado_ou_cancelado_nao_altera_configuracao(self):
        with patch.object(app,'inline',return_value=None),patch.object(app.SERVICOS,'executar_acao') as executar:
            for tipo in ('cancelar','expirado'):
                app.PENDENTES.clear()
                app.tratar_pedido(self.mensagem('/modelos perfil padrao'))
                token=next(iter(app.PENDENTES))
                if tipo=='expirado':app.PENDENTES[token]['expira']=time.monotonic()-1
                chamada=self.chamada(tipo='cancelar' if tipo=='cancelar' else 'ok')
                chamada.data=chamada.data.partition(':')[0]+':'+token
                self.callback(chamada)
            executar.assert_not_called()

    def test_documento_nao_autorizado_nao_baixa(self):
        mensagem=self.mensagem('',usuario=3)
        mensagem.document=SimpleNamespace(file_name='proposta.md',file_size=10,file_id='id')
        app.importar_documento(mensagem)
        self.bot.download_file.assert_not_called()


if __name__=='__main__':unittest.main()
