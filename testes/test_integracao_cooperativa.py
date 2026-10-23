"""Cooperação integrada com catálogo/IA fictícios e estado exclusivamente temporário."""
from __future__ import annotations

import copy
import json
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
import configurar_ia_local as configurar
import multi_ia as ia
import nucleo
import servicos_chat as servicos
import voz_assistente as voz


MODELOS = ['qwen3.8:27b', 'mistral:latest', 'llama3.2:latest', 'qwen3.5:4b']


class IntegracaoCooperativa(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        for nome, valor in (('BASE', self.raiz / 'codigo'), ('DADOS', self.raiz / 'dados')):
            p = patch.object(nucleo, nome, valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {
            'TELEGRAM_ALLOWED_USER_IDS': '1', 'OLLAMA_HABILITADO': '1',
            'OLLAMA_MODEL': 'llama3.2:latest', 'OLLAMA_PERFIL': 'cpu',
        }, clear=True)
        p.start(); self.addCleanup(p.stop)
        for modulo, nome, valor in ((servicos, '_TRAVAS', {}), (app, 'PENDENTES', {}),
                                   (app, 'BOT', MagicMock())):
            p = patch.object(modulo, nome, valor)
            p.start(); self.addCleanup(p.stop)
        self.contexto = '1:10:4'
        self.outro = '1:10:5'
        self.chat = central.criar_chat(self.contexto, 'Plano fictício', 'Ollama')
        central.configurar_chat(self.contexto, self.chat['id'], modelo_ollama='llama3.2:latest')
        self.roteador = MagicMock()
        self.roteador.catalogo_ollama.side_effect = lambda: {
            'habilitado': True, 'padrao': 'llama3.2:latest',
            'modelos': [{'nome': modelo, 'nuvem': False} for modelo in MODELOS]}
        self.roteador.responder.side_effect = lambda texto, **opcoes: (
            'Contribuição de ' + opcoes['modelo_ollama'], 'Ollama')

    def ativar(self, **campos):
        return servicos.executar_acao('chat_equipe', {'ativo': True, **campos},
                                      self.contexto, self.roteador)

    def mensagem(self, texto, usuario=1, topico=4):
        return SimpleNamespace(text=texto, chat=SimpleNamespace(id=10),
                               from_user=SimpleNamespace(id=usuario), message_thread_id=topico)

    def handler_voz(self):
        bot = MagicMock()
        handlers = {}
        def registrar(**opcoes):
            def decorar(fn):
                for tipo in opcoes.get('content_types', []): handlers[tipo] = fn
                return fn
            return decorar
        bot.message_handler.side_effect = registrar
        bot.callback_query_handler.side_effect = lambda **kw: lambda fn: fn
        bot.get_file.return_value = SimpleNamespace(file_path='fixture/voz.ogg')
        bot.download_file.return_value = b'fixture-audio'
        with patch.dict(os.environ, {'TELEGRAM_TOKEN': 'fixture-token'}), \
                patch.dict(sys.modules, {'telebot': SimpleNamespace(TeleBot=MagicMock(return_value=bot))}), \
                patch('configurar_telegram.validar_token', return_value=True):
            app.configurar_bot()
        return handlers['voice'], bot

    def mensagem_voz(self, usuario=1):
        mensagem = self.mensagem('', usuario=usuario)
        mensagem.voice = SimpleNamespace(file_id='fixture-voz', file_size=13)
        mensagem.audio = None
        return mensagem

    def test_ativacao_padrao_e_cooperativa_preserva_cpu_e_historico(self):
        central.registrar_troca(self.contexto, 'Objetivo fictício', 'Contexto fictício', 'Ollama')
        anterior = central.historico_chat(self.contexto)
        ambiente = os.environ.copy()
        mensagem = self.ativar()
        ativo = central.obter_chat_ativo(self.contexto)
        self.assertEqual(ativo['equipe_modo'], 'cooperativa')
        self.assertIs(ativo['equipe_paralela'], True)
        self.assertEqual(ativo['equipe_modelos'], MODELOS)
        self.assertEqual(central.historico_chat(self.contexto), anterior)
        self.assertEqual(os.environ.copy(), ambiente)
        self.roteador.responder.assert_not_called()
        self.assertIn('cooperativa', mensagem)
        disco = json.loads((nucleo.DADOS / central.ARQUIVO).read_text(encoding='utf-8'))
        chat_disco = next(iter(disco['contextos'].values()))['chats'][0]
        self.assertEqual(chat_disco['equipe_modo'], 'cooperativa')

    def test_todos_contribuem_uma_vez_e_ha_no_maximo_uma_sintese(self):
        central.registrar_troca(self.contexto, 'Pergunta anterior', 'Resposta anterior', 'Ollama')
        anterior = central.historico_chat(self.contexto)
        self.ativar()
        eventos = []
        resposta = servicos.conversar('Compare estratégias de estudo', self.contexto,
                                     self.roteador, progresso=eventos.append)
        chamadas = self.roteador.responder.call_args_list
        self.assertEqual(len(chamadas), len(MODELOS) + 1)
        self.assertEqual([c.kwargs['modelo_ollama'] for c in chamadas[:-1]], MODELOS)
        self.assertEqual(chamadas[-1].kwargs['modelo_ollama'], 'llama3.2:latest')
        self.assertTrue(all(c.kwargs['modo_cooperativo'] is True for c in chamadas))
        self.assertTrue(all(c.kwargs['provedor'] == 'Ollama' for c in chamadas))
        self.assertTrue(all(c.kwargs['historico'] == anterior for c in chamadas))
        self.assertEqual(len({id(c.kwargs['historico']) for c in chamadas}), len(chamadas))
        self.assertIn('Contribuição de llama3.2:latest', resposta)
        self.assertEqual(len(central.historico_chat(self.contexto)), 4)
        self.assertEqual(central.historico_chat(self.outro), [])
        campos = {'etapa', 'estado', 'modelo', 'indice', 'total'}
        self.assertTrue(eventos)
        self.assertTrue(all(set(evento) == campos for evento in eventos))
        self.assertNotIn('estratégias', json.dumps(eventos, ensure_ascii=False))

    def test_modelo_individual_antigo_fora_catalogo_nao_impede_cooperacao(self):
        central.configurar_chat(self.contexto, self.chat['id'], modelo_ollama='removido:latest')
        self.ativar()
        servicos.conversar('Explique uma alternativa', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 5)
        self.assertEqual(self.roteador.responder.call_args.kwargs['modelo_ollama'], 'llama3.2:latest')

    def test_chat_legado_sem_modo_continua_paralelo_sem_migracao_destrutiva(self):
        self.ativar(modo='paralela')
        arquivo = nucleo.DADOS / central.ARQUIVO
        disco = json.loads(arquivo.read_text(encoding='utf-8'))
        chat_disco = next(iter(disco['contextos'].values()))['chats'][0]
        chat_disco.pop('equipe_modo')
        arquivo.write_text(json.dumps(disco), encoding='utf-8')
        antes = arquivo.read_bytes()
        self.assertEqual(central.obter_chat_ativo(self.contexto)['equipe_modo'], 'paralela')
        self.assertEqual(arquivo.read_bytes(), antes)
        servicos.conversar('Uma pergunta', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertTrue(all('modo_cooperativo' not in c.kwargs
                            for c in self.roteador.responder.call_args_list))

    def test_modo_invalido_nao_consulta_nem_altera_chat(self):
        antes = central.obter_chat_ativo(self.contexto)
        for modo in ('automatico', '', True, None):
            with self.subTest(modo=modo), self.assertRaises(ValueError):
                self.ativar(modo=modo)
        self.roteador.catalogo_ollama.assert_not_called()
        self.assertEqual(central.obter_chat_ativo(self.contexto), antes)

    def test_rotina_exata_da_imagem_consulta_dados_locais_sem_ia(self):
        self.ativar()
        with patch.object(app, 'ROTEADOR', self.roteador), \
                patch.object(app, 'mostrar_rotina', return_value='Segunda 14:00 — Estudar fixture') as ler:
            resultado = app.preparar_pedido_natural('Mostre a minha rotina da semana', self.contexto)
        self.roteador.responder.assert_not_called()
        ler.assert_called_once_with()
        self.assertEqual(resultado['mensagem'], 'Segunda 14:00 — Estudar fixture')
        self.assertIsNone(resultado['plano'])

    def test_consenso_prepara_pedido_sem_executar_acao(self):
        self.ativar()
        self.roteador.responder.side_effect = lambda *a, **kw: (json.dumps({
            'resposta': 'Abra a calculadora após confirmação.',
            'acao': 'pc', 'campos': {'comando': 'calc'}}), 'Ollama')
        with patch.object(app, 'ROTEADOR', self.roteador), patch.object(app, 'executar') as executar:
            resultado = app.preparar_pedido_natural('Sugira a ferramenta adequada para calcular', self.contexto)
        executar.assert_not_called()
        self.assertEqual(resultado['plano']['acao'], 'pc')
        self.assertEqual(resultado['plano']['campos'], {'comando': 'calc'})
        self.assertEqual(self.roteador.responder.call_count, 5)

    def test_telegram_on_autorizado_ativa_cooperativa_e_paralelo_preserva_opcao(self):
        with patch.object(app, 'ROTEADOR', self.roteador):
            app.tratar_pedido(self.mensagem('/chat equipe on', usuario=2))
            self.roteador.catalogo_ollama.assert_not_called()
            app.tratar_pedido(self.mensagem('/chat equipe on'))
            self.assertEqual(central.obter_chat_ativo(self.contexto)['equipe_modo'], 'cooperativa')
            self.roteador.responder.assert_not_called()
            app.tratar_pedido(self.mensagem('/chat equipe paralelo'))
            self.assertEqual(central.obter_chat_ativo(self.contexto)['equipe_modo'], 'paralela')
            app.tratar_pedido(self.mensagem('/chat equipe off'))
            self.assertIs(central.obter_chat_ativo(self.contexto)['equipe_paralela'], False)

    def test_voz_nao_autorizada_nao_baixa_ou_transcreve(self):
        handler, bot = self.handler_voz()
        with patch.object(voz, 'verificar_disponibilidade_voz') as verificar, \
                patch.object(voz, 'transcrever_audio') as transcrever:
            handler(self.mensagem_voz(usuario=2))
        verificar.assert_not_called()
        transcrever.assert_not_called()
        bot.get_file.assert_not_called()
        bot.download_file.assert_not_called()

    def test_voz_em_pausa_nao_baixa_nem_tenta_transcrever(self):
        handler, bot = self.handler_voz()
        with patch.object(voz, 'verificar_disponibilidade_voz', side_effect=ia.FalhaAPI(
                'Gemini', 401, 'Transcrição pausada; envie texto.', 'suspenso')), \
                patch.object(voz, 'transcrever_audio') as transcrever, \
                patch.object(app, 'registrar'):
            handler(self.mensagem_voz())
        bot.get_file.assert_not_called()
        bot.download_file.assert_not_called()
        transcrever.assert_not_called()
        self.assertIn('pausada', bot.send_message.call_args.args[1])

    def test_voz_transcrita_usa_mesmo_fluxo_natural_e_contexto(self):
        handler, bot = self.handler_voz()
        mensagem = self.mensagem_voz()
        with patch.object(voz, 'verificar_disponibilidade_voz'), \
                patch.object(voz, 'transcrever_audio', return_value='Mostre a minha rotina da semana') as transcrever, \
                patch.object(app, 'responder_natural_telegram') as natural, \
                patch.object(app, 'interpretar_comando') as antigo:
            handler(mensagem)
        natural.assert_called_once_with(mensagem, 'Mostre a minha rotina da semana')
        antigo.assert_not_called()
        self.assertEqual(app.contexto_mensagem(natural.call_args.args[0]), self.contexto)
        self.assertEqual(transcrever.call_args.args[:2], (b'fixture-audio', 'audio/ogg'))
        bot.download_file.assert_called_once_with('fixture/voz.ogg')

    def test_voz_com_pedido_pc_prepara_confirmacao_sem_executar(self):
        handler, bot = self.handler_voz()
        with patch.object(voz, 'verificar_disponibilidade_voz'), \
                patch.object(voz, 'transcrever_audio', return_value='Abra o VS Code'), \
                patch.object(app, 'inline', return_value=None), \
                patch.object(app, 'executar') as executar:
            handler(self.mensagem_voz())
        executar.assert_not_called()
        self.assertEqual(len(app.PENDENTES), 1)
        pendente = next(iter(app.PENDENTES.values()))
        self.assertEqual(pendente['acao'], 'pedido_natural')
        self.assertEqual(pendente['dados']['contexto'], self.contexto)
        self.assertEqual(pendente['dados']['plano']['campos'], {'comando': 'vscode_pc'})


class PayloadCooperativo(unittest.TestCase):
    def setUp(self):
        p = patch.dict(os.environ, {
            'OLLAMA_HABILITADO': '1', 'OLLAMA_MODEL': 'llama3.2:latest',
            'OLLAMA_URL': 'http://127.0.0.1:11434', 'OLLAMA_PERFIL': 'cpu',
        }, clear=True)
        p.start(); self.addCleanup(p.stop)
        for alvo, valor in (('ler_json', {}), ('gravar_json', None), ('registrar', None)):
            p = patch.object(ia, alvo, return_value=valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(configurar, 'listar_catalogo', return_value=[
            {'nome': 'llama3.2:latest', 'nuvem': False}])
        p.start(); self.addCleanup(p.stop)
        self.roteador = ia.Roteador()

    def test_payload_cpu_cooperativo_preserva_limites_sem_mudar_env(self):
        antes = os.environ.copy()
        with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta'}}) as enviar:
            resultado = self.roteador.responder('Um pedido', provedor='Ollama',
                modelo_ollama='llama3.2:latest', modo_cooperativo=True)
        self.assertEqual(resultado, ('Resposta', 'Ollama'))
        payload = enviar.call_args.args[2]
        self.assertEqual(payload['keep_alive'], 0)
        self.assertEqual(payload['options'], {'num_gpu': 0, 'num_ctx': 1024, 'num_predict': 128})
        self.assertEqual(os.environ.copy(), antes)
        enviar.assert_called_once()

    def test_payload_padrao_cooperativo_nao_forca_gpu_e_individual_nao_muda(self):
        os.environ['OLLAMA_PERFIL'] = 'padrao'
        with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta'}}) as enviar:
            self.roteador.ollama('Pedido', modo_cooperativo=True)
            cooperativo = copy.deepcopy(enviar.call_args.args[2])
            self.roteador.ollama('Pedido individual')
            individual = enviar.call_args.args[2]
        self.assertEqual(cooperativo['options'], {'num_ctx': 4096, 'num_predict': 384})
        self.assertEqual(cooperativo['keep_alive'], 0)
        self.assertNotIn('options', individual)
        self.assertNotIn('keep_alive', individual)

    def test_flag_invalida_ou_sem_modelo_explicito_nao_envia_http(self):
        with patch.object(ia, 'postar') as enviar:
            for opcoes in ({'modo_cooperativo': 'sim'},
                           {'modo_cooperativo': True},
                           {'modo_cooperativo': True, 'provedor': 'OpenAI', 'modelo_ollama': 'llama3.2:latest'},
                           {'modo_cooperativo': True, 'provedor': 'Ollama', 'modelo_ollama': 'llama3.2:latest', 'pesquisa': True}):
                with self.subTest(opcoes=opcoes), self.assertRaises(ValueError):
                    self.roteador.responder('Pedido', **opcoes)
        enviar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
