"""Equipe automática com catálogo fictício e estado somente temporário."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import nucleo
import servicos_chat as servicos


MODELOS = ['qwen3.8:27b', 'mistral:latest', 'llama3.2:latest', 'qwen3.5:4b']


class EquipePadraoTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        for nome, valor in (('BASE', self.raiz / 'codigo'), ('DADOS', self.raiz / 'dados')):
            p = patch.object(nucleo, nome, valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'OLLAMA_HABILITADO': '1', 'OLLAMA_PERFIL': 'cpu',
                                   'OLLAMA_MODEL': 'llama3.2:latest'}, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos, '_TRAVAS', {})
        p.start(); self.addCleanup(p.stop)
        self.contexto = 'telegram:1:10:0'
        self.outro = 'telegram:1:20:0'
        self.roteador = MagicMock()
        self.catalogo = {'habilitado': True, 'modelos': [
            {'nome': nome, 'nuvem': False} for nome in MODELOS]}
        self.roteador.catalogo_ollama.side_effect = lambda: copy.deepcopy(self.catalogo)
        self.roteador.responder.side_effect = lambda texto, **kw: (
            'Contribuição de ' + kw.get('modelo_ollama', kw['provedor']), kw['provedor'])

    def chat(self, contexto=None):
        return central.obter_chat_ativo(contexto or self.contexto)

    def arquivo(self):
        return nucleo.DADOS / central.ARQUIVO

    def perguntar(self):
        return servicos.conversar('Compare estratégias de organização', self.contexto, self.roteador)

    def test_principal_novo_auto_sem_consultar_catalogo_nas_leituras(self):
        chat = self.chat()
        self.assertEqual(chat['equipe_politica'], 'automatica')
        self.assertEqual(chat['mensagens'], [])
        central.listar_chats(self.contexto)
        central.estado_central(self.contexto)
        servicos.resumo_chats(self.contexto)
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_not_called()

    def test_primeira_mensagem_usa_todos_sem_comando_ou_alteracao_env(self):
        ambiente = os.environ.copy()
        resposta = self.perguntar()
        self.roteador.catalogo_ollama.assert_called_once_with()
        chamadas = self.roteador.responder.call_args_list
        self.assertEqual(len(chamadas), len(MODELOS) + 1)
        self.assertEqual([c.kwargs['modelo_ollama'] for c in chamadas[:-1]], MODELOS)
        self.assertTrue(all(c.kwargs['provedor'] == 'Ollama' for c in chamadas))
        self.assertTrue(all(c.kwargs['modo_cooperativo'] is True for c in chamadas))
        self.assertEqual(chamadas[-1].kwargs['modelo_ollama'], 'llama3.2:latest')
        atual = self.chat()
        self.assertEqual(atual['equipe_politica'], 'automatica')
        self.assertEqual(atual['equipe_modo'], 'cooperativa')
        self.assertTrue(atual['equipe_paralela'])
        self.assertEqual(atual['equipe_modelos'], MODELOS)
        self.assertEqual(len(central.historico_chat(self.contexto)), 2)
        self.assertIn('Equipe cooperativa', resposta)
        self.assertEqual(os.environ.copy(), ambiente)
        self.roteador.reativar.assert_not_called()

    def test_catalogo_e_relido_e_novos_modelos_participam_na_pergunta_seguinte(self):
        self.perguntar()
        novos = ['llama3.2:latest', 'novo:3b']
        self.catalogo['modelos'] = [{'nome': nome, 'nuvem': False} for nome in novos]
        self.roteador.responder.reset_mock()
        self.perguntar()
        self.assertEqual(self.roteador.catalogo_ollama.call_count, 2)
        chamadas = self.roteador.responder.call_args_list
        self.assertEqual([c.kwargs['modelo_ollama'] for c in chamadas[:-1]], novos)
        self.assertEqual(self.chat()['equipe_modelos'], novos)

    def test_duplicatas_do_catalogo_nao_repetem_participantes(self):
        self.catalogo['modelos'].append(copy.deepcopy(self.catalogo['modelos'][0]))
        self.perguntar()
        self.assertEqual(self.roteador.responder.call_count, 5)
        self.assertEqual(self.chat()['equipe_modelos'], MODELOS)

    def test_legado_sem_politica_migra_sob_demanda_preservando_historia(self):
        chat = central.criar_chat(self.contexto, 'Legado fictício', 'Gemini')
        central.registrar_troca(self.contexto, 'Pergunta anterior', 'Resposta preservada', 'Gemini')
        disco = json.loads(self.arquivo().read_text())
        espaco = next(iter(disco['contextos'].values()))
        espaco['chats'][0].pop('equipe_politica')
        self.arquivo().write_text(json.dumps(disco), encoding='utf-8')
        original = self.arquivo().read_bytes()
        self.assertEqual(self.chat()['equipe_politica'], 'automatica')
        self.assertEqual(central.listar_chats(self.contexto)[0]['equipe_politica'], 'automatica')
        self.assertEqual(self.arquivo().read_bytes(), original)
        self.perguntar()
        atual = self.chat()
        self.assertEqual(atual['id'], chat['id'])
        self.assertEqual(atual['provedor'], 'Ollama')
        self.assertEqual(atual['equipe_politica'], 'automatica')
        self.assertEqual(central.historico_chat(self.contexto)[0]['content'], 'Pergunta anterior')
        self.assertEqual(len(atual['mensagens']), 4)

    def test_off_explicito_permanece_manual_apos_novas_perguntas(self):
        self.perguntar()
        servicos.executar_acao('chat_equipe', {'ativo': False}, self.contexto, self.roteador)
        self.assertEqual(self.chat()['equipe_politica'], 'manual')
        self.roteador.catalogo_ollama.reset_mock()
        self.roteador.responder.reset_mock()
        self.perguntar()
        self.perguntar()
        self.roteador.catalogo_ollama.assert_not_called()
        self.assertEqual(self.roteador.responder.call_count, 2)
        self.assertFalse(self.chat()['equipe_paralela'])
        self.assertEqual(self.chat()['equipe_politica'], 'manual')

    def test_modelo_individual_explicito_nao_e_substituido(self):
        self.perguntar()
        servicos.executar_acao('chat_modelo', {'modelo': 'mistral:latest'}, self.contexto, self.roteador)
        self.roteador.catalogo_ollama.reset_mock()
        self.roteador.responder.reset_mock()
        self.perguntar()
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_called_once()
        self.assertEqual(self.roteador.responder.call_args.kwargs['modelo_ollama'], 'mistral:latest')
        self.assertEqual(self.chat()['equipe_politica'], 'manual')

    def test_provedor_individual_novo_e_manual_e_nao_acessa_ollama(self):
        chat = central.criar_chat(self.contexto, 'Provedor escolhido', 'Gemini')
        self.assertEqual(chat['equipe_politica'], 'manual')
        self.perguntar()
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_called_once()
        self.assertEqual(self.roteador.responder.call_args.kwargs['provedor'], 'Gemini')

    def test_somente_modo_conversa_preserva_politica_automatica(self):
        chat = self.chat()
        central.configurar_chat(self.contexto, chat['id'], modo_conversa=False)
        self.assertEqual(self.chat()['equipe_politica'], 'automatica')
        central.configurar_chat(self.contexto, chat['id'], modo_conversa=True)
        self.perguntar()
        self.assertEqual(self.roteador.responder.call_count, 5)

    def test_falha_de_catalogo_nao_muda_politica_nem_usa_api_externa(self):
        self.chat()
        original = self.arquivo().read_bytes()
        self.roteador.catalogo_ollama.side_effect = RuntimeError('Serviço fictício sem resposta')
        with self.assertRaises(RuntimeError):
            self.perguntar()
        self.assertEqual(self.arquivo().read_bytes(), original)
        self.roteador.responder.assert_not_called()
        self.assertEqual(self.chat()['equipe_politica'], 'automatica')

    def test_catalogo_desabilitado_vazio_invalido_ou_excedente_nao_gera(self):
        self.chat()
        original = self.arquivo().read_bytes()
        catalogos = [None, {'habilitado': False, 'modelos': []},
                     {'habilitado': True, 'modelos': []},
                     {'habilitado': True, 'modelos': 'invalido'},
                     {'habilitado': True, 'modelos': [{}]},
                     {'habilitado': True, 'modelos': [{'nome': 'tag;invalida'}]},
                     {'habilitado': True, 'modelos': [{'nome': f'modelo:{i}'} for i in range(33)]}]
        for catalogo in catalogos:
            with self.subTest(catalogo=catalogo):
                self.roteador.catalogo_ollama.side_effect = None
                self.roteador.catalogo_ollama.return_value = catalogo
                with self.assertRaises(ValueError):
                    self.perguntar()
                self.assertEqual(self.arquivo().read_bytes(), original)
        self.roteador.responder.assert_not_called()

    def test_off_durante_leitura_do_catalogo_nao_e_sobrescrito(self):
        chat = self.chat()
        def ler():
            central.configurar_chat(self.contexto, chat['id'], equipe_paralela=False, equipe_modelos=[])
            return copy.deepcopy(self.catalogo)
        self.roteador.catalogo_ollama.side_effect = ler
        with self.assertRaises(RuntimeError):
            self.perguntar()
        self.roteador.responder.assert_not_called()
        self.assertFalse(self.chat()['equipe_paralela'])
        self.assertEqual(self.chat()['equipe_politica'], 'manual')

    def test_selecao_trocada_durante_catalogo_nao_configura_outro_chat(self):
        inicial = self.chat()
        novo = central.criar_chat(self.contexto, 'Outro chat')
        central.selecionar_chat(self.contexto, inicial['id'])
        def ler():
            central.selecionar_chat(self.contexto, novo['id'])
            return copy.deepcopy(self.catalogo)
        self.roteador.catalogo_ollama.side_effect = ler
        with self.assertRaises(RuntimeError):
            self.perguntar()
        self.roteador.responder.assert_not_called()
        self.assertEqual(self.chat()['id'], novo['id'])
        self.assertFalse(self.chat()['equipe_paralela'])
        self.assertEqual(central.historico_chat(self.contexto), [])

    def test_atualizacao_automatica_e_isolada_por_contexto(self):
        outro = self.chat(self.outro)
        self.perguntar()
        self.assertFalse(self.chat(self.outro)['equipe_paralela'])
        self.assertEqual(self.chat(self.outro)['id'], outro['id'])
        self.assertEqual(central.historico_chat(self.outro), [])

    def test_politica_invalida_nao_altera_estado(self):
        chat = self.chat()
        antes = self.arquivo().read_bytes()
        for politica in ('', True, 'todos', 1):
            with self.subTest(politica=politica), self.assertRaises(ValueError):
                central.configurar_chat(self.contexto, chat['id'], equipe_politica=politica)
        self.assertEqual(self.arquivo().read_bytes(), antes)


if __name__ == '__main__':
    unittest.main()
