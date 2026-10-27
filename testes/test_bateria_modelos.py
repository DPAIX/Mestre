"""Bateria explícita com relógio e modelos fictícios, sem rede ou dados de uso."""
import threading
import unittest
from unittest.mock import patch

import bateria_modelos as bateria
import conversa_equipe
from multi_ia import FalhaAPI
import servicos_chat

MODELOS = ['llama3.2:latest', 'qwen3.5:4b', 'mistral:latest', 'qwen3.8:27b']


class RoteadorFicticio:
    def __init__(self):
        self.chamadas = []
        self.catalogos = 0
        self.erros = {}
        self.tempo = 100.0

    def catalogo_ollama(self):
        self.catalogos += 1
        return {'habilitado': True, 'modelos': [{'nome': n} for n in MODELOS]}

    def limites_equipe(self, total):
        return {'por_modelo': 90., 'rodada': 90. * (total + 1), 'origem': 'adaptativo'}

    def ordenar_equipe_cpu(self, modelos):
        return list(reversed(modelos))

    def responder_equipe(self, pergunta, *, historico, modelo_ollama, limite_segundos):
        self.chamadas.append((pergunta, historico, modelo_ollama, limite_segundos))
        self.tempo += 45
        if modelo_ollama in self.erros:
            raise self.erros[modelo_ollama]
        return 'OK', 'Ollama'

    def responder(self, *args, **kwargs):
        raise AssertionError('O teste nativo não usa fallback.')


