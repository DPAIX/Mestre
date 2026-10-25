"""Preparação local explícita, sem inferência ou execução durante o planejamento."""
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interpretacao_natural as natural


class IntencoesConfiguracao(unittest.TestCase):
    def test_frase_exata_da_imagem_e_variantes_preparam_configuracao_local(self):
        exemplos = ('faça as configurações necessárias',
                    'realize as configurações necessárias',
                    'Faça todas as configurações necessárias!',
                    'configure o assistente', 'configurar o assistente',
                    'prepare as integrações', 'configure as integrações do assistente',
                    'faça a configuração inicial do assistente', 'prepare o MeuControlePC')
        for texto in exemplos:
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertEqual(plano['acao'], 'configurar_assistente')
                self.assertEqual(plano['campos'], {})
                self.assertEqual(natural.validar_plano(plano), plano)
                self.assertLessEqual(len(plano['descricao']), 500)

    def test_cortesia_acentos_e_espacos_nao_exigem_comandos(self):
        for texto in ('Por favor, faça as configurações necessárias.',
                      'Você pode configurar o assistente?',
                      'FAÇA   AS   CONFIGURAÇÕES  NECESSÁRIAS',
                      'configure o assistente, por favor!'):
            with self.subTest(texto=texto):
                self.assertEqual(natural.interpretar_local(texto)['acao'], 'configurar_assistente')

    def test_consulta_de_configuracao_e_leitura_local(self):
        for texto in ('diagnosticar a configuração', 'diagnostique a configuração local',
                      'mostre a configuração do assistente',
                      'verifique as configurações do assistente',
                      'consulte a configuração atual do assistente'):
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertEqual(plano['acao'], 'configuracao')
                self.assertEqual(plano['campos'], {})
                self.assertIn(plano['acao'], natural.CONSULTAS)
        self.assertNotIn('configurar_assistente', natural.CONSULTAS)

    def test_negacoes_citacoes_condicoes_compostos_e_alvos_especificos_nao_sao_absorvidos(self):
        exemplos = ('não faça as configurações necessárias',
                    'nunca configure o assistente', 'talvez configure o assistente',
                    'se eu pedir configure o assistente',
                    'quando eu chegar configure o assistente',
                    '"faça as configurações necessárias"',
                    '`configure o assistente`', 'explique a frase configure o assistente',
                    'faça as configurações necessárias e abra o Explorer',
                    'configure o assistente; execute meu script',
                    'configure o assistente\ninicie o 9Remote',
                    'configure o assistente para usar a nuvem',
                    'configure o modelo llama3.2:latest',
                    'configure o 9Remote', 'prepare as integrações e reinicie o PC',
                    'mostre a configuração do Windows',
                    'faça as configurações necessárias com powershell',
                    'configure tudo', '/configure o assistente')
        for texto in exemplos:
            with self.subTest(texto=texto):
                self.assertIsNone(natural.interpretar_local(texto))

    def test_alvos_existentes_continuam_com_planos_especificos(self):
        self.assertEqual(natural.interpretar_local('configure o OpenCode')['acao'], 'agente_abrir')
        self.assertEqual(natural.interpretar_local('use mistral como padrão')['acao'], 'modelo_padrao')
        self.assertEqual(natural.interpretar_local('inicie o 9Remote')['acao'], '9stack')

    def test_validador_rejeita_campos_extras_e_tipos_antes_de_qualquer_execucao(self):
        for acao in ('configurar_assistente', 'configuracao'):
            for campos in (None, [], {'confirmado': True}, {'modelo': 'gemma4:31b-cloud'},
                           {'comando': 'shell'}, {'iniciar_remoto': True}):
                with self.subTest(acao=acao, campos=campos), self.assertRaises(ValueError):
                    natural.validar_plano({'acao': acao, 'campos': campos})

    def test_plano_e_puro_sem_diagnosticar_ou_abrir_configuracao(self):
        import configuracao_assistente as configuracao
        with patch.object(configuracao, 'resumo_configuracao', side_effect=AssertionError('Somente plano.')), \
                patch.object(configuracao, 'abrir_configuracao', side_effect=AssertionError('Não executar.')):
            plano = natural.interpretar_local('faça as configurações necessárias')
            self.assertEqual(natural.validar_plano(plano), plano)

    def test_sugestao_da_ia_nao_pode_abrir_preparacao(self):
        import configuracao_assistente as configuracao
        resposta = json.dumps({'resposta': 'Vou configurar.', 'acao': 'configurar_assistente', 'campos': {}})
        with patch.object(configuracao, 'preparar_configuracao', side_effect=AssertionError('Não promover sugestão da IA.')):
            resultado = natural.extrair_resposta(resposta)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Não preparei', resultado['texto'])

    def test_capacidades_descrevem_preparacao_sem_promessa_de_contas_configuradas(self):
        texto = natural.texto_capacidades()
        self.assertIn('Configuração local guiada', texto)
        self.assertIn('faça as configurações necessárias', texto)
        self.assertIn('sem consultar modelos', texto)
        self.assertNotIn('contas já configuradas', texto)


if __name__ == '__main__':
    unittest.main()
