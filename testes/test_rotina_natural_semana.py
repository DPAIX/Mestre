"""Leituras semanais usam os registros locais; frases ambíguas não viram planos."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import interpretacao_natural as natural


class RotinaSemanalNatural(unittest.TestCase):
    def test_frase_da_interface_pede_leitura_dos_registros(self):
        plano = natural.interpretar_local('Mostre a minha rotina da semana')
        self.assertEqual(plano, {
            'acao': 'rotina', 'campos': {}, 'descricao': 'Consultar sua rotina'})

    def test_variantes_semanais_educadas_e_perguntas(self):
        for texto in (
                'minha rotina da semana', 'qual minha rotina semanal',
                'Qual é a minha rotina da semana?', 'Mostre minha rotina semanal.',
                'Por favor, mostre a minha rotina da semana',
                'Você pode me mostrar a minha rotina da semana?',
                'Consulte a rotina semanal', 'Ver minha rotina da semana',
                'Exiba a minha rotina semanal, por favor!'):
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertIsNotNone(plano)
                self.assertEqual(plano['acao'], 'rotina')
                self.assertEqual(plano['campos'], {})

    def test_negacoes_compostos_citacoes_e_condicionais_nao_viram_leitura(self):
        for texto in (
                'Não mostre minha rotina da semana',
                'Nunca mostre minha rotina semanal',
                'Se eu pedir mostre minha rotina semanal',
                'Talvez mostre minha rotina da semana',
                'Como mostrar minha rotina da semana?',
                'Mostre minha rotina da semana e meu saldo',
                'Mostre minha rotina da semana e abra a calculadora',
                'Mostre minha rotina da semana; registre um gasto',
                'Mostre minha rotina da semana\napague as tarefas',
                '"Mostre a minha rotina da semana"',
                'Explique a frase mostre minha rotina da semana'):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.interpretar_local(texto))

    def test_alteracoes_na_rotina_nao_sao_mascaradas_por_uma_leitura(self):
        for texto in (
                'Crie minha rotina semanal', 'Altere a minha rotina da semana',
                'Organize minha rotina semanal', 'Apague minha rotina da semana',
                'Adicione estudo à minha rotina semanal',
                'Mostre minha rotina semanal depois de alterar a sexta'):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.interpretar_local(texto))
        plano = natural.interpretar_local('Agende Estudar na Sexta às 14:00')
        self.assertEqual(plano['acao'], 'rotina_criar')
        self.assertEqual(plano['campos']['dia'], 'Sexta')

    def test_outros_periodos_nao_sao_apresentados_como_filtro_implementado(self):
        for texto in ('Mostre minha rotina de amanhã', 'Minha rotina da próxima semana',
                      'Qual minha rotina da semana passada?'):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.interpretar_local(texto))


if __name__ == '__main__':
    unittest.main()