class BateriaModelosTeste(unittest.TestCase):
    def setUp(self):
        self.roteador = RoteadorFicticio()
        for contexto in (patch.object(conversa_equipe, '_TRAVA', threading.Lock()),
                patch.object(bateria.time, 'monotonic', side_effect=lambda: self.roteador.tempo)):
            contexto.start()
            self.addCleanup(contexto.stop)

    def test_todos_sao_consultados_uma_vez_sem_historico_sintese_ou_fallback(self):
        resultado = bateria.testar_catalogo(self.roteador)
        self.assertEqual(resultado['responderam'], 4)
        self.assertEqual(resultado['total'], 4)
        self.assertFalse(resultado['historico_enviado'])
        self.assertEqual(self.roteador.catalogos, 1)
        self.assertEqual(len(self.roteador.chamadas), 4)
        self.assertEqual([n for _, _, n, _ in self.roteador.chamadas], list(reversed(MODELOS)))
        self.assertEqual([r['modelo'] for r in resultado['resultados']], MODELOS)
        for pergunta, historico, _, limite in self.roteador.chamadas:
            self.assertEqual(pergunta, 'Responda somente OK.')
            self.assertEqual(historico, [])
            self.assertEqual(limite, 90)

    def test_recursos_nao_apagam_participante_e_permite_outros_modelos(self):
        self.roteador.erros[MODELOS[-1]] = FalhaAPI('Ollama', 0, 'Não cabe na estimativa de RAM.', 'recursos')
        resultado = bateria.testar_catalogo(self.roteador)
        self.assertEqual(resultado['responderam'], 3)
        self.assertEqual(len(self.roteador.chamadas), 4)
        item = resultado['resultados'][-1]
        self.assertEqual(item['categoria'], 'recursos')
        self.assertFalse(item['enviado'])
        self.assertIn(MODELOS[-1], bateria.texto_resultado(resultado))

    def test_timeout_e_conclusao_incerta_nao_enfileiram_novos_pedidos(self):
        for categoria in ('tempo_esgotado', 'geracao_incompleta'):
            with self.subTest(categoria=categoria):
                self.roteador.chamadas.clear()
                self.roteador.erros[MODELOS[-1]] = FalhaAPI('Ollama', 0, 'Prazo ou conclusão incerta.', categoria)
                resultado = bateria.testar_catalogo(self.roteador)
                self.assertEqual(len(self.roteador.chamadas), 1)
                self.assertEqual(resultado['responderam'], 0)
                for item in resultado['resultados'][:-1]:
                    self.assertEqual(item['categoria'], 'adiado')
                    self.assertFalse(item['enviado'])
                self.assertIn('0/4', bateria.texto_resultado(resultado))

    def test_orcamento_total_e_respeitado_sem_reiniciar_relogio(self):
        with patch.object(RoteadorFicticio, 'limites_equipe', return_value={
                'por_modelo': 90., 'rodada': 50., 'origem': 'personalizado'}):
            resultado = bateria.testar_catalogo(self.roteador)
        self.assertEqual([limite for _, _, _, limite in self.roteador.chamadas], [50, 5])
        self.assertEqual(sum(r.get('categoria') == 'adiado' for r in resultado['resultados']), 2)

    def test_progresso_lento_nao_envia_depois_do_orcamento(self):
        def progresso(_):
            self.roteador.tempo += 500
        resultado = bateria.testar_catalogo(self.roteador, progresso=progresso)
        self.assertEqual(self.roteador.chamadas, [])
        self.assertTrue(all(r['categoria'] == 'adiado' for r in resultado['resultados']))

    def test_compartilha_trava_com_equipe_e_libera_ao_falhar(self):
        conversa_equipe._TRAVA.acquire()
        with self.assertRaisesRegex(RuntimeError, 'já está trabalhando'):
            bateria.testar_catalogo(self.roteador)
        self.assertEqual(self.roteador.catalogos, 0)
        conversa_equipe._TRAVA.release()
        with patch.object(self.roteador, 'catalogo_ollama', side_effect=ValueError('fixture')):
            with self.assertRaises(ValueError):
                bateria.testar_catalogo(self.roteador)
        self.assertTrue(conversa_equipe._TRAVA.acquire(blocking=False))
        conversa_equipe._TRAVA.release()

    def test_catalogo_invalido_nao_gera(self):
        for modelos in ([], [{'nome': '../invalido'}], [{'nuvem': False}], 'fixture'):
            with self.subTest(modelos=modelos), patch.object(self.roteador, 'catalogo_ollama',
                    return_value={'habilitado': True, 'modelos': modelos}):
                with self.assertRaises(ValueError):
                    bateria.testar_catalogo(self.roteador)
                self.assertEqual(self.roteador.chamadas, [])

    def test_ordem_nao_pode_descartar_um_modelo(self):
        with patch.object(RoteadorFicticio, 'ordenar_equipe_cpu', return_value=MODELOS[:-1]):
            with self.assertRaises(ValueError):
                bateria.testar_catalogo(self.roteador)
        self.assertEqual(self.roteador.chamadas, [])

    def test_teste_exige_confirmacao_antes_do_catalogo(self):
        with self.assertRaises(ValueError):
            servicos_chat.executar_acao('modelos_testar', {}, 'fixture', self.roteador)
        self.assertEqual(self.roteador.catalogos, 0)
        texto = servicos_chat.executar_acao('modelos_testar',
            {'confirmacao': 'TESTAR MODELOS'}, 'fixture', self.roteador)
        self.assertIn('4/4', texto)
        self.assertEqual(len(self.roteador.chamadas), 4)

    def test_callback_interno_exige_funcao_e_nao_vem_de_json(self):
        with self.assertRaises(ValueError):
            servicos_chat.executar_acao('modelos_testar',
                {'confirmacao': 'TESTAR MODELOS', '_progresso_modelos': 'invalido'},
                'fixture', self.roteador)
        self.assertEqual(self.roteador.catalogos, 0)
        eventos=[]
        texto=servicos_chat.executar_acao('modelos_testar',
            {'confirmacao': 'TESTAR MODELOS', '_progresso_modelos': eventos.append},
            'fixture', self.roteador)
        self.assertEqual(len(eventos), 4)
        self.assertEqual(len(self.roteador.chamadas), 4)
        self.assertIn('4/4', texto)


if __name__ == '__main__':
    unittest.main()
