"""Equipe com modelos Ollama distintos; chamadas simuladas e propostas inertes."""
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import nucleo
from equipe_ia import consultar_equipe


class EquipeModelos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        dados = patch.object(nucleo, 'DADOS', Path(self.tmp.name))
        dados.start()
        self.addCleanup(dados.stop)
        self.roteador = MagicMock()
        self.roteador.estado_local.return_value = {
            nome: {'configurado': True, 'em_pausa': False}
            for nome in ('Gemini', 'OpenAI', 'Claude', 'Ollama')
        }
        self.roteador.catalogo_ollama.return_value = {
            'habilitado': True, 'padrao': 'qwen3.5:4b',
            'modelos': [
                {'nome': 'qwen3.5:4b', 'nuvem': False},
                {'nome': 'gemma4:31b-cloud', 'nuvem': True},
                {'nome': 'qwen3.5:latest', 'nuvem': False},
            ],
        }
        self.roteador.responder.side_effect = lambda prompt, **kw: (
            'Proposta de ' + kw.get('modelo_ollama', kw['provedor']), kw['provedor'])

    def consultar(self, modelos=None, provedores=None):
        return consultar_equipe(
            'Melhorar o assistente', self.roteador,
            provedores=provedores, modelos_ollama=modelos,
            confirmacao='CONSULTAR EQUIPE')

    def test_modelos_distintos_uma_chamada_cada_e_propostas_identificadas(self):
        resultado = self.consultar(
            ['qwen3.5:4b', 'gemma4:31b-cloud', 'qwen3.5:4b'], ['Ollama'])
        self.roteador.catalogo_ollama.assert_called_once_with()
        self.assertEqual(self.roteador.responder.call_count, 2)
        self.assertEqual([item['modelo'] for item in resultado['resultados']],
                         ['qwen3.5:4b', 'gemma4:31b-cloud'])
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))
        self.assertEqual(resultado['resultados'][1]['papel'], 'alternativa em nuvem')
        chamadas = [ch.kwargs for ch in self.roteador.responder.call_args_list]
        self.assertEqual({ch['modelo_ollama'] for ch in chamadas},
                         {'qwen3.5:4b', 'gemma4:31b-cloud'})
        self.assertTrue(all(ch['provedor'] == 'Ollama' for ch in chamadas))
        propostas = central.estado_central('teste')['contribuicoes']
        self.assertEqual({p['origem'] for p in propostas},
                         {'Ollama / qwen3.5:4b', 'Ollama / gemma4:31b-cloud'})
        self.assertTrue(all(p['status'] == 'rascunho' for p in propostas))

    def test_confirmacao_e_limite_sao_verificados_antes_do_catalogo(self):
        with self.assertRaises(ValueError):
            consultar_equipe('Objetivo', self.roteador, [], modelos_ollama=['qwen3.5:4b'])
        self.roteador.estado_local.assert_not_called()
        with self.assertRaises(ValueError):
            self.consultar(['qwen3.5:4b'] * 5, ['Gemini', 'OpenAI', 'Claude'])
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_not_called()

    def test_cinco_provedores_incluem_9router_sem_duplicar_uma_chamada(self):
        self.roteador.estado_local.return_value['9Router']={'configurado':True,'em_pausa':False}
        resultado=self.consultar(provedores=['Gemini','OpenAI','Claude','Ollama','9Router'])
        self.assertEqual(len(resultado['resultados']),5)
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))
        chamadas=self.roteador.responder.call_args_list
        self.assertEqual(len(chamadas),5)
        self.assertEqual({c.kwargs['provedor'] for c in chamadas},{'Gemini','OpenAI','Claude','Ollama','9Router'})

    def test_nomes_invalidos_ou_fora_do_catalogo_nao_consultam_modelos(self):
        for modelos in ('qwen3.5:4b', [None], ['modelo;comando'], ['ausente:4b']):
            with self.subTest(modelos=modelos), self.assertRaises(ValueError):
                self.consultar(modelos, [])
        self.roteador.catalogo_ollama.assert_called_once_with()
        self.roteador.responder.assert_not_called()

    def test_alias_latest_normaliza_e_nao_duplica_participante(self):
        resultado = self.consultar(['qwen3.5', 'qwen3.5:latest'], [])
        self.assertEqual(len(resultado['resultados']), 1)
        self.assertEqual(resultado['resultados'][0]['modelo'], 'qwen3.5:latest')
        self.roteador.responder.assert_called_once()
        self.assertEqual(self.roteador.responder.call_args.kwargs['modelo_ollama'], 'qwen3.5:latest')

    def test_falha_cloud_preserva_sucesso_local_sem_fallback_ou_repeticao(self):
        self.roteador.estado_local.return_value['Ollama']['em_pausa'] = True
        def responder(prompt, **kw):
            if kw.get('modelo_ollama') == 'gemma4:31b-cloud':
                raise RuntimeError('Conta cloud sem acesso')
            return 'Proposta local', 'Ollama'
        self.roteador.responder.side_effect = responder
        resultado = self.consultar(['gemma4:31b-cloud', 'qwen3.5:4b'], [])
        self.assertEqual([item['ok'] for item in resultado['resultados']], [False, True])
        self.assertEqual(self.roteador.responder.call_count, 2)
        self.assertEqual(len(central.estado_central('teste')['contribuicoes']), 1)
        self.assertTrue(self.roteador.estado_local.return_value['Ollama']['em_pausa'])
        self.roteador.reativar.assert_not_called()

    def test_modelos_locais_em_sequencia_e_provedor_remoto_em_paralelo(self):
        trava = threading.Lock()
        local_iniciado, remoto_iniciado = threading.Event(), threading.Event()
        ativos = 0
        max_ativos = 0
        def responder(prompt, **kw):
            nonlocal ativos, max_ativos
            if kw['provedor'] == 'Gemini':
                remoto_iniciado.set()
                if not local_iniciado.wait(2):
                    raise RuntimeError('O local não iniciou em paralelo ao remoto')
                return 'Proposta remota', 'Gemini'
            with trava:
                ativos += 1
                max_ativos = max(max_ativos, ativos)
            try:
                local_iniciado.set()
                if not remoto_iniciado.wait(2):
                    raise RuntimeError('O remoto não iniciou em paralelo ao local')
                return 'Proposta local', 'Ollama'
            finally:
                with trava: ativos -= 1
        self.roteador.responder.side_effect = responder
        resultado = self.consultar(['qwen3.5:4b', 'gemma4:31b-cloud'], ['Gemini'])
        self.assertEqual(max_ativos, 1)
        self.assertEqual(self.roteador.responder.call_count, 3)
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))

    def test_fluxo_legado_nao_lista_modelos_nem_muda_kwargs(self):
        resultado = self.consultar(None, ['Gemini', 'Ollama'])
        self.roteador.catalogo_ollama.assert_not_called()
        self.assertEqual(len(resultado['resultados']), 2)
        self.assertEqual({tuple(ch.kwargs) for ch in self.roteador.responder.call_args_list},
                         {('provedor',)})
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))

    def test_catalogo_desabilitado_impede_chamadas_de_geracao(self):
        self.roteador.catalogo_ollama.return_value['habilitado'] = False
        with self.assertRaises(ValueError):
            self.consultar(['qwen3.5:4b'], [])
        self.roteador.responder.assert_not_called()


if __name__ == '__main__':
    unittest.main()
