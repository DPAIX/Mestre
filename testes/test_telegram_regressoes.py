"""Callbacks e confirmações simulados, sem conexão ao Telegram ou Windows."""
import os
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


if __name__=='__main__':unittest.main()
