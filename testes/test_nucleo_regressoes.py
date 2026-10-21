import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import nucleo


class PersistenciaRegressoes(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.patch = patch.object(nucleo, 'DADOS', Path(self.temp.name))
        self.patch.start()
        self.addCleanup(self.patch.stop)
        nucleo.gravar_json('gestao_vida.json', {
            'rotina': [], 'financeiro': {'saldo': 10, 'movimentacoes': []},
        })

    def test_excecoes_e_aliases_de_chave_sao_redigidos(self):
        # Valores fictícios; nenhuma credencial de usuário é carregada.
        chave = 'sk-proj-' + 'Z' * 35
        self.assertNotIn(chave, str(nucleo.redigir(RuntimeError(chave))))
        obj = nucleo.redigir({
            'ANTHROPIC_API_KEY': 'valor-ficticio-a',
            'GOOGLE_API_KEY': 'valor-ficticio-b',
            'Authorization': 'valor-ficticio-c',
        })
        self.assertEqual(set(obj.values()), {'[REDACTADO]'})

    def test_token_telegram_sem_prefixo_aa_tambem_e_redigido(self):
        token = '1234567890:' + 'B' * 35
        self.assertNotIn(token, nucleo.redigir('Falha ao acessar /bot' + token + '/getMe'))

    def test_evento_redige_todos_os_campos(self):
        chave = 'sk-proj-' + 'Z' * 35
        nucleo.registrar(chave, chave, RuntimeError(chave), chave)
        texto = (nucleo.DADOS / 'log_acoes_e_erros.json').read_text(encoding='utf-8')
        self.assertNotIn(chave, texto)

    def test_gravacao_rejeita_nao_finitos_sem_perder_original(self):
        original = (nucleo.DADOS / 'gestao_vida.json').read_bytes()
        for valor in (float('nan'), float('inf'), float('-inf')):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    nucleo.gravar_json('gestao_vida.json', {'saldo': valor})
                self.assertEqual((nucleo.DADOS / 'gestao_vida.json').read_bytes(), original)
                self.assertFalse(list(nucleo.DADOS.glob('*.tmp')))

    def test_leitura_rejeita_nao_finitos_sem_alterar_arquivo(self):
        for constante in ('NaN', 'Infinity', '-Infinity', '1e9999'):
            with self.subTest(constante=constante):
                path = nucleo.DADOS / 'invalido.json'
                original = ('{"saldo":' + constante + '}').encode()
                path.write_bytes(original)
                with self.assertLogs(nucleo._LOG,level='ERROR') as logs,self.assertRaises(ValueError):
                    nucleo.ler_json('invalido.json', {})
                self.assertIn('invalido.json',logs.output[0])
                self.assertEqual(path.read_bytes(), original)

    def test_subcentavos_nao_alteram_saldo_nem_historico(self):
        antes = nucleo.vida()
        for valor in ('0,001', '1.005', '0.009'):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    nucleo.movimentar('entrada', valor, 'teste')
                self.assertEqual(nucleo.vida(), antes)

    def test_saldo_e_historico_usam_os_mesmos_centavos(self):
        saldo = nucleo.movimentar('entrada', '0,10', 'teste')
        self.assertEqual(saldo, 10.10)
        saldo = nucleo.movimentar('saida', '0,30', 'teste')
        self.assertEqual(saldo, 9.80)
        self.assertEqual([m['valor'] for m in nucleo.vida()['financeiro']['movimentacoes']], [.1, .3])

    def test_saldo_legado_invalido_e_preservado(self):
        for saldo in ('NaN', 'Infinity', 'banana'):
            with self.subTest(saldo=saldo):
                nucleo.gravar_json('gestao_vida.json', {
                    'financeiro': {'saldo': saldo, 'movimentacoes': []},
                })
                original = (nucleo.DADOS / 'gestao_vida.json').read_bytes()
                with self.assertRaises(ValueError):
                    nucleo.movimentar('entrada', 1, 'teste')
                self.assertEqual((nucleo.DADOS / 'gestao_vida.json').read_bytes(), original)

    def test_exportacoes_no_mesmo_segundo_sao_independentes(self):
        agora = nucleo.dt.datetime.now()
        with patch.object(nucleo.dt, 'datetime', wraps=nucleo.dt.datetime) as relogio:
            relogio.now.return_value = agora
            primeiro = nucleo.exportacao_segura()
            original = primeiro.read_bytes()
            nucleo.movimentar('entrada', 1, 'teste')
            segundo = nucleo.exportacao_segura()
        self.assertNotEqual(primeiro, segundo)
        self.assertEqual(primeiro.read_bytes(), original)
        with zipfile.ZipFile(primeiro) as z:
            self.assertEqual(json.loads(z.read('gestao_vida.json'))['financeiro']['saldo'], 10)
        with zipfile.ZipFile(segundo) as z:
            self.assertEqual(json.loads(z.read('gestao_vida.json'))['financeiro']['saldo'], 11)


if __name__ == '__main__':
    unittest.main()
