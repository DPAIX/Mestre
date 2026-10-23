"""Respostas de conversa locais não devem exigir um pedido de ação."""
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conversa_equipe as equipe
import interpretacao_natural as natural
import servicos_chat as servicos


class ConversaSemAcaoTeste(unittest.TestCase):
    def test_variacoes_inertes_preservam_resposta_sem_criar_plano(self):
        variantes = [
            {'resposta': 'Teste recebido. Como posso ajudar?', 'acao': None, 'campos': {}},
            {'resposta': 'Posso conversar com você.', 'acao': 'nenhuma', 'campos': None},
            {'resposta': 'Olá! Em que posso ajudar?', 'acao': ' NONE ', 'campos': {}},
            {'resposta': 'Vamos conversar.', 'acao': ''},
            {'resposta': 'Recebi sua mensagem.'},
        ]
        for obj in variantes:
            with self.subTest(obj=obj):
                self.assertEqual(natural.extrair_resposta(json.dumps(obj)),
                                 {'texto': obj['resposta'], 'plano': None})

    def test_conversa_sem_acao_dentro_de_cerca_json(self):
        texto = '```json\n' + json.dumps({'resposta': 'Entendo sua mensagem.', 'acao': None, 'campos': None}) + '\n```'
        self.assertEqual(natural.extrair_resposta(texto), {'texto': 'Entendo sua mensagem.', 'plano': None})

    def test_json_incompleto_e_duplicado_nao_inventam_falha_de_acao(self):
        for texto in ('{"resposta":"Teste recebido", "acao":',
                      '{"resposta":"Olá","acao":null,"acao":"pc","campos":{}}',
                      '{"resposta":"Olá","acao":null,"campos":{},"extra":NaN}'):
            with self.subTest(texto=texto):
                resultado = natural.extrair_resposta(texto)
                self.assertIsNone(resultado['plano'])
                self.assertIn('formato incompleto ou inválido', resultado['texto'])
                self.assertNotIn('ação válida', resultado['texto'])
                self.assertNotIn('"resposta"', resultado['texto'])

    def test_acao_invalida_nao_recebe_tolerancia_de_conversa(self):
        variantes = [
            {'resposta': 'Pronto.', 'acao': 'shell', 'campos': {'comando': 'fixture'}},
            {'resposta': 'Pronto.', 'acao': ' pc ', 'campos': {'comando': 'calc'}},
            {'resposta': 'Pronto.', 'acao': {'nome': 'pc'}, 'campos': {}},
            {'resposta': 'Pronto.', 'acao': 'pc', 'campos': {'comando': 'calc'}, 'executar': True},
            {'resposta': 'Pronto.', 'acao': None, 'campos': {'comando': 'calc'}},
            {'resposta': 'Pronto.', 'acao': 'nenhuma', 'campos': {'comando': 'calc'}},
        ]
        for obj in variantes:
            with self.subTest(obj=obj):
                resultado = natural.extrair_resposta(json.dumps(obj))
                self.assertIsNone(resultado['plano'])
                self.assertIn('Não preparei uma ação válida', resultado['texto'])

    def test_acao_valida_continua_exigindo_envelope_exato(self):
        valido = {'resposta': 'Posso abrir o programa.', 'acao': 'pc', 'campos': {'comando': 'calc'}}
        resultado = natural.extrair_resposta(json.dumps(valido))
        self.assertEqual(resultado['plano']['campos'], {'comando': 'calc'})
        for obj in ({'resposta': 'Posso abrir.', 'acao': 'pc'},
                    {'resposta': 'Posso abrir.', 'campos': {'comando': 'calc'}},
                    {**valido, 'campos': None}):
            self.assertIsNone(natural.extrair_resposta(json.dumps(obj))['plano'])

    def test_teste_com_apenas_llama_preserva_conversa_sem_segunda_chamada(self):
        roteador = MagicMock()
        modelos = ['qwen3.8:27b', 'mistral:latest', 'llama3.2:latest', 'qwen3.5:4b']
        def responder(texto, **opcoes):
            if opcoes['modelo_ollama'] != 'llama3.2:latest':
                raise RuntimeError('Fixture timed out')
            self.assertIn('resposta direta', texto)
            return json.dumps({'resposta': 'Teste recebido. Estou aqui para ajudar.', 'acao': None, 'campos': {}}), 'Ollama'
        roteador.responder.side_effect = responder
        with patch.object(equipe, '_TRAVA', threading.Lock()):
            resultado = equipe.consultar_modelos(natural.instrucoes_ia() + '\nÚLTIMA MENSAGEM DO PROPRIETÁRIO:\nteste123?',
                [], modelos, roteador, interpretar=True, modo='cooperativa')
        self.assertIn('1/4 modelos responderam', resultado['texto'])
        self.assertIn('Teste recebido. Estou aqui para ajudar.', resultado['texto'])
        self.assertNotIn('Não preparei uma ação válida', resultado['texto'])
        self.assertIsNone(resultado['plano'])
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertEqual(roteador.responder.call_count, 4)

    def test_sintese_conversacional_inerte_nao_inventa_plano(self):
        roteador = MagicMock()
        def responder(texto, **opcoes):
            resposta = 'Como posso ajudar?' if texto.startswith('Consolide ') else 'Recebi sua mensagem.'
            return json.dumps({'resposta': resposta, 'acao': None, 'campos': None}), 'Ollama'
        roteador.responder.side_effect = responder
        with patch.object(equipe, '_TRAVA', threading.Lock()):
            resultado = equipe.consultar_modelos('teste?', [], ['mistral:latest', 'llama3.2:latest'],
                roteador, interpretar=True, modo='cooperativa')
        self.assertIn('Como posso ajudar?', resultado['texto'])
        self.assertNotIn('ação válida', resultado['texto'])
        self.assertNotIn('Nenhuma ação foi preparada', resultado['texto'])
        self.assertTrue(resultado['sintese']['ok'])
        self.assertIsNone(resultado['plano'])
        self.assertEqual(roteador.responder.call_count, 3)

    def test_instrucoes_compactas_preservam_conversa_formato_e_autorizacao(self):
        texto = natural.instrucoes_ia(compacto=True)
        self.assertLess(len(texto), 1100)
        for trecho in ('resposta direta', 'JSON', 'acao nenhuma', 'campos {}',
                       'último pedido explícito', 'confirmação', 'não autorização',
                       'sem inventar dados', 'Nunca shell', 'Agenda Google é só leitura'):
            self.assertIn(trecho, texto)
        with self.assertRaises(ValueError):
            natural.instrucoes_ia(compacto='cpu')

    def test_perfil_cpu_compacta_instrucoes_e_resumos_preservando_pergunta(self):
        roteador = MagicMock()
        def responder(texto, **opcoes):
            resposta = 'Recebi sua mensagem.' if texto.startswith('Consolide ') else 'Revisão do pedido. ' * 500
            return json.dumps({'resposta': resposta, 'acao': None, 'campos': {}}), 'Ollama'
        roteador.responder.side_effect = responder
        chat = {'id': 'fixture-chat', 'titulo': 'Conversa fictícia', 'equipe_politica': 'manual',
                'provedor': 'Ollama', 'modelo_ollama': 'llama3.2:latest', 'equipe_paralela': True,
                'equipe_modo': 'cooperativa', 'equipe_modelos': ['mistral:latest', 'llama3.2:latest']}
        pergunta = 'Você me entende? Quero uma resposta apenas para esta pergunta.'
        with patch.dict(os.environ, {'OLLAMA_PERFIL': 'cpu'}, clear=True), \
                patch.object(servicos, '_TRAVAS', {}), \
                patch.object(servicos.central, 'obter_chat_ativo', return_value=chat), \
                patch.object(servicos.central, 'historico_chat', return_value=[]), \
                patch.object(servicos.central, 'registrar_troca') as registrar, \
                patch.object(equipe, '_TRAVA', threading.Lock()):
            resultado = servicos.conversar(pergunta, 'fixture-contexto', roteador, retornar_plano=True)
        prompts = [c.args[0] for c in roteador.responder.call_args_list]
        self.assertEqual(len(prompts), 3)
        self.assertTrue(all(natural.instrucoes_ia(compacto=True) in p for p in prompts))
        self.assertTrue(all(p.endswith(pergunta) for p in prompts))
        self.assertTrue(all(len(p) < 2400 for p in prompts))
        self.assertNotIn('CONTRIBUIÇÕES ANTERIORES (resumos limitados)', prompts[0])
        self.assertIsNone(resultado['plano'])
        self.assertIn('Recebi sua mensagem.', resultado['texto'])
        registrar.assert_called_once()
        roteador.catalogo_ollama.assert_not_called()

    def test_cpu_cooperativo_preserva_consenso_para_confirmacao(self):
        proposta = {'resposta': 'Proponho abrir a Calculadora.', 'acao': 'pc', 'campos': {'comando': 'calc'}}
        roteador = MagicMock()
        roteador.responder.return_value = (json.dumps(proposta), 'Ollama')
        with patch.dict(os.environ, {'OLLAMA_PERFIL': 'cpu'}, clear=True), \
                patch.object(equipe, '_TRAVA', threading.Lock()):
            resultado = equipe.consultar_modelos(natural.instrucoes_ia(compacto=True) + '\nAbra a calculadora',
                [], ['mistral:latest', 'llama3.2:latest'], roteador, interpretar=True, modo='cooperativa')
        self.assertEqual(resultado['plano']['campos'], {'comando': 'calc'})
        self.assertIn('Ainda não foi executado', resultado['texto'])
        self.assertEqual(roteador.responder.call_count, 3)
        roteador.executar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
