"""Regressões da auditoria: sockets locais limitados, mocks e JSON temporários."""
from __future__ import annotations

import http.client
import json
import os
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multi_ia
import nucleo
with patch.object(multi_ia, 'ler_json', return_value={}):
    import assistente_pc as app
from idempotencia_painel import ControleAcoes


class AuditoriaV250Teste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dados = Path(self.tmp.name)
        for modulo, nome, valor in (
                (nucleo, 'DADOS', self.dados),
                (app, 'CONTROLE_PAINEL', ControleAcoes()),
                (app, 'POMODOROS_ATIVOS', set()),
                (app, 'BOT', MagicMock())):
            alteracao = patch.object(modulo, nome, valor)
            alteracao.start(); self.addCleanup(alteracao.stop)

    def servidor(self, *, timeout=0.15, capacidade=16):
        for alvo, nome, valor in (
                (app.PainelHandler, 'timeout_conexao', timeout),
                (app.ServidorPainel, 'max_conexoes', capacidade)):
            alteracao = patch.object(alvo, nome, valor)
            alteracao.start(); self.addCleanup(alteracao.stop)
        servidor = app.ServidorPainel(('127.0.0.1', 0), app.PainelHandler)
        thread = threading.Thread(target=servidor.serve_forever, daemon=True)
        thread.start()

        def encerrar():
            servidor.shutdown()
            servidor.server_close()
            thread.join(2)
        self.addCleanup(encerrar)
        return servidor

    @staticmethod
    def cabecalho(servidor, tamanho):
        host = '127.0.0.1:' + str(servidor.server_port)
        return ('POST /api/acao HTTP/1.1\r\nHost: ' + host +
                '\r\nOrigin: http://' + host + '\r\nX-Painel-Token: ' + app.TOKEN_PAINEL +
                '\r\nContent-Type: application/json\r\nContent-Length: ' + str(tamanho) +
                '\r\n\r\n').encode('ascii')

    def verificar_encerramento(self, servidor, pedido, *, fim_escrita=False):
        with socket.create_connection(servidor.server_address, timeout=1) as cliente:
            cliente.settimeout(0.8)
            cliente.sendall(pedido)
            if fim_escrita:
                cliente.shutdown(socket.SHUT_WR)
            try:
                resposta = cliente.recv(4096)
            except socket.timeout:
                self.fail('A conexão incompleta permaneceu aguardando dados sem limite.')
            if resposta:
                codigo = int(resposta.split(b' ', 2)[1])
                self.assertGreaterEqual(codigo, 400)
                self.assertLess(codigo, 500)

    def test_request_line_incompleta_nao_mantem_thread_indefinidamente(self):
        servidor = self.servidor()
        self.verificar_encerramento(servidor, b'GET /')

    def test_corpo_incompleto_com_conexao_aberta_expira_sem_executar(self):
        servidor = self.servidor()
        with patch.object(app, 'registrar_agua') as executar:
            self.verificar_encerramento(servidor, self.cabecalho(servidor, 100) + b'{"acao":')
        executar.assert_not_called()

    def test_eof_antes_content_length_nao_aceita_json_truncado_valido(self):
        servidor = self.servidor()
        corpo = b'{"acao":"agua"}'
        with patch.object(app, 'registrar_agua', return_value=(1, 8)) as executar:
            self.verificar_encerramento(servidor, self.cabecalho(servidor, len(corpo) + 5) + corpo,
                                    fim_escrita=True)
        executar.assert_not_called()

    def test_conexoes_excedentes_nao_criam_workers_sem_limite(self):
        servidor = self.servidor(timeout=2, capacidade=2)
        clientes = []
        try:
            for _ in range(2):
                cliente = socket.create_connection(servidor.server_address, timeout=1)
                cliente.sendall(b'GET /')
                clientes.append(cliente)
            with socket.create_connection(servidor.server_address, timeout=1) as excedente:
                excedente.settimeout(0.8)
                try:
                    resposta = excedente.recv(4096)
                except socket.timeout:
                    self.fail('A conexão excedente foi mantida como um worker adicional.')
                if resposta:
                    self.assertIn(resposta.split(b' ', 2)[1], (b'429', b'503'))
        finally:
            for cliente in clientes:
                cliente.close()

    def test_json_chaves_duplicadas_e_numeros_nao_finitos_rejeitados_antes_acao(self):
        servidor = self.servidor(timeout=2)
        host = '127.0.0.1:' + str(servidor.server_port)
        corpos = (
            '{"acao":"agua","acao":"financeiro"}',
            '{"acao":"financeiro","valor":NaN}',
            '{"acao":"financeiro","valor":Infinity}',
            '{"acao":"financeiro","valor":-Infinity}',
            '{"acao":"financeiro","valor":1e9999}',
            '{"acao":"financeiro","valor":-1e9999}',
            '{"acao":"financeiro","valor":1,"valor":2}',
        )
        with patch.object(app.SERVICOS, 'executar_acao') as executar, \
                patch.object(app, 'registrar_agua') as agua:
            for corpo in corpos:
                with self.subTest(corpo=corpo):
                    cliente = http.client.HTTPConnection(*servidor.server_address, timeout=2)
                    try:
                        cliente.request('POST', '/api/acao', corpo.encode('utf-8'), headers={
                            'Host': host, 'Origin': 'http://' + host,
                            'X-Painel-Token': app.TOKEN_PAINEL, 'Content-Type': 'application/json'})
                        resposta = cliente.getresponse()
                        self.assertEqual(resposta.status, 400)
                        self.assertIn('erro', json.loads(resposta.read()))
                    finally:
                        cliente.close()
        executar.assert_not_called()
        agua.assert_not_called()

    def test_relatorio_campos_preferidos_nao_avaliam_fallback_inexistente(self):
        texto = app.texto_relatorio({
            'estado_local': 'OK', 'verificacoes_ok': 1, 'problemas_locais': [],
            'avisos_externos': [{'provedor': 'Ollama', 'detalhe': 'Fixture legível.'}],
            'falhas_recentes': 0, 'sugestoes': []})
        self.assertIn('OK', texto)
        self.assertIn('Ollama', texto)
        self.assertIn('Fixture legível.', texto)
        self.assertIsInstance(app.texto_relatorio({}), str)

    def test_pomodoro_falha_primeiro_envio_libera_chat_para_nova_tentativa(self):
        app.BOT.send_message.side_effect = RuntimeError('transporte fictício')
        with patch.object(app.threading, 'Thread') as thread:
            try:
                app.iniciar_pomodoro(123, 25, 5)
            except RuntimeError:
                pass
        self.assertNotIn(123, app.POMODOROS_ATIVOS)
        thread.return_value.start.assert_not_called()

    def test_pomodoro_falha_thread_start_libera_chat_para_nova_tentativa(self):
        with patch.object(app.threading, 'Thread') as thread:
            thread.return_value.start.side_effect = RuntimeError('worker fictício não iniciou')
            try:
                app.iniciar_pomodoro(123, 25, 5)
            except RuntimeError:
                pass
        thread.return_value.start.assert_called_once()
        self.assertNotIn(123, app.POMODOROS_ATIVOS)

    def test_vida_com_estrutura_invalida_gera_erro_controlado_e_preserva_arquivo(self):
        caminho = self.dados / 'gestao_vida.json'
        invalidos = ([], False, 'fixture', {'rotina': {}}, {'rotina': ['fixture']},
                     {'financeiro': []}, {'kanban': []}, {'habitos_saude': []})
        for valor in invalidos:
            with self.subTest(valor=valor):
                original = json.dumps(valor).encode('utf-8')
                caminho.write_bytes(original)
                with self.assertRaises(ValueError):
                    nucleo.vida()
                self.assertEqual(caminho.read_bytes(), original)

    def configurar_bot_ficticio(self):
        handlers = {}
        bot = MagicMock()

        def registrar_mensagem(**opcoes):
            def registrar(funcao):
                for tipo in opcoes.get('content_types', []):
                    handlers[tipo] = funcao
                return funcao
            return registrar

        def registrar_callback(**opcoes):
            def registrar(funcao):
                handlers['callback'] = funcao
                return funcao
            return registrar

        bot.message_handler.side_effect = registrar_mensagem
        bot.callback_query_handler.side_effect = registrar_callback
        telebot = ModuleType('telebot')
        telebot.TeleBot = MagicMock(return_value=bot)
        ambiente = patch.dict(os.environ, {
            'TELEGRAM_TOKEN': '123456789:' + 'X' * 35,
            'TELEGRAM_ALLOWED_USER_IDS': '11', 'GEMINI_API_KEY': 'fixture-genai'}, clear=True)
        ambiente.start(); self.addCleanup(ambiente.stop)
        with patch.dict(sys.modules, {'telebot': telebot}):
            app.configurar_bot()
        return bot, handlers

    def test_voz_falha_geracao_fecha_cliente_sem_upload_ou_temporario(self):
        bot, handlers = self.configurar_bot_ficticio()
        bot.get_file.return_value = SimpleNamespace(file_path='fixture/audio.ogg')
        bot.download_file.return_value = b'audio-ficticio'
        google = ModuleType('google')
        genai = ModuleType('google.genai')
        google.genai = genai
        genai.Client = MagicMock()
        genai.Client.return_value.models.generate_content.side_effect = RuntimeError('Falha fictícia na transcrição.')
        mensagem = SimpleNamespace(
            from_user=SimpleNamespace(id=11), chat=SimpleNamespace(id=22),
            voice=SimpleNamespace(file_id='fixture', file_size=13), audio=None)
        roteador = MagicMock()
        roteador.estado_local.return_value = {'Gemini': {'configurado': True, 'em_pausa': False}}
        with patch.dict(sys.modules, {'google': google, 'google.genai': genai}), \
                patch.object(app, 'ROTEADOR', roteador), \
                patch('tempfile.NamedTemporaryFile') as temporario, \
                patch.object(app, 'responder_natural_telegram') as interpretar:
            handlers['voice'](mensagem)
        genai.Client.assert_called_once()
        self.assertGreater(genai.Client.call_args.kwargs['http_options']['timeout'], 0)
        genai.Client.return_value.close.assert_called_once_with()
        genai.Client.return_value.models.generate_content.assert_called_once()
        genai.Client.return_value.files.upload.assert_not_called()
        temporario.assert_not_called()
        interpretar.assert_not_called()
        self.assertIn('Transcrição não concluída', bot.send_message.call_args.args[1])

    def test_callback_ack_expirado_nao_transforma_acao_executada_em_falha(self):
        bot, handlers = self.configurar_bot_ficticio()
        eventos = []

        def falhar_ack(*args, **kwargs):
            eventos.append('ack')
            raise RuntimeError('Callback fixture expirado.')

        def executar_ficticio(acao):
            eventos.append('executar')
            return 'Desktop solicitado com sucesso.'

        bot.answer_callback_query.side_effect = falhar_ack
        chamada = SimpleNamespace(
            id='fixture-callback', data='ok:fixture-pedido',
            from_user=SimpleNamespace(id=11), message=SimpleNamespace(chat=SimpleNamespace(id=22)))
        pedido = {'user': 11, 'chat': 22, 'acao': 'desktop', 'expira': time.monotonic() + 90}
        with patch.object(app, 'PENDENTES', {'fixture-pedido': pedido}), \
                patch.object(app, 'executar', side_effect=executar_ficticio) as executar, \
                patch.object(app, 'registrar') as registrar:
            handlers['callback'](chamada)
            executar.assert_called_once_with('desktop')
            self.assertEqual(eventos[:2], ['ack', 'executar'])
            self.assertNotIn('fixture-pedido', app.PENDENTES)
            bot.send_message.assert_called_once_with(22, 'Desktop solicitado com sucesso.')
            self.assertTrue(any(c.args[0] == 'callback_ack' for c in registrar.call_args_list))
            self.assertFalse(any(c.args[0] == 'callback' for c in registrar.call_args_list))
            handlers['callback'](chamada)
            executar.assert_called_once()


if __name__ == '__main__':
    unittest.main()
