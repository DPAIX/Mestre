"""Estado passivo em HTTP loopback real; Telegram e dados de uso não são acessados."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import assistente_pc as app
import nucleo
from saude_telegram import MonitorTelegram


class SaudeTelegramIntegracao(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.instante = 100.0
        self.monitor = MonitorTelegram(relogio=lambda: self.instante)
        for alvo, nome, valor in (
            (nucleo, 'DADOS', Path(self.tmp.name)),
            (app, 'SAUDE_TELEGRAM', self.monitor),
        ):
            contexto = patch.object(alvo, nome, valor)
            contexto.start()
            self.addCleanup(contexto.stop)
        nucleo.gravar_json('gestao_vida.json', {
            'rotina': [], 'financeiro': {'saldo': 0}, 'habitos_saude': {},
        })
        self.roteador = Mock()
        self.roteador.status.return_value = {}
        contexto = patch.object(app, 'ROTEADOR', self.roteador)
        contexto.start()
        self.addCleanup(contexto.stop)
        with patch.dict(os.environ, {'PAINEL_PORTA': '0'}):
            self.servidor = app.iniciar_painel()
        self.addCleanup(self.fechar)

    def fechar(self):
        self.servidor.shutdown()
        self.servidor.server_close()

    def consultar(self, token=None):
        conexao = http.client.HTTPConnection('127.0.0.1', self.servidor.server_port, timeout=3)
        try:
            conexao.request('GET', '/api/estado', headers={
                'X-Painel-Token': app.TOKEN_PAINEL if token is None else token,
            })
            resposta = conexao.getresponse()
            return resposta.status, json.loads(resposta.read())
        finally:
            conexao.close()

    def test_http_e_status_reutilizam_observacao_sem_nova_consulta(self):
        bot = Mock()
        bot.get_updates.return_value = []
        consulta_original = bot.get_updates
        self.monitor.iniciar()
        self.monitor.observar(bot)
        self.assertEqual(bot.get_updates(offset=7, timeout=15), [])
        self.instante += 4
        with patch('socket.create_connection', side_effect=AssertionError('Sem rede adicional.')):
            # O resumo usa apenas a evidência já observada, sem chamar Telegram.
            texto = app.mostrar_status()
        self.assertIn('Telegram', texto)
        codigo, estado = self.consultar()
        self.assertEqual(codigo, 200)
        self.assertEqual(estado['telegram']['estado'], 'consultando')
        self.assertEqual(estado['telegram']['ultima_consulta_ha_s'], 4)
        consulta_original.assert_called_once_with(offset=7, timeout=15)
        self.roteador.responder.assert_not_called()
        self.assertTrue({'vida', 'resumo', 'provedores', 'versao_estado'}.issubset(estado))

    def test_http_nao_autorizado_nao_revela_estado(self):
        self.monitor.somente_painel()
        codigo, estado = self.consultar(token='invalido')
        self.assertEqual(codigo, 403)
        self.assertNotIn('telegram', estado)

    def test_http_distingue_somente_painel_e_evidencia_antiga(self):
        self.monitor.somente_painel()
        self.assertEqual(self.consultar()[1]['telegram']['estado'], 'somente_painel')
        self.monitor.iniciar()
        bot = Mock()
        bot.get_updates.return_value = []
        consulta_original = bot.get_updates
        self.monitor.observar(bot)
        bot.get_updates()
        self.instante += 91
        estado = self.consultar()[1]['telegram']
        self.assertEqual(estado['estado'], 'sem_confirmacao_recente')
        self.assertEqual(estado['ultima_consulta_ha_s'], 91)
        consulta_original.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
