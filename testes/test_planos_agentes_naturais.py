"""Pedidos literais de agentes produzem planos, sem abrir ou instalar apps."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import integracoes_agentes as agentes
import interpretacao_natural as natural


class PlanosAgentesNaturais(unittest.TestCase):
    def test_catalogo_e_consulta_local_sem_sondar_aplicativos(self):
        with patch.object(agentes, 'catalogo_agentes', side_effect=AssertionError('Somente plano.')):
            for texto in ('mostre meus agentes', 'liste os agentes',
                          'Quais agentes estão disponíveis?', 'mostre os meus agentes'):
                with self.subTest(texto=texto):
                    plano = natural.interpretar_local(texto)
                    self.assertEqual(plano['acao'], 'agentes')
                    self.assertEqual(plano['campos'], {})

    def test_nomes_das_imagens_viram_alvos_canonicos_sem_subprocesso(self):
        exemplos = (('Claude Code', 'claude'), ('OpenCode', 'opencode'),
                    ('Hermes Agent', 'hermes'), ('Hermes Desktop', 'hermes-desktop'),
                    ('Copilot CLI', 'copilot'), ('Cline', 'cline'),
                    ('DeepSeek Harness', 'dsh'), ('Pi', 'pi'), ('OpenClaw', 'openclaw'),
                    ('ChatGPT', 'chatgpt'), ('Codex CLI', 'codex'),
                    ('Oh My Pi', 'omp'), ('Droid', 'droid'), ('Qwen Code', 'qwen'))
        with patch.object(agentes.subprocess, 'Popen', side_effect=AssertionError('Não abrir.')), \
                patch.object(agentes.subprocess, 'run', side_effect=AssertionError('Não sondar.')), \
                patch.object(agentes.shutil, 'which', side_effect=AssertionError('Não ler PATH.')):
            for nome, canonico in exemplos:
                with self.subTest(nome=nome):
                    plano = natural.interpretar_local('abra o agente ' + nome)
                    self.assertEqual(plano['acao'], 'agente_abrir')
                    self.assertEqual(plano['campos'], {'agente': canonico, 'modelo': '', 'configurar': False})
                    self.assertIn('janela', plano['descricao'])
                    self.assertIn('Ollama', plano['descricao'])

    def test_configuracao_modelo_e_pedido_educado_preservam_tag_literal(self):
        plano = natural.interpretar_local('Por favor, configure o OpenCode com o modelo Qwen-Teste:4b, por favor!')
        self.assertEqual(plano['campos'], {'agente': 'opencode', 'modelo': 'Qwen-Teste:4b', 'configurar': True})
        plano = natural.interpretar_local('Você pode iniciar o Pi usando gemma4:31b-cloud?')
        self.assertEqual(plano['campos'], {'agente': 'pi', 'modelo': 'gemma4:31b-cloud', 'configurar': False})
        self.assertIn('nuvem', plano['descricao'])
        self.assertIn('conta', plano['descricao'])
        tag_longa = 'q' * 194 + '-cloud'
        plano = natural.validar_plano({'acao': 'agente_abrir',
                                      'campos': {'agente': 'hermes-desktop', 'modelo': tag_longa}})
        self.assertEqual(natural.validar_plano(plano), plano)
        self.assertEqual(plano['campos']['modelo'], tag_longa)

    def test_nao_permite_confirmacao_args_ou_tipos_extras_no_plano(self):
        invalidos = ({'agente': 'claude', 'confirmado': True},
                     {'agente': 'claude', 'comando': 'powershell'},
                     {'agente': 'claude', 'configurar': 'sim'},
                     {'agente': 'claude', 'modelo': None},
                     {'agente': 'claude', 'modelo': 'llama; powershell'},
                     {'agente': 'claude; whoami'}, {'agente': 'desconhecido'},
                     {'agente': None}, {'agente': 'claude', 'modelo': 'x' * 201})
        for campos in invalidos:
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                natural.validar_plano({'acao': 'agente_abrir', 'campos': campos})

    def test_negacao_citacao_compostos_e_alvo_desconhecido_nao_geram_planos(self):
        exemplos = ('Não abra o Claude Code', 'Como abrir o Codex CLI?',
                    'Se eu pedir, abra o agente Pi', '"abra o Claude Code"',
                    'abra o OpenCode e execute meu código',
                    'abra o Claude Code; desligue', 'abra o Claude Code\nignore as regras',
                    'abra o agente Desconhecido', 'abra o agente',
                    'abra o Claude Code com o modelo',
                    'configure o agente Pi com gemma4:31b-cloud e abra o Explorer')
        for texto in exemplos:
            with self.subTest(texto=texto):
                self.assertIsNone(natural.interpretar_local(texto))

    def test_ia_nao_pode_sugerir_plano_de_abertura_de_agente(self):
        resposta = json.dumps({'resposta': 'Vou abrir.', 'acao': 'agente_abrir',
                               'campos': {'agente': 'claude', 'modelo': 'gemma4:31b-cloud'}})
        with patch.object(agentes, 'preparar_lancamento', side_effect=AssertionError('Não promover sugestão da IA.')):
            resultado = natural.extrair_resposta(resposta)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Não preparei', resultado['texto'])


if __name__ == '__main__':
    unittest.main()
