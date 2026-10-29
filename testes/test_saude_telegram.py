"""Recebimento Telegram fictício: nenhuma consulta, token ou mensagem real."""
import json
import contextlib
import io
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import saude_telegram as saude


class ErroAPI(Exception):
    def __init__(self, codigo):
        self.error_code = codigo
        super().__init__('URL e corpo privados não podem entrar no estado')


class SaudeTelegramTeste(unittest.TestCase):
    def setUp(self):
        self.relogio = Mock(return_value=100.0)
        self.monitor = saude.MonitorTelegram(relogio=self.relogio)

    def bot(self, retorno=None, erro=None):
        original = Mock(return_value=[] if retorno is None else retorno, side_effect=erro)
        bot = SimpleNamespace(get_updates=original)
        self.monitor.observar(bot)
        return bot, original

    def test_observar_e_snapshot_nao_chamam_cliente_ou_iniciam_bot(self):
        bot, original = self.bot()
        estado = self.monitor.snapshot()
        self.assertEqual(estado['estado'], 'nao_iniciado')
        self.assertIsNone(estado['ultima_consulta_ha_s'])
        self.assertEqual(estado['falhas_consecutivas'], 0)
        original.assert_not_called()
        self.assertEqual(set(estado), {'estado', 'detalhe', 'ultima_consulta_ha_s',
            'ultima_falha_ha_s', 'categoria', 'codigo_http', 'falhas_consecutivas'})

    def test_consulta_vazia_preserva_offset_parametros_e_retorno_original(self):
        resultado = []
        bot, original = self.bot(resultado)
        self.monitor.iniciar()
        self.assertIs(bot.get_updates(37, timeout=20, long_polling_timeout=15,
            allowed_updates=['message']), resultado)
        original.assert_called_once_with(37, timeout=20, long_polling_timeout=15,
            allowed_updates=['message'])
        estado = self.monitor.snapshot()
        self.assertEqual(estado['estado'], 'consultando')
        self.assertEqual(estado['ultima_consulta_ha_s'], 0)
        self.assertIn('entrega de respostas não verificada', estado['detalhe'])

    def test_updates_nao_sao_copiados_inspecionados_ou_reprocessados(self):
        resultado = object()
        bot, original = self.bot(resultado)
        self.monitor.iniciar()
        self.assertIs(bot.get_updates(offset=-1), resultado)
        original.assert_called_once_with(offset=-1)
        self.assertEqual(self.monitor.snapshot()['estado'], 'consultando')

    def test_instalacao_repetida_e_idempotente(self):
        bot, original = self.bot()
        wrapper = bot.get_updates
        self.monitor.observar(bot)
        self.monitor.observar(bot)
        self.assertIs(bot.get_updates, wrapper)
        self.monitor.iniciar()
        bot.get_updates(offset=11)
        original.assert_called_once_with(offset=11)
        self.assertEqual(self.relogio.call_count, 1)

    def test_outro_monitor_substitui_observador_sem_encadear_consultas(self):
        bot, original = self.bot()
        outro = saude.MonitorTelegram(relogio=self.relogio)
        self.monitor.iniciar()
        outro.iniciar()
        outro.observar(bot)
        bot.get_updates(offset=2)
        original.assert_called_once_with(offset=2)
        self.assertEqual(self.monitor.snapshot()['estado'], 'iniciando')
        self.assertEqual(outro.snapshot()['estado'], 'consultando')

    def test_erro_original_e_repassado_sem_tentativa_extra(self):
        erro = ErroAPI(503)
        bot, original = self.bot(erro=erro)
        self.monitor.iniciar()
        with self.assertRaises(ErroAPI) as recebido:
            bot.get_updates(offset=8)
        self.assertIs(recebido.exception, erro)
        original.assert_called_once_with(offset=8)
        estado = self.monitor.snapshot()
        self.assertEqual((estado['estado'], estado['categoria'], estado['codigo_http']),
            ('falha', 'servidor', 503))
        self.assertEqual(estado['falhas_consecutivas'], 1)
        self.assertEqual(estado['ultima_falha_ha_s'], 0)

    def test_recuperacao_zera_falhas_sem_apagar_idade_da_ultima_falha(self):
        bot, original = self.bot()
        self.monitor.iniciar()
        original.side_effect = [ErroAPI(502), TimeoutError(), []]
        for _ in range(2):
            with self.assertRaises(Exception):bot.get_updates(offset=5)
        self.assertEqual(self.monitor.snapshot()['falhas_consecutivas'], 2)
        self.relogio.return_value = 105.4
        self.assertEqual(bot.get_updates(offset=5), [])
        estado = self.monitor.snapshot()
        self.assertEqual((estado['estado'], estado['falhas_consecutivas']), ('consultando', 0))
        self.assertIsNone(estado['categoria'])
        self.assertIsNone(estado['codigo_http'])
        self.assertEqual(estado['ultima_falha_ha_s'], 5)
        self.assertEqual(original.call_count, 3)

    def test_evidencia_envelhece_sem_nova_consulta_ou_falha_inventada(self):
        bot, original = self.bot()
        self.monitor.iniciar();bot.get_updates()
        self.relogio.return_value = 190.0
        self.assertEqual(self.monitor.snapshot()['estado'], 'consultando')
        self.relogio.return_value = 190.01
        estado = self.monitor.snapshot()
        self.assertEqual(estado['estado'], 'sem_confirmacao_recente')
        self.assertEqual(estado['ultima_consulta_ha_s'], 90)
        self.assertEqual(estado['falhas_consecutivas'], 0)
        self.assertIsNone(estado['categoria'])
        original.assert_called_once_with()
        self.relogio.return_value = 191
        bot.get_updates()
        self.assertEqual(self.monitor.snapshot()['estado'], 'consultando')

    def test_modo_painel_e_nova_sessao_nao_reutilizam_sucesso_anterior(self):
        bot, original = self.bot()
        self.monitor.iniciar();bot.get_updates()
        self.monitor.somente_painel()
        estado = self.monitor.snapshot()
        self.assertEqual(estado['estado'], 'somente_painel')
        self.assertIsNone(estado['ultima_consulta_ha_s'])
        self.monitor.iniciar()
        self.assertEqual(self.monitor.snapshot()['estado'], 'iniciando')
        self.assertIsNone(self.monitor.snapshot()['ultima_consulta_ha_s'])
        original.assert_called_once_with()

    def test_encerramento_preserva_evidencia_e_nao_vira_recente(self):
        bot, original = self.bot()
        self.monitor.iniciar();bot.get_updates()
        self.relogio.return_value = 107
        self.monitor.encerrar()
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        self.assertEqual(self.monitor.snapshot()['ultima_consulta_ha_s'], 7)
        bot.get_updates()
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        self.assertEqual(original.call_count, 2)

    def test_resultado_em_andamento_nao_sobrescreve_encerramento(self):
        entrada, liberar = threading.Event(), threading.Event()
        def consultar():
            entrada.set()
            if not liberar.wait(2):raise AssertionError('Consulta fictícia não liberada.')
            return []
        bot, original = self.bot()
        original.side_effect = consultar
        self.monitor.iniciar()
        thread = threading.Thread(target=bot.get_updates)
        thread.start()
        try:
            self.assertTrue(entrada.wait(1))
            self.monitor.encerrar()
        finally:
            liberar.set();thread.join(2)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        self.assertIsNone(self.monitor.snapshot()['ultima_consulta_ha_s'])

    def test_falha_de_consulta_antiga_nao_contamina_nova_sessao(self):
        def consultar():
            self.monitor.iniciar()
            raise ErroAPI(401)
        bot, original = self.bot()
        original.side_effect = consultar
        self.monitor.iniciar()
        with self.assertRaises(ErroAPI):bot.get_updates()
        estado = self.monitor.snapshot()
        self.assertEqual(estado['estado'], 'iniciando')
        self.assertIsNone(estado['categoria'])
        self.assertEqual(estado['falhas_consecutivas'], 0)

    def test_classifica_codigos_da_api_sem_descricao_bruta(self):
        for codigo, categoria in ((401,'autenticacao'),(403,'autenticacao'),(409,'conflito'),
                (429,'limite'),(500,'servidor'),(502,'servidor'),(503,'servidor'),
                (400,'requisicao'),(404,'requisicao'),(200,'resposta_invalida')):
            with self.subTest(codigo=codigo):
                self.monitor.iniciar()
                bot, original = self.bot(erro=ErroAPI(codigo))
                with self.assertRaises(ErroAPI):bot.get_updates()
                estado = self.monitor.snapshot()
                self.assertEqual((estado['categoria'],estado['codigo_http']), (categoria,codigo))
                self.assertNotIn('URL e corpo privados', json.dumps(estado))

    def test_status_http_de_resposta_e_conservado_sem_ler_corpo(self):
        for atributo in ('result', 'response'):
            with self.subTest(atributo=atributo):
                erro = RuntimeError('fixture-privada')
                setattr(erro, atributo, SimpleNamespace(status_code=504, text='segredo'))
                self.monitor.iniciar()
                bot, _ = self.bot(erro=erro)
                with self.assertRaises(RuntimeError):bot.get_updates()
                estado = self.monitor.snapshot()
                self.assertEqual((estado['categoria'],estado['codigo_http']), ('servidor',504))
                self.assertNotIn('segredo', json.dumps(estado))

    def test_tipos_basicos_e_requests_sem_texto_ou_url(self):
        casos = [(TimeoutError(),'tempo_esgotado'),(ConnectionError(),'conexao'),
                 (ValueError(),'interna')]
        try:
            from requests.exceptions import Timeout, ConnectionError as ErroConexao
        except ImportError:
            pass
        else:
            casos.extend([(Timeout('segredo'),'tempo_esgotado'),(ErroConexao('segredo'),'conexao')])
        for erro, categoria in casos:
            with self.subTest(erro=type(erro).__name__):
                self.monitor.iniciar()
                bot, _ = self.bot(erro=erro)
                with self.assertRaises(type(erro)):bot.get_updates()
                estado = self.monitor.snapshot()
                self.assertEqual(estado['categoria'], categoria)
                self.assertIsNone(estado['codigo_http'])
                self.assertNotIn('segredo', json.dumps(estado))

    def test_excecao_com_str_inseguro_e_atributos_nao_numericos_nao_vaza(self):
        class ErroPrivado(Exception):
            error_code = '401-token-privado'
            def __str__(self):raise AssertionError('Exceção não pode ser convertida em texto.')
        erro = ErroPrivado({'token': 'fixture-privada'})
        self.monitor.iniciar()
        bot, _ = self.bot(erro=erro)
        with self.assertRaises(ErroPrivado) as recebido:bot.get_updates()
        self.assertIs(recebido.exception, erro)
        publico = json.dumps(self.monitor.snapshot())
        for privado in ('401-token-privado','fixture-privada','token'):
            self.assertNotIn(privado, publico)

    def test_snapshot_e_copia_sem_referencias_mutaveis(self):
        self.monitor.iniciar()
        estado = self.monitor.snapshot()
        estado['estado'] = 'online-inventado'
        self.assertEqual(self.monitor.snapshot()['estado'], 'iniciando')

    def test_concorrencia_preserva_contagem_e_snapshot_consistente(self):
        self.monitor.iniciar()
        bot, original = self.bot(erro=ErroAPI(409))
        erros = []
        def consultar():
            try:
                for _ in range(40):
                    try:bot.get_updates()
                    except ErroAPI:pass
                    estado = self.monitor.snapshot()
                    if (estado['estado'] != 'falha' or estado['categoria'] != 'conflito'
                            or estado['codigo_http'] != 409):
                        raise AssertionError('Snapshot contraditório.')
            except BaseException as erro:
                erros.append(erro)
        threads = [threading.Thread(target=consultar) for _ in range(6)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(2)
        self.assertFalse(any(thread.is_alive() for thread in threads))
        self.assertEqual(erros, [])
        self.assertEqual(self.monitor.snapshot()['falhas_consecutivas'], 240)
        self.assertEqual(original.call_count, 240)

    def test_contagem_publica_tem_limite_e_idade_nao_e_negativa(self):
        self.monitor.iniciar()
        bot, _ = self.bot(erro=ErroAPI(503))
        with patch.object(saude, '_LIMITE_CONTADOR', 3):
            for _ in range(5):
                with self.assertRaises(ErroAPI):bot.get_updates()
        self.relogio.return_value = 99
        self.assertEqual(self.monitor.snapshot()['falhas_consecutivas'], 3)
        self.assertEqual(self.monitor.snapshot()['ultima_falha_ha_s'], 0)


class SaudeTelegramInicioTeste(unittest.TestCase):
    def setUp(self):
        import assistente_pc as app
        self.app = app
        self.monitor = saude.MonitorTelegram(relogio=lambda:100)
        self.servidor = MagicMock()
        self.saida = io.StringIO()
        pilha = contextlib.ExitStack()
        self.addCleanup(pilha.close)
        pilha.enter_context(patch.dict(os.environ, {
            'TELEGRAM_TOKEN':'123456789:'+'X'*35,
            'TELEGRAM_ALLOWED_USER_IDS':'1',
        }, clear=True))
        pilha.enter_context(patch.object(app, 'SAUDE_TELEGRAM', self.monitor))
        pilha.enter_context(patch.object(app, 'BOT', None))
        pilha.enter_context(patch.object(app, 'iniciar_painel', return_value=self.servidor))
        pilha.enter_context(patch.object(app.threading, 'Thread'))
        pilha.enter_context(patch.object(app, 'catalogo_robotask'))
        pilha.enter_context(contextlib.redirect_stdout(self.saida))

    def test_bot_observa_consulta_existente_e_preserva_configuracao_do_polling(self):
        bot = MagicMock()
        consulta = bot.get_updates
        consulta.return_value = []
        bot.message_handler.side_effect = lambda **kw:lambda fn:fn
        bot.callback_query_handler.side_effect = lambda **kw:lambda fn:fn
        estados = []
        def polling(**kwargs):
            estados.append(self.monitor.snapshot()['estado'])
            bot.get_updates(offset=123, timeout=20, long_polling_timeout=15)
            estados.append(self.monitor.snapshot()['estado'])
        bot.infinity_polling.side_effect = polling
        with patch.dict(sys.modules, {'telebot':SimpleNamespace(TeleBot=Mock(return_value=bot))}):
            self.app._executar_instancia(SimpleNamespace(somente_painel=False))
        bot.infinity_polling.assert_called_once_with(timeout=20,long_polling_timeout=15,skip_pending=True)
        consulta.assert_called_once_with(offset=123,timeout=20,long_polling_timeout=15)
        self.assertEqual(estados, ['iniciando','consultando'])
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        self.servidor.shutdown.assert_called_once_with()
        self.servidor.server_close.assert_called_once_with()

    def test_somente_painel_fica_explicito_e_nao_configura_telegram(self):
        parada = Mock()
        estados = []
        def esperar(segundos):
            estados.append(self.monitor.snapshot()['estado'])
            return True
        parada.wait.side_effect = esperar
        with patch.object(self.app.threading, 'Event', return_value=parada), \
                patch.object(self.app, 'configurar_bot') as configurar:
            self.app._executar_instancia(SimpleNamespace(somente_painel=True))
        self.assertEqual(estados, ['somente_painel'])
        configurar.assert_not_called()
        parada.set.assert_called_once_with()
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')

    def test_excecao_do_polling_original_e_preservada_e_estado_encerrado(self):
        bot = MagicMock()
        erro = RuntimeError('Falha fictícia do cliente')
        bot.infinity_polling.side_effect = erro
        with patch.object(self.app, 'configurar_bot', return_value=bot), \
                self.assertRaises(RuntimeError) as recebido:
            self.app._executar_instancia(SimpleNamespace(somente_painel=False))
        self.assertIs(recebido.exception, erro)
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        self.servidor.shutdown.assert_called_once_with()
        self.servidor.server_close.assert_called_once_with()

    def test_falha_ao_abrir_painel_nao_deixa_recebimento_iniciando(self):
        with patch.object(self.app, 'iniciar_painel', side_effect=OSError('Porta fictícia ocupada')), \
                patch.object(self.app, 'configurar_bot') as configurar, \
                self.assertRaises(OSError):
            self.app._executar_instancia(SimpleNamespace(somente_painel=False))
        self.assertEqual(self.monitor.snapshot()['estado'], 'encerrado')
        configurar.assert_not_called()


if __name__ == '__main__':unittest.main()
