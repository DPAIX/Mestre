"""Configuração Ollama, pausas e diagnóstico404 com persistência/rede simuladas."""
import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multi_ia as ia
from configurar_ia_local import FalhaConfiguracao


class OllamaConfiguracao(unittest.TestCase):
    def setUp(self):
        self.persistido = {}
        self.ambiente = {
            'OLLAMA_HABILITADO': '1',
            'OLLAMA_MODEL': 'antigo:3b',
            'OLLAMA_URL': 'http://127.0.0.1:11434',
            'OPENAI_API_KEY': 'fixture-openai',
            'ANTHROPIC_API_KEY': 'fixture-claude',
        }
        env = patch.dict(os.environ, self.ambiente, clear=True)
        env.start(); self.addCleanup(env.stop)
        tempo = patch.object(ia.time, 'time', return_value=10000)
        tempo.start(); self.addCleanup(tempo.stop)
        leitura = patch.object(ia, 'ler_json', side_effect=lambda *a, **k: copy.deepcopy(self.persistido))
        leitura.start(); self.addCleanup(leitura.stop)
        def gravar(nome, dados):
            self.assertEqual(nome, 'estado_ia.json')
            self.persistido = copy.deepcopy(dados)
        escrita = patch.object(ia, 'gravar_json', side_effect=gravar)
        self.escrita = escrita.start(); self.addCleanup(escrita.stop)
        registro = patch.object(ia, 'registrar')
        self.registro = registro.start(); self.addCleanup(registro.stop)

    def falha_modelo(self, roteador):
        roteador.registrar_falha(ia.FalhaAPI('Ollama', 404, 'Modelo antigo ausente', 'modelo_indisponivel'))

    def test_trocar_configuracao_libera_apenas_padrao_ollama(self):
        for campo, valor in (('OLLAMA_MODEL', 'mistral:latest'),
                             ('OLLAMA_URL', 'http://127.0.0.1:11435'),
                             ('OLLAMA_HABILITADO', '0')):
            with self.subTest(campo=campo), patch.dict(os.environ, self.ambiente):
                self.persistido = {}
                roteador = ia.Roteador()
                roteador.registrar_falha(ia.FalhaAPI('OpenAI', 402, 'Crédito indisponível', 'sem_creditos'))
                roteador.registrar_falha(ia.FalhaAPI('Claude', 400, 'Crédito indisponível', 'sem_creditos'))
                self.falha_modelo(roteador)
                outros = {nome: copy.deepcopy(roteador.estado_local()[nome]) for nome in ('OpenAI', 'Claude')}
                self.assertFalse(roteador.disponivel('Ollama'))
                os.environ[campo] = valor
                estado = roteador.estado_local()
                self.assertNotIn('Ollama', roteador.bloqueados)
                self.assertNotIn('Ollama', roteador.falhas)
                self.assertNotIn('Ollama', roteador.sucessos)
                self.assertEqual({nome: estado[nome] for nome in outros}, outros)
                if campo != 'OLLAMA_HABILITADO':
                    with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta nova'}}) as pedido:
                        self.assertEqual(roteador.responder('Teste', provedor='Ollama'), ('Resposta nova', 'Ollama'))
                    pedido.assert_called_once()
                    self.assertEqual(pedido.call_args.args[2]['model'], os.environ['OLLAMA_MODEL'])

    def test_pausa_persistida_so_restaura_para_mesma_configuracao(self):
        roteador = ia.Roteador()
        self.falha_modelo(roteador)
        assinatura = ia.assinatura_configuracao_ollama()
        self.assertEqual(self.persistido['Ollama']['configuracao'], assinatura)
        self.assertNotIn(os.environ['OLLAMA_URL'], str(self.persistido))
        self.assertFalse(ia.Roteador().disponivel('Ollama'))
        os.environ['OLLAMA_MODEL'] = 'mistral:latest'
        novo = ia.Roteador()
        self.assertTrue(novo.disponivel('Ollama'))
        self.assertIsNone(novo.estado_local()['Ollama']['falha_em'])

    def test_estado_legado_ollama_sem_assinatura_nao_invalida_outros_provedores(self):
        self.persistido = {
            nome: {'ate': 12000, 'categoria': 'modelo_indisponivel', 'codigo': 404, 'falha_em': 9990}
            for nome in ('Ollama', 'OpenAI')
        }
        roteador = ia.Roteador()
        self.assertTrue(roteador.disponivel('Ollama'))
        self.assertFalse(roteador.disponivel('OpenAI'))

    def test_importar_roteador_antes_ler_env_preserva_pausa_da_configuracao_carregada(self):
        assinatura = ia.assinatura_configuracao_ollama()
        self.persistido = {'Ollama': {'ate': 12000, 'categoria': 'modelo_indisponivel',
                                     'codigo': 404, 'falha_em': 9990, 'configuracao': assinatura}}
        with patch.dict(os.environ, {}, clear=True):
            roteador = ia.Roteador()
            self.assertNotIn('Ollama', roteador.bloqueados)
        estado = roteador.estado_local()['Ollama']
        self.assertTrue(estado['em_pausa'])
        self.assertEqual(estado['codigo'], 404)
        self.assertEqual(estado['pausa_ate'], 12000)

    def test_resultado_atrasado_do_modelo_antigo_nao_altera_estado_novo(self):
        roteador = ia.Roteador()
        assinatura_antiga = ia.assinatura_configuracao_ollama()
        os.environ['OLLAMA_MODEL'] = 'mistral:latest'
        roteador.atualizar_configuracao_ollama()
        assinatura_nova = ia.assinatura_configuracao_ollama()
        roteador.registrar_falha(ia.FalhaAPI('Ollama', 429, 'Limite atual', 'limite_temporario'),
                                assinatura_ollama=assinatura_nova)
        antes = copy.deepcopy(roteador.estado_local()['Ollama'])
        roteador.registrar_falha(ia.FalhaAPI('Ollama', 404, 'Modelo antigo', 'modelo_indisponivel'),
                                assinatura_ollama=assinatura_antiga)
        roteador._registrar_sucesso('Ollama', assinatura_ollama=assinatura_antiga)
        self.assertEqual(roteador.estado_local()['Ollama'], antes)

    def test_modelo_explicito_consulta_sem_mudar_pausa_do_padrao(self):
        roteador = ia.Roteador()
        self.falha_modelo(roteador)
        antes = copy.deepcopy(roteador.estado_local()['Ollama'])
        with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta do modelo selecionado'}}) as pedido:
            self.assertEqual(roteador.responder('Teste', provedor='Ollama', modelo_ollama='mistral:latest'),
                             ('Resposta do modelo selecionado', 'Ollama'))
        pedido.assert_called_once()
        self.assertEqual(pedido.call_args.args[2]['model'], 'mistral:latest')
        self.assertEqual(roteador.estado_local()['Ollama'], antes)

    def test_sondagem404_modelo_ausente_uma_geracao_e_uma_leitura_catalogo(self):
        roteador = ia.Roteador()
        with patch.object(ia, 'postar', side_effect=ia.FalhaAPI('Ollama', 404, 'Ausente', 'modelo_indisponivel')) as pedido, \
                patch('configurar_ia_local.listar_modelos', return_value=['mistral:latest']) as catalogo:
            resultado = roteador.verificar_conexoes('Ollama')['Ollama']
        pedido.assert_called_once(); catalogo.assert_called_once_with('http://127.0.0.1:11434')
        self.assertFalse(resultado['ok'])
        self.assertEqual(resultado['codigo'], 404)
        self.assertIn('antigo:3b não consta no catálogo', resultado['mensagem'])
        self.assertIn('mistral:latest', resultado['mensagem'])
        self.assertIn('/modelos padrao NOME', resultado['mensagem'])

    def test_sondagem404_modelo_presente_identifica_rota_sem_fallback(self):
        roteador = ia.Roteador()
        with patch.object(ia, 'postar', side_effect=ia.FalhaAPI('Ollama', 404, 'Rota ausente', 'modelo_indisponivel')) as pedido, \
                patch('configurar_ia_local.listar_modelos', return_value=['antigo:3b']) as catalogo:
            resultado = roteador.verificar_conexoes('Ollama')['Ollama']
        pedido.assert_called_once(); catalogo.assert_called_once()
        self.assertEqual(resultado['codigo'], 404)
        self.assertIn('está no catálogo, mas a rota /api/chat', resultado['mensagem'])
        self.assertNotIn('não consta no catálogo', resultado['mensagem'])

    def test_catalogo_indisponivel_preserva404_e_nao_reenvia_geracao(self):
        roteador = ia.Roteador()
        with patch.object(ia, 'postar', side_effect=ia.FalhaAPI('Ollama', 404, 'Ausente', 'modelo_indisponivel')) as pedido, \
                patch('configurar_ia_local.listar_modelos', side_effect=FalhaConfiguracao('Serviço sem catálogo')) as catalogo:
            resultado = roteador.verificar_conexoes('Ollama')['Ollama']
        pedido.assert_called_once(); catalogo.assert_called_once()
        self.assertEqual(resultado['codigo'], 404)
        self.assertIn('não foi possível conferir o catálogo', resultado['mensagem'])


if __name__ == '__main__':
    unittest.main()
