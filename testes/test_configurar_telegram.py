import tempfile
import unittest
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from configurar_telegram import atualizar_env, valores_env, validar_token, validar_ids, verificar

class TesteConfiguracaoTelegram(unittest.TestCase):
    def test_token_invalido_nao_passa(self):
        for token in ['', 'COLOQUE_NOVO_TOKEN_AQUI', 'foo:bar', '000:xyz', '123456:']:
            self.assertFalse(validar_token(token))
    def test_token_sintaxe(self):
        self.assertTrue(validar_token('123456789:'+'a'*35))
    def test_ids(self):
        self.assertTrue(validar_ids(''))
        self.assertTrue(validar_ids('1234567,9876543'))
        self.assertFalse(validar_ids('SEU_ID_NUMERICO'))
        self.assertFalse(validar_ids('123,usuario'))
    def test_preservacao_configs(self):
        with tempfile.TemporaryDirectory() as pasta:
            alvo=Path(pasta)/'.env'
            alvo.write_text('# cabecalho\nGEMINI_API_KEY=abc\nTELEGRAM_TOKEN=velho\nTELEGRAM_TOKEN=duplicado\nTELEGRAM_ALLOWED_USER_IDS=SEU_ID_NUMERICO\n', encoding='utf-8')
            atualizado={'TELEGRAM_TOKEN':'123456789:'+'b'*32, 'TELEGRAM_ALLOWED_USER_IDS':'123456789'}
            atualizar_env(atualizado, alvo)
            conteudo=alvo.read_text(encoding='utf-8')
            self.assertEqual(conteudo.count('TELEGRAM_TOKEN='),1)
            self.assertIn('GEMINI_API_KEY=abc',conteudo)
            self.assertEqual(valores_env(alvo),atualizado)
            self.assertTrue(verificar(alvo))

if __name__=='__main__':unittest.main()
