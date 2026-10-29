"""Texto e áudio simulados usam a mesma origem e confirmação, sem ações reais."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import colaboracao_chats as central
import nucleo
from saude_telegram import MonitorTelegram
import voz_assistente as voz
from esclarecimento_conversa import GerenciadorEsclarecimentos


class TelegramNatural212(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.handlers = {}
        self.bot = MagicMock()
        def mensagem_handler(**opcoes):
            def registrar(funcao):
                for tipo in opcoes['content_types']:
                    self.handlers[tipo] = funcao
                return funcao
            return registrar
        def callback_handler(**opcoes):
            def registrar(funcao):
                self.callback = funcao
                return funcao
            return registrar
        self.bot.message_handler.side_effect = mensagem_handler
        self.bot.callback_query_handler.side_effect = callback_handler
        self.bot.get_file.return_value = SimpleNamespace(file_path='fixture/voz.ogg')
        self.bot.download_file.return_value = b'audio-ficticio'
        for alvo, nome, valor in (
            (nucleo, 'DADOS', Path(self.tmp.name)), (app, 'PENDENTES', {}),
            (app, 'BOT', None), (app, 'SAUDE_TELEGRAM', MonitorTelegram()),
            (app, 'ESCLARECIMENTOS', GerenciadorEsclarecimentos()),
        ):
            contexto = patch.object(alvo, nome, valor)
            contexto.start()
            self.addCleanup(contexto.stop)
        ambiente = patch.dict(os.environ, {
            'TELEGRAM_TOKEN': '123456789:'+'X'*35,
            'TELEGRAM_ALLOWED_USER_IDS': '1,2',
        }, clear=True)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        with patch.dict(sys.modules, {'telebot': SimpleNamespace(TeleBot=MagicMock(return_value=self.bot))}):
            app.configurar_bot()
        inline = patch.object(app, 'inline', return_value=None)
        inline.start()
        self.addCleanup(inline.stop)

    def mensagem(self, texto='', *, usuario=1, chat=10, topico=4, audio=False):
        return SimpleNamespace(text=None if audio else texto,
            from_user=SimpleNamespace(id=usuario), chat=SimpleNamespace(id=chat),
            message_thread_id=topico, audio=None,
            voice=SimpleNamespace(file_id='fixture', file_size=12) if audio else None)

    def ouvir(self, texto, **origem):
        mensagem = self.mensagem(audio=True, **origem)
        with patch.object(voz, 'verificar_disponibilidade_voz'), \
                patch.object(voz, 'transcrever_audio', return_value=texto):
            self.handlers['voice'](mensagem)
        return mensagem

    def test_texto_comum_nao_exige_comando(self):
        mensagem = self.mensagem('Preciso de ajuda para organizar meus estudos')
        with patch.object(app, 'responder_natural_telegram') as natural:
            self.handlers['text'](mensagem)
        natural.assert_called_once_with(mensagem, mensagem.text)

    def test_audio_preserva_origem_e_chama_mesmo_fluxo(self):
        with patch.object(app, 'responder_natural_telegram') as natural:
            mensagem = self.ouvir('Preciso de ajuda para organizar meus estudos')
        natural.assert_called_once_with(mensagem, 'Preciso de ajuda para organizar meus estudos')
        self.assertEqual(app.contexto_mensagem(mensagem), '1:10:4')
        self.assertIsNone(mensagem.text)

    def test_audio_sim_confirma_pedido_textual_uma_vez(self):
        with patch.object(app, 'executar', return_value='Calculadora solicitada') as executar:
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            executar.assert_not_called()
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('Sim, pode executar.')
            executar.assert_called_once_with('calc')
            self.assertFalse(app.PENDENTES)
            with patch.object(app, 'responder_natural_telegram'):
                self.ouvir('Sim, pode executar.')
            executar.assert_called_once_with('calc')

    def test_texto_sim_confirma_pedido_de_audio(self):
        with patch.object(app, 'executar', return_value='Editor solicitado') as executar:
            self.ouvir('abra o bloco de notas')
            executar.assert_not_called()
            app.tratar_pedido(self.mensagem('pode executar'))
        executar.assert_called_once_with('notepad')

    def test_audio_negativo_cancela_sem_execucao(self):
        with patch.object(app, 'executar') as executar:
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            self.ouvir('Não execute.')
        executar.assert_not_called()
        self.assertFalse(app.PENDENTES)
        self.assertIn('cancelado', self.bot.send_message.call_args.args[1])

    def test_audio_outro_usuario_ou_topico_nao_confirma(self):
        with patch.object(app, 'executar') as executar:
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            with patch.object(app, 'responder_natural_telegram'):
                self.ouvir('sim', usuario=2)
                self.ouvir('sim', topico=5)
            executar.assert_not_called()
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('sim')
        executar.assert_called_once_with('calc')

    def test_audio_nao_autorizado_nao_baixa_nem_transcreve(self):
        with patch.object(voz, 'verificar_disponibilidade_voz') as verificar, \
                patch.object(voz, 'transcrever_audio') as transcrever:
            self.handlers['voice'](self.mensagem(usuario=3, audio=True))
        self.bot.get_file.assert_not_called()
        self.bot.download_file.assert_not_called()
        verificar.assert_not_called()
        transcrever.assert_not_called()
        self.assertFalse(app.PENDENTES)

    def test_pausa_explicita_vale_para_texto_audio_e_retoma_por_fala(self):
        contexto = '1:10:4'
        atual = central.obter_chat_ativo(contexto)
        central.configurar_chat(contexto, atual['id'], modo_conversa=False)
        with patch.object(app.SERVICOS, 'conversar') as conversar:
            app.tratar_pedido(self.mensagem('Gostaria de conversar sobre meus estudos'))
            self.ouvir('Gostaria de conversar sobre meus estudos')
            conversar.assert_not_called()
            self.assertIn('volte a conversar', self.bot.send_message.call_args.args[1])
            self.ouvir('Volte a conversar.')
            conversar.assert_not_called()
            self.assertTrue(central.obter_chat_ativo(contexto)['modo_conversa'])
            mensagem = self.mensagem('Gostaria de conversar sobre meus estudos')
            with patch.object(app, 'responder_natural_telegram') as natural:
                app.tratar_pedido(mensagem)
                natural.assert_called_once_with(mensagem, mensagem.text)

    def test_frase_com_negacao_ou_outro_pedido_nao_confirma(self):
        with patch.object(app, 'executar') as executar:
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            with patch.object(app, 'responder_natural_telegram'):
                for texto in ('não, pode executar', 'sim, mas abra outra coisa', 'explique o que é execute'):
                    self.ouvir(texto)
            executar.assert_not_called()
            self.assertEqual(len(app.PENDENTES), 1)

    def test_pergunta_por_texto_completa_por_audio_e_confirma_sem_ia(self):
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Sem IA para esclarecer tarefa.')):
            app.tratar_pedido(self.mensagem('adicione uma tarefa'))
            self.assertIn('título', self.bot.send_message.call_args.args[1])
            self.assertFalse(app.PENDENTES)
            self.ouvir('Estudar cálculo')
            self.assertEqual(len(app.PENDENTES), 1)
            pendente = next(iter(app.PENDENTES.values()))
            self.assertEqual(pendente['dados']['plano']['campos']['texto'], 'Estudar cálculo')
            self.assertEqual(central.obter_chat_ativo('1:10:4')['id'], pendente['dados']['chat_id'])
            self.assertNotIn('Estudar cálculo', nucleo.vida().get('kanban', {}).get('A_Fazer', []))
            app.tratar_pedido(self.mensagem('sim'))
        self.assertIn('Estudar cálculo', nucleo.vida()['kanban']['A_Fazer'])
        self.assertFalse(app.PENDENTES)

    def test_pergunta_por_audio_completa_por_texto_cancelamento_por_audio(self):
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Sem IA para esclarecer tarefa.')):
            self.ouvir('adicione uma tarefa')
            self.assertFalse(app.PENDENTES)
            app.tratar_pedido(self.mensagem('Estudar física'))
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('Não.')
        self.assertFalse(app.PENDENTES)
        self.assertNotIn('Estudar física', nucleo.vida().get('kanban', {}).get('A_Fazer', []))

    def test_agendamento_da_captura_completa_por_audio_e_so_grava_apos_confirmar(self):
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Agendamento incompleto é local.')):
            app.tratar_pedido(self.mensagem('me agende uma tarefa'))
            self.assertIn('dia e horário', self.bot.send_message.call_args.args[1])
            self.assertFalse(app.PENDENTES)
            self.ouvir('Estudar navegação na sexta às 14h30')
            self.assertEqual(len(app.PENDENTES), 1)
            pendente = next(iter(app.PENDENTES.values()))
            self.assertEqual(pendente['dados']['plano']['acao'], 'rotina_criar')
            self.assertEqual(pendente['dados']['plano']['campos']['atividade'], 'Estudar navegação')
            self.assertEqual(pendente['dados']['plano']['campos']['horario'], '14:30')
            antes = [t for t in nucleo.vida().get('rotina', []) if t.get('atividade') == 'Estudar navegação']
            self.assertEqual(antes, [])
            app.tratar_pedido(self.mensagem('sim'))
        depois = [t for t in nucleo.vida()['rotina'] if t.get('atividade') == 'Estudar navegação']
        self.assertEqual(len(depois), 1)
        self.assertEqual((depois[0]['dia'], depois[0]['horario']), ('Sexta', '14:30'))
        self.assertFalse(app.PENDENTES)

    def test_agendamento_por_audio_completa_por_texto_e_cancela_sem_gravar(self):
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Agendamento incompleto é local.')):
            self.ouvir('me agende uma tarefa')
            self.assertIn('Qual atividade', self.bot.send_message.call_args.args[1])
            app.tratar_pedido(self.mensagem('Revisar hidrostática'))
            self.assertFalse(app.PENDENTES)
            self.ouvir('na sexta às 10h')
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('Não.')
        self.assertFalse(app.PENDENTES)
        self.assertFalse(any(t.get('atividade') == 'Revisar hidrostática' for t in nucleo.vida().get('rotina', [])))

    def test_cancelar_pergunta_nao_cria_plano_ou_chama_modelos(self):
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Sem IA para cancelar.')):
            app.tratar_pedido(self.mensagem('adicione uma tarefa'))
            self.ouvir('cancelar')
        self.assertFalse(app.PENDENTES)
        self.assertIn('cancelado', self.bot.send_message.call_args.args[1].lower())

    def test_resposta_a_pergunta_nao_migra_para_outra_conversa(self):
        app.tratar_pedido(self.mensagem('adicione uma tarefa'))
        central.criar_chat('1:10:4', 'Outra conversa')
        with patch.object(app, 'preparar_pedido_natural', return_value={
                'mensagem': 'Nova mensagem, sem plano.', 'plano': None, 'chat_id': None}) as preparar:
            self.ouvir('Estudar cálculo')
        preparar.assert_called_once()
        self.assertFalse(app.PENDENTES)

    def test_pedido_de_todos_modelos_exige_confirmacao_sem_comandos(self):
        with patch.object(app.SERVICOS, 'executar_acao', return_value='Relatório fictício.') as executar:
            app.tratar_pedido(self.mensagem('teste todos os modelos'))
            executar.assert_not_called()
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('Sim, pode executar.')
        executar.assert_called_once()
        acao, opcoes, contexto, roteador = executar.call_args.args
        self.assertEqual((acao, contexto, roteador), ('modelos_testar', '1:10:4', app.ROTEADOR))
        self.assertEqual(opcoes['confirmacao'], 'TESTAR MODELOS')
        opcoes['_progresso_modelos']({'modelo': 'llama3.2:latest', 'indice': 1, 'total': 2})
        self.assertIn('llama3.2:latest (1/2)', self.bot.send_message.call_args.args[1])
        self.assertFalse(app.PENDENTES)

    def test_confirmacao_expirada_por_audio_nao_vira_pergunta_para_ia(self):
        with patch.object(app, 'executar') as executar:
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            next(iter(app.PENDENTES.values()))['expira'] = 0
            with patch.object(app, 'responder_natural_telegram') as natural:
                self.ouvir('Sim, pode executar.')
            natural.assert_not_called()
        executar.assert_not_called()
        self.assertFalse(app.PENDENTES)
        self.assertIn('prazo de confirmação terminou', self.bot.send_message.call_args.args[1])

    def test_modelo_natural_so_muda_conversa_apos_confirmar(self):
        atual = central.obter_chat_ativo('1:10:4')
        central.configurar_chat('1:10:4', atual['id'], provedor='Ollama',
            equipe_modelos=['llama3.2:latest', 'mistral:latest'], equipe_paralela=True)
        with patch.object(app.ROTEADOR, 'catalogo_ollama', return_value={
                'habilitado': True, 'modelos': [{'nome': 'llama3.2:latest', 'nuvem': False}]}) as catalogo:
            app.tratar_pedido(self.mensagem('use somente o modelo llama3.2:latest'))
            self.assertTrue(central.obter_chat_ativo('1:10:4')['equipe_paralela'])
            catalogo.assert_not_called()
            self.ouvir('sim')
        selecionado = central.obter_chat_ativo('1:10:4')
        self.assertEqual(selecionado['modelo_ollama'], 'llama3.2:latest')
        self.assertFalse(selecionado['equipe_paralela'])
        self.assertEqual(selecionado['equipe_politica'], 'manual')
        catalogo.assert_called_once_with()

    def test_nova_pergunta_invalida_acao_antiga_e_botao_antigo(self):
        with patch.object(app, 'executar') as executar, \
                patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Perguntas locais não usam IA.')):
            app.tratar_pedido(self.mensagem('abra a calculadora'))
            token_antigo = next(iter(app.PENDENTES))
            app.tratar_pedido(self.mensagem('adicione uma tarefa'))
            self.assertFalse(app.PENDENTES)
            app.tratar_pedido(self.mensagem('sim'))
            self.assertFalse(app.PENDENTES)
            self.assertIn('título', self.bot.send_message.call_args.args[1])
            chamada = SimpleNamespace(id='callback', data='ok:'+token_antigo,
                from_user=SimpleNamespace(id=1), message=SimpleNamespace(chat=SimpleNamespace(id=10)))
            self.callback(chamada)
            self.ouvir('Estudar cálculo')
            self.ouvir('sim')
        executar.assert_not_called()
        self.assertIn('Estudar cálculo', nucleo.vida()['kanban']['A_Fazer'])

    def test_nova_pergunta_por_audio_nao_confirma_acao_anterior(self):
        with patch.object(app, 'executar') as executar, \
                patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Perguntas locais não usam IA.')):
            self.ouvir('abra a calculadora')
            self.ouvir('adicione uma tarefa')
            self.ouvir('Sim, pode executar.')
        executar.assert_not_called()
        self.assertFalse(app.PENDENTES)
        self.assertIn('título', self.bot.send_message.call_args.args[1])

    def test_nova_pergunta_preserva_pedidos_de_outro_usuario_ou_topico(self):
        app.tratar_pedido(self.mensagem('abra a calculadora', usuario=2))
        app.tratar_pedido(self.mensagem('abra a calculadora', topico=5))
        outros = set(app.PENDENTES)
        app.tratar_pedido(self.mensagem('abra a calculadora'))
        self.assertEqual(len(app.PENDENTES), 3)
        app.tratar_pedido(self.mensagem('adicione uma tarefa'))
        self.assertEqual(set(app.PENDENTES), outros)

    def test_conversa_pausada_ainda_esclarece_acao_local_sem_ia(self):
        contexto = '1:10:4'
        atual = central.obter_chat_ativo(contexto)
        central.configurar_chat(contexto, atual['id'], modo_conversa=False)
        with patch.object(app.SERVICOS, 'conversar', side_effect=AssertionError('Conversa continua pausada.')):
            self.ouvir('adicione uma tarefa')
            self.assertIn('título', self.bot.send_message.call_args.args[1])
            app.tratar_pedido(self.mensagem('Estudar física'))
            self.assertEqual(len(app.PENDENTES), 1)
            self.ouvir('sim')
        self.assertIn('Estudar física', nucleo.vida()['kanban']['A_Fazer'])
        self.assertFalse(central.obter_chat_ativo(contexto)['modo_conversa'])

    def test_consulta_explicita_legada_preserva_pausa_para_mensagens_comuns(self):
        contexto='1:10:4'
        atual=central.obter_chat_ativo(contexto)
        central.configurar_chat(contexto,atual['id'],modo_conversa=False)
        with patch.object(app,'preparar_pedido_natural',return_value={
                'mensagem':'Resposta fictícia','plano':None,'chat_id':atual['id']}) as preparar:
            app.tratar_pedido(self.mensagem('/ia Explique uma função'))
        self.assertEqual(preparar.call_args.args[:2],('Explique uma função',contexto))
        self.assertFalse(central.obter_chat_ativo(contexto)['modo_conversa'])


if __name__ == '__main__':
    unittest.main()
