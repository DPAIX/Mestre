"""Conversa entre modelos: concorrência real, roteador falso e planos inertes."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import conversa_equipe as equipe


MODELOS = ['mistral:latest', 'llama3.2:latest', 'qwen3.5:4b', 'gemma4:31b-cloud']


def envelope(acao='pc', campos=None, resposta='Posso preparar o pedido.'):
    return json.dumps({'resposta': resposta, 'acao': acao,
                       'campos': {'comando': 'calc'} if campos is None else campos},
                      ensure_ascii=False)


class ConversaEquipeTeste(unittest.TestCase):
    def setUp(self):
        self.trava = threading.Lock()
        alteracao = patch.object(equipe, '_TRAVA', self.trava)
        alteracao.start(); self.addCleanup(alteracao.stop)
        self.roteador = MagicMock()
        self.roteador.responder.side_effect = lambda mensagem, **kw: (
            'Resposta de ' + kw['modelo_ollama'], 'Ollama')

    def consultar(self, *, texto='Ajude a desenvolver o assistente.', historico=None,
                  modelos=None, interpretar=False, roteador=None):
        return equipe.consultar_modelos(
            texto, [] if historico is None else historico,
            MODELOS if modelos is None else modelos,
            self.roteador if roteador is None else roteador, interpretar=interpretar)

    def test_quatro_modelos_entram_simultaneamente_com_provedor_e_tag_explicitos(self):
        barreira = threading.Barrier(4)
        trava = threading.Lock()
        threads = set()
        chamadas = []

        def responder(mensagem, **kw):
            with trava:
                threads.add(threading.get_ident())
                chamadas.append((mensagem, kw))
            barreira.wait(timeout=2)
            return 'Resposta de ' + kw['modelo_ollama'], 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar()
        self.assertEqual(len(threads), 4)
        self.assertEqual(len(chamadas), 4)
        self.assertEqual({kw['modelo_ollama'] for _, kw in chamadas}, set(MODELOS))
        self.assertTrue(all(kw['provedor'] == 'Ollama' for _, kw in chamadas))
        self.assertTrue(all(set(kw) == {'provedor', 'modelo_ollama', 'historico'}
                            for _, kw in chamadas))
        self.assertEqual([r['modelo'] for r in resultado['resultados']], MODELOS)
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertIn('4/4 modelos responderam', resultado['texto'])
        self.assertIsNone(resultado['plano'])

    def test_copias_de_historico_isolam_participantes_e_preservam_original(self):
        historico = [{'role': 'user', 'content': 'Contexto original.'}]
        original = copy.deepcopy(historico)
        barreira = threading.Barrier(4)
        observados = []
        trava = threading.Lock()

        def responder(mensagem, **kw):
            with trava:
                observados.append(copy.deepcopy(kw['historico']))
            kw['historico'][0]['content'] = kw['modelo_ollama']
            kw['historico'].append({'role': 'assistant', 'content': 'Turno privado.'})
            barreira.wait(timeout=2)
            self.assertEqual(kw['historico'][0]['content'], kw['modelo_ollama'])
            return 'Resposta independente.', 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar(historico=historico)
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertEqual(historico, original)
        self.assertEqual(observados, [original] * 4)

    def test_falha_parcial_preserva_demais_respostas_sem_repeticao_ou_fallback(self):
        def responder(mensagem, **kw):
            if kw['modelo_ollama'] == MODELOS[1]:
                raise RuntimeError('Modelo fixture indisponível.')
            return 'Resposta de ' + kw['modelo_ollama'], 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar()
        self.assertEqual([r['ok'] for r in resultado['resultados']], [True, False, True, True])
        self.assertIn('3/4 modelos responderam', resultado['texto'])
        self.assertIn('Modelo fixture indisponível.', resultado['texto'])
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertTrue(all(c.kwargs['provedor'] == 'Ollama'
                            for c in self.roteador.responder.call_args_list))
        self.assertFalse(self.trava.locked())

    def test_falha_total_informa_modelos_e_libera_trava_para_proxima_conversa(self):
        self.roteador.responder.side_effect = RuntimeError('Falha fixture em todos.')
        with self.assertRaisesRegex(RuntimeError, 'Nenhum modelo da equipe respondeu') as erro:
            self.consultar()
        self.assertEqual(self.roteador.responder.call_count, 4)
        for modelo in MODELOS:
            self.assertIn(modelo, str(erro.exception))
        self.assertFalse(self.trava.locked())
        self.roteador.responder.side_effect = lambda mensagem, **kw: ('Voltou a responder.', 'Ollama')
        resultado = self.consultar()
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))

    def test_unanimidade_de_acao_e_campos_normalizados_prepara_um_plano(self):
        def responder(mensagem, **kw):
            valor = '2,50' if kw['modelo_ollama'] in MODELOS[:2] else '2.50'
            campos = {'descricao': 'Almoço', 'valor': valor, 'tipo': 'saida'}
            return envelope('financeiro', campos, resposta='Avaliação de ' + kw['modelo_ollama']), 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar(interpretar=True)
        self.assertEqual(resultado['plano']['acao'], 'financeiro')
        self.assertEqual(resultado['plano']['campos'],
                         {'tipo': 'saida', 'valor': '2.50', 'descricao': 'Almoço'})
        self.assertTrue(all(r['plano'] == resultado['plano'] for r in resultado['resultados']))
        self.assertIn('concordaram', resultado['texto'])
        self.assertIn('Ainda não foi executado', resultado['texto'])

    def test_divergencia_de_campo_acao_ou_ausencia_de_plano_nao_prepara_acao(self):
        divergencias = (
            envelope('pc', {'comando': 'notepad'}),
            envelope('agua', {}),
            envelope('nenhuma', {}, resposta='Preciso de uma informação.'),
            'Resposta em conversa, sem proposta de ação.',
            envelope('shell', {'comando': 'fixture-bloqueada'}),
        )
        for divergente in divergencias:
            with self.subTest(divergente=divergente):
                self.roteador.responder.side_effect = lambda mensagem, **kw: (
                    divergente if kw['modelo_ollama'] == MODELOS[-1] else envelope(), 'Ollama')
                resultado = self.consultar(interpretar=True)
                if '"acao": "shell"' in divergente:
                    self.assertEqual([r['ok'] for r in resultado['resultados']],[True,True,True,False])
                    self.assertEqual(resultado['resultados'][-1]['categoria'],'resposta_invalida')
                else:
                    self.assertTrue(all(r['ok'] for r in resultado['resultados']))
                self.assertIsNone(resultado['plano'])
                self.assertIn('não tiveram concordância de todos', resultado['texto'])

    def test_concordancia_dos_sobreviventes_nao_substitui_unanimidade(self):
        def responder(mensagem, **kw):
            if kw['modelo_ollama'] == MODELOS[-1]:
                raise RuntimeError('Fixture sem resposta.')
            return envelope(), 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar(interpretar=True)
        self.assertEqual(sum(r['ok'] for r in resultado['resultados']), 3)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada', resultado['texto'])

    def test_provedor_errado_ou_conteudo_invalido_nao_conta_como_resposta(self):
        retornos = dict(zip(MODELOS, [
            ('Resposta válida.', 'Ollama'), ('Provedor incorreto.', 'Gemini'),
            ('   ', 'Ollama'), (None, 'Ollama')]))
        self.roteador.responder.side_effect = lambda mensagem, **kw: retornos[kw['modelo_ollama']]
        resultado = self.consultar()
        self.assertEqual([r['ok'] for r in resultado['resultados']], [True, False, False, False])
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertIn('1/4 modelos responderam', resultado['texto'])

    def test_segunda_equipe_e_rejeitada_enquanto_primeira_trabalha(self):
        barreira = threading.Barrier(5)
        liberar = threading.Event()
        resultados = []
        erros = []

        def responder(mensagem, **kw):
            barreira.wait(timeout=2)
            if not liberar.wait(2):
                raise RuntimeError('Fixture não foi liberada.')
            return 'Resposta da primeira equipe.', 'Ollama'

        def executar_primeira():
            try:
                resultados.append(self.consultar())
            except Exception as erro:
                erros.append(erro)

        self.roteador.responder.side_effect = responder
        thread = threading.Thread(target=executar_primeira, daemon=True)
        thread.start()
        outro = MagicMock()
        try:
            barreira.wait(timeout=2)
            with self.assertRaisesRegex(RuntimeError, 'já está respondendo'):
                self.consultar(roteador=outro)
            outro.responder.assert_not_called()
        finally:
            liberar.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(erros, [])
        self.assertEqual(len(resultados), 1)
        self.assertFalse(self.trava.locked())

    def test_falha_ao_criar_executor_tambem_libera_trava(self):
        with patch.object(equipe, 'ThreadPoolExecutor', side_effect=RuntimeError('Fixture sem workers')):
            with self.assertRaisesRegex(RuntimeError, 'Fixture sem workers'):
                self.consultar()
        self.assertFalse(self.trava.locked())
        self.assertTrue(all(r['ok'] for r in self.consultar()['resultados']))

    def test_redacao_antes_do_roteador_e_em_respostas_erros_e_plano(self):
        segredos = ['fixture-pergunta-123', 'fixture-historico-456',
                    'fixture-resposta-789', 'fixture-erro-987']
        recebidos = []
        trava = threading.Lock()

        def responder(mensagem, **kw):
            with trava:
                recebidos.append((mensagem, copy.deepcopy(kw['historico'])))
            if kw['modelo_ollama'] == MODELOS[-1]:
                raise RuntimeError('CLIENT_SECRET="' + segredos[3] + '"')
            return envelope('kanban_adicionar', {
                'coluna': 'A_Fazer', 'texto': 'Revisar EXA_API_KEY=' + segredos[2]},
                resposta='Diagnóstico CLIENT_SECRET="' + segredos[2] + '"'), 'Ollama'

        self.roteador.responder.side_effect = responder
        resultado = self.consultar(
            texto='Compare EXA_API_KEY=' + segredos[0],
            historico=[{'role': 'user', 'content': 'CLIENT_SECRET="' + segredos[1] + '"'}],
            interpretar=True)
        serializado = json.dumps({'recebidos': recebidos, 'resultado': resultado})
        for segredo in segredos:
            self.assertNotIn(segredo, serializado)
        self.assertEqual(len(recebidos), 4)

    def test_erro_total_tambem_redige_credencial_sem_prefixo(self):
        segredo = 'fixture-erro-global-763'
        self.roteador.responder.side_effect = RuntimeError('EXA_API_KEY=' + segredo)
        with self.assertRaises(RuntimeError) as erro:
            self.consultar()
        self.assertNotIn(segredo, str(erro.exception))
        self.assertFalse(self.trava.locked())

    def test_modelos_duplicados_sao_consultados_uma_vez_sem_alterar_lista(self):
        modelos = MODELOS + [MODELOS[0], MODELOS[2]]
        original = list(modelos)
        resultado = self.consultar(modelos=modelos)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertEqual([r['modelo'] for r in resultado['resultados']], MODELOS)
        self.assertEqual(modelos, original)

    def test_argumentos_invalidos_nao_consultam_modelos_nem_retendem_trava(self):
        invalidos = [
            {'texto': ''}, {'texto': 'x' * 12001}, {'texto': None},
            {'modelos': []}, {'modelos': ['fixture'] * 9}, {'modelos': 'fixture'},
            {'modelos': ['fixture;comando']}, {'modelos': [None]},
            {'historico': 'histórico inválido'},
        ]
        for argumentos in invalidos:
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                self.consultar(**argumentos)
            self.assertFalse(self.trava.locked())
        self.roteador.responder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
