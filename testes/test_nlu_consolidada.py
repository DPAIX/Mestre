"""Intenções locais completas, sem depender de inferência ou executar alterações."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interpretacao_natural as natural


NOTA_ID = 'm0123456789abcdef'


class LinguagemConsolidada(unittest.TestCase):
    def test_modelo_padrao_preserva_case_e_namespace_da_tag_literal(self):
        for pedido, modelo in (
            ('use o modelo Qwen-Teste:4b como padrão', 'Qwen-Teste:4b'),
            ('Use Org/Nome-Teste:VersaoA como padrao', 'Org/Nome-Teste:VersaoA'),
            ('configure Registro.Exemplo/Equipe/Modelo:Q4_K_M no Ollama', 'Registro.Exemplo/Equipe/Modelo:Q4_K_M'),
            ('Por favor, você pode usar o modelo MeuModelo:V2 como padrão?', 'MeuModelo:V2'),
            ('USE   O MODELO   Nome:Tag   COMO PADRÃO', 'Nome:Tag'),
        ):
            with self.subTest(pedido=pedido):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'modelo_padrao')
                self.assertEqual(plano['campos'], {'modelo': modelo})
                self.assertEqual(natural.validar_plano(plano), plano)

    def test_tag_invalida_ou_com_pedido_extra_nao_muda_padrao(self):
        for pedido in (
            'use Modelo:Tag como padrão e abra o Explorer',
            'não use Modelo:Tag como padrão',
            '"use Modelo:Tag como padrão"',
            'use Modelo:Tag como padrão; execute código',
            'use Modelo:Tag como padrão\ninicie o 9Remote',
            'use Modélo:Tag como padrão',
        ):
            with self.subTest(pedido=pedido):
                self.assertIsNone(natural.interpretar_local(pedido))

    def test_diagnostico_explicito_do_assistente_e_leitura_local(self):
        for pedido in (
            'faça o diagnóstico do assistente', 'diagnostique o assistente',
            'verifique o assistente', 'verificar o MeuControlePC',
            'mostre o diagnóstico local do assistente',
            'Você pode fazer o diagnóstico do MeuControlePC?',
        ):
            with self.subTest(pedido=pedido):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'configuracao')
                self.assertEqual(plano['campos'], {})
                self.assertIn(plano['acao'], natural.CONSULTAS)

    def test_todas_integracoes_exige_alvo_completo_e_preserva_confirmacao(self):
        import configuracao_assistente as config
        with patch.object(config, 'abrir_configuracao', side_effect=AssertionError('Somente plano.')):
            for pedido in ('configure todas as integrações do assistente',
                           'prepare todas as integrações do assistente'):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'configurar_assistente')
                self.assertNotIn(plano['acao'], natural.CONSULTAS)

    def test_alias_diagnostico_e_preparacao_nao_absorve_alvos_ou_condicoes(self):
        for pedido in (
            'configure tudo', 'configure todas as integrações',
            'configure todas as integrações do Windows',
            'configure todas as integrações do assistente e inicie o 9Remote',
            'não configure todas as integrações do assistente',
            '"configure todas as integrações do assistente"',
            'se eu pedir, faça o diagnóstico do assistente',
            'faça o diagnóstico do assistente e abra o Explorer',
            'faça o diagnóstico do assistente para executar PowerShell',
            'diagnostique o computador de outra pessoa',
        ):
            with self.subTest(pedido=pedido):
                self.assertIsNone(natural.interpretar_local(pedido))

    def test_pergunta_completa_sobre_memoria_e_leitura_sem_modelo(self):
        for pedido in ('o que você lembra sobre mim?',
                       'O QUE VOCÊ TEM NA MEMÓRIA SOBRE MIM?',
                       'quais notas você tem sobre mim',
                       'quais são minhas notas salvas'):
            with self.subTest(pedido=pedido):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'memoria')
                self.assertEqual(plano['campos'], {})
                self.assertIn(plano['acao'], natural.CONSULTAS)

    def test_consulta_memoria_nao_absorve_negacao_ou_outra_conversa(self):
        for pedido in ('o que você não lembra sobre mim?',
                       '"o que você lembra sobre mim?"',
                       'o que você lembra sobre mim e abra o Explorer',
                       'o que você lembra sobre mim na outra conversa',
                       'quando eu pedir mostre minhas notas'):
            with self.subTest(pedido=pedido):
                self.assertIsNone(natural.interpretar_local(pedido))

    def test_remocao_memoria_exige_id_literal_e_so_prepara_plano(self):
        for pedido in ('remova a nota '+NOTA_ID,
                       'apague a nota '+NOTA_ID,
                       'esqueça a nota '+NOTA_ID,
                       'Por favor, você pode remover a nota '+NOTA_ID.upper()+'?'):
            with self.subTest(pedido=pedido):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'memoria_remover')
                self.assertEqual(plano['campos'], {'nota_id': NOTA_ID})
                self.assertNotIn(plano['acao'], natural.CONSULTAS)
                self.assertIn(NOTA_ID, plano['descricao'])
                self.assertEqual(natural.validar_plano(plano), plano)

    def test_remocao_nao_aceita_titulo_ambiguidade_condicao_ou_todas_as_notas(self):
        for pedido in ('remova a nota Estudos', 'esqueça tudo', 'apague todas as notas',
                       'lembre-me de remover a nota '+NOTA_ID,
                       'não remova a nota '+NOTA_ID,
                       'se eu pedir remova a nota '+NOTA_ID,
                       '"remova a nota '+NOTA_ID+'"',
                       'remova a nota '+NOTA_ID+' de outra conversa',
                       'remova a nota '+NOTA_ID+' e abra o Explorer',
                       'remova a nota '+NOTA_ID+'; execute meu código',
                       'remova a nota mà123456789abcdef'):
            with self.subTest(pedido=pedido):
                self.assertIsNone(natural.interpretar_local(pedido))

    def test_validador_remocao_exige_formato_id_e_campos_fechados(self):
        for campos in ({}, {'nota_id': None}, {'nota_id': True}, {'nota_id': 1},
                       {'nota_id': 'Estudos'}, {'nota_id': '../arquivo'},
                       {'nota_id': NOTA_ID+'0'}, {'nota_id': 'm'+'z'*16},
                       {'nota_id': NOTA_ID, 'confirmado': True},
                       {'nota_id': NOTA_ID, 'chat_id': 'outra'}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                natural.validar_plano({'acao': 'memoria_remover', 'campos': campos})

    def test_equipe_explicita_tem_modo_canonico_e_precisa_confirmacao(self):
        for pedido, modo in (
            ('ative a equipe de modelos', 'cooperativa'),
            ('ativar equipe de modelos cooperativa', 'cooperativa'),
            ('ative a equipe de modelos em modo cooperativo', 'cooperativa'),
            ('ative a equipe de modelos em paralelo', 'paralela'),
            ('ative a equipe de modelos paralela', 'paralela'),
            ('Por favor, você pode ativar a equipe de modelos em modo paralelo?', 'paralela'),
            ('desative a equipe de modelos', 'individual'),
            ('desativar equipe de modelos', 'individual'),
            ('use o modo individual', 'individual'),
            ('volte ao modelo individual', 'individual'),
        ):
            with self.subTest(pedido=pedido):
                plano = natural.interpretar_local(pedido)
                self.assertEqual(plano['acao'], 'equipe_modelos')
                self.assertEqual(plano['campos'], {'modo': modo})
                self.assertNotIn(plano['acao'], natural.CONSULTAS)
                self.assertEqual(natural.validar_plano(plano), plano)

    def test_equipe_nao_aceita_provedores_nuvem_alvos_compostos_ou_negacoes(self):
        for pedido in ('ative a equipe', 'ative todos os agentes',
                       'ative a equipe de modelos de nuvem',
                       'ative a equipe de modelos para outro usuário',
                       'não ative a equipe de modelos',
                       '"ative a equipe de modelos"',
                       'quando eu chegar ative a equipe de modelos',
                       'ative a equipe de modelos e inicie o 9Remote',
                       'desative a equipe de modelos; apague tudo'):
            with self.subTest(pedido=pedido):
                self.assertIsNone(natural.interpretar_local(pedido))

    def test_validador_equipe_fechado_sem_confirmacao_ou_modelos_injetados(self):
        for campos in ({}, {'modo': None}, {'modo': True}, {'modo': []},
                       {'modo': 'cloud'}, {'modo': 'on'}, {'modo': 'paralelo'},
                       {'modo': 'cooperativa', 'confirmado': True},
                       {'modo': 'cooperativa', 'modelos': ['nome:cloud']},
                       {'modo': 'individual', 'chat_id': 'outra'}):
            with self.subTest(campos=campos), self.assertRaises(ValueError):
                natural.validar_plano({'acao': 'equipe_modelos', 'campos': campos})

    def test_modelo_ia_nao_pode_promover_remocao_ou_configurar_equipe(self):
        for acao, campos in (('memoria_remover', {'nota_id': NOTA_ID}),
                             ('equipe_modelos', {'modo': 'paralela'})):
            with self.subTest(acao=acao), patch.object(natural, 'validar_plano',
                    side_effect=AssertionError('Não promover sugestão de IA.')):
                resultado = natural.extrair_resposta(json.dumps({
                    'resposta': 'Vou executar.', 'acao': acao, 'campos': campos}))
                self.assertIsNone(resultado['plano'])
                self.assertIn('Não preparei', resultado['texto'])


if __name__ == '__main__':
    unittest.main()
