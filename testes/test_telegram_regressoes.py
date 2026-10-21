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
            app.tratar_pedido(self.mensagem('/ia Outro tópico',topico=5))
            self.assertEqual(responder.call_args.kwargs['historico'],[])

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

    def test_documento_nao_autorizado_nao_baixa(self):
        mensagem=self.mensagem('',usuario=3)
        mensagem.document=SimpleNamespace(file_name='proposta.md',file_size=10,file_id='id')
        app.importar_documento(mensagem)
        self.bot.download_file.assert_not_called()


if __name__=='__main__':unittest.main()
