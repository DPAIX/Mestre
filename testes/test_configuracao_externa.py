"""Configurações compartilhadas com instalação externa, usando só arquivos fictícios."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agenda_google as agenda
import autorizar_google as google
import configurar_ia_local as ollama
import configurar_telegram as telegram


class ConfiguracaoExternaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.codigo = self.raiz / 'codigo novo'
        self.original = self.raiz / 'instalacao anterior'
        self.outro = self.raiz / 'outro perfil'
        for pasta in (self.codigo, self.original, self.outro):
            pasta.mkdir()
        self.token = '123456789:' + 'a' * 35
        self.conteudo = ('# preservar\nTELEGRAM_TOKEN=' + self.token + '\n'
                         'TELEGRAM_ALLOWED_USER_IDS=11\nOLLAMA_HABILITADO=0\n'
                         'OLLAMA_URL=http://127.0.0.1:11434\nOLLAMA_MODEL=fixture:antigo\n'
                         'OUTRA_CONFIGURACAO=fixture-preservada\n')
        self.local_env = self.codigo / '.env'
        self.externo = self.original / '.env'
        self.outro_env = self.outro / 'perfil.env'
        for caminho in (self.local_env, self.externo, self.outro_env):
            caminho.write_text(self.conteudo, encoding='utf-8')
        cliente = {'installed': {'client_id': 'fixture-google-client', 'client_secret': 'fixture-google-secret',
                                'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                                'token_uri': 'https://oauth2.googleapis.com/token'}}
        for pasta in (self.codigo, self.original, self.outro):
            (pasta / 'credentials.json').write_text(json.dumps(cliente), encoding='utf-8')
        for modulo in (telegram, ollama, google, agenda):
            p = patch.object(modulo, 'BASE', self.codigo)
            p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.externo)}, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(google, 'ler_env')
        p.start(); self.addCleanup(p.stop)
        self.saida = io.StringIO()
        p = contextlib.redirect_stdout(self.saida)
        p.__enter__(); self.addCleanup(p.__exit__, None, None, None)

    def test_todos_configuradores_alteram_env_externo_e_preservam_codigo(self):
        antes = self.local_env.read_bytes()
        telegram.atualizar_env({'TELEGRAM_ALLOWED_USER_IDS': '42'})
        ollama.atualizar_env('mistral:latest')
        google.salvar_caminho(self.original / 'credentials.json')
        texto = self.externo.read_text(encoding='utf-8')
        self.assertEqual(telegram.valores_env()['TELEGRAM_ALLOWED_USER_IDS'], '42')
        self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'mistral:latest')
        self.assertIn('GOOGLE_OAUTH_CREDENTIALS=' + str((self.original / 'credentials.json').resolve()), texto)
        self.assertIn('OUTRA_CONFIGURACAO=fixture-preservada', texto)
        self.assertIn('TELEGRAM_TOKEN=' + self.token, texto)
        self.assertNotIn('fixture-google-secret', texto)
        self.assertEqual(self.local_env.read_bytes(), antes)

    def test_caminho_explicito_tem_prioridade_sobre_env_do_processo(self):
        antes = self.externo.read_bytes()
        telegram.atualizar_env({'TELEGRAM_ALLOWED_USER_IDS': '84'}, path=str(self.outro_env))
        ollama.atualizar_env('llama3.2:latest', caminho=self.outro_env)
        google.salvar_caminho(self.outro / 'credentials.json', arquivo_env=self.outro_env)
        self.assertEqual(telegram.valores_env(self.outro_env)['TELEGRAM_ALLOWED_USER_IDS'], '84')
        self.assertEqual(ollama.valores_env(str(self.outro_env))['OLLAMA_MODEL'], 'llama3.2:latest')
        self.assertIn('GOOGLE_OAUTH_CREDENTIALS=' + str((self.outro / 'credentials.json').resolve()),
                      self.outro_env.read_text(encoding='utf-8'))
        self.assertEqual(self.externo.read_bytes(), antes)

    def test_defaults_sao_resolvidos_em_cada_chamada_apos_importacao(self):
        telegram.atualizar_env({'TELEGRAM_ALLOWED_USER_IDS': '21'})
        ollama.atualizar_env('primeiro:latest')
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.outro_env)}):
            self.assertEqual(telegram.valores_env()['TELEGRAM_ALLOWED_USER_IDS'], '11')
            self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'fixture:antigo')
            telegram.atualizar_env({'TELEGRAM_ALLOWED_USER_IDS': '22'})
            ollama.atualizar_env('segundo:latest')
            google.salvar_caminho(self.outro / 'credentials.json')
        self.assertEqual(telegram.valores_env()['TELEGRAM_ALLOWED_USER_IDS'], '21')
        self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'primeiro:latest')
        self.assertEqual(telegram.valores_env(self.outro_env)['TELEGRAM_ALLOWED_USER_IDS'], '22')
        self.assertEqual(ollama.valores_env(self.outro_env)['OLLAMA_MODEL'], 'segundo:latest')
        self.assertNotIn('GOOGLE_OAUTH_CREDENTIALS=', self.externo.read_text(encoding='utf-8'))

    def test_sem_variavel_do_processo_usa_env_junto_ao_codigo(self):
        antes = self.externo.read_bytes()
        with patch.dict(os.environ, {}, clear=True):
            telegram.atualizar_env({'TELEGRAM_ALLOWED_USER_IDS': '31'})
            ollama.atualizar_env('local:latest')
            google.salvar_caminho(self.codigo / 'credentials.json')
            self.assertEqual(telegram.valores_env()['TELEGRAM_ALLOWED_USER_IDS'], '31')
            self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'local:latest')
            self.assertEqual(agenda.encontrar_credenciais(), (self.codigo / 'credentials.json').resolve())
        self.assertEqual(self.externo.read_bytes(), antes)

    def test_assistente_telegram_reaproveita_token_do_env_ativo(self):
        antes = self.local_env.read_bytes()
        with patch.object(telegram.getpass, 'getpass', return_value=''), patch('builtins.input', return_value='52'):
            self.assertEqual(telegram.assistente(), 0)
        self.assertEqual(telegram.valores_env()['TELEGRAM_TOKEN'], self.token)
        self.assertEqual(telegram.valores_env()['TELEGRAM_ALLOWED_USER_IDS'], '52')
        self.assertEqual(self.local_env.read_bytes(), antes)
        self.assertNotIn(self.token, self.saida.getvalue())

    def test_cli_ollama_sem_caminho_explicito_grava_no_env_ativo(self):
        antes = self.local_env.read_bytes()
        with patch.object(ollama, 'listar_modelos', return_value=['mistral:latest']), patch.object(ollama.subprocess, 'run') as baixar:
            self.assertEqual(ollama.main(['--modelo', 'mistral']), 0)
        baixar.assert_not_called()
        self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'mistral:latest')
        self.assertEqual(ollama.valores_env()['OLLAMA_HABILITADO'], '1')
        self.assertEqual(self.local_env.read_bytes(), antes)

    def test_helpers_ollama_sem_caminho_reaproveitam_o_mesmo_env(self):
        antes = self.local_env.read_bytes()
        with patch.object(ollama, 'listar_catalogo', return_value=[{'nome': 'llama3.2:latest', 'nuvem': False}]):
            self.assertEqual(ollama.usar_existente(), 'llama3.2:latest')
        with patch.object(ollama, 'listar_modelos', return_value=['mistral:latest']), patch.object(ollama.subprocess, 'run') as baixar:
            self.assertEqual(ollama.baixar_modelo('mistral:latest'), 'mistral:latest')
        baixar.assert_not_called()
        self.assertEqual(ollama.valores_env()['OLLAMA_MODEL'], 'mistral:latest')
        self.assertEqual(self.local_env.read_bytes(), antes)

    def test_google_relativo_e_padrao_resolvem_junto_ao_env_externo(self):
        self.assertEqual(agenda.validar_credenciais('"credentials.json"'),
                         (self.original / 'credentials.json').resolve())
        self.assertEqual(agenda.encontrar_credenciais(), (self.original / 'credentials.json').resolve())
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.outro_env)}):
            self.assertEqual(agenda.encontrar_credenciais(), (self.outro / 'credentials.json').resolve())
        with patch.dict(os.environ, {'GOOGLE_OAUTH_CREDENTIALS': 'credentials.json'}):
            self.assertEqual(agenda.encontrar_credenciais(), (self.original / 'credentials.json').resolve())

    def test_cli_google_escolha_relativa_salva_env_externo_sem_autenticacao_real(self):
        antes = self.local_env.read_bytes()
        with patch.object(agenda, 'autorizacao', return_value=True) as autorizar:
            self.assertEqual(google.main(['credentials.json'], interativo=False), 0)
        autorizar.assert_called_once_with((self.original / 'credentials.json').resolve())
        self.assertIn('GOOGLE_OAUTH_CREDENTIALS=' + str((self.original / 'credentials.json').resolve()),
                      self.externo.read_text(encoding='utf-8'))
        self.assertEqual(self.local_env.read_bytes(), antes)

    def test_verificacao_google_externa_nao_grava_ou_abre_navegador(self):
        antes = self.externo.read_bytes()
        with patch.object(agenda, 'autorizacao') as autorizar:
            self.assertEqual(google.main(['--verificar'], interativo=False), 0)
        autorizar.assert_not_called()
        self.assertEqual(self.externo.read_bytes(), antes)

    def test_telegram_seletor_relativo_falha_sem_fallback_ou_segredos(self):
        antes = self.local_env.read_bytes()
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': 'fixture-nao-expor.env'}), \
                patch.object(sys, 'argv', ['configurar_telegram.py', '--verificar']):
            self.assertEqual(telegram.main(), 2)
        self.assertEqual(self.local_env.read_bytes(), antes)
        self.assertNotIn('fixture-nao-expor.env', self.saida.getvalue())
        self.assertNotIn(self.token, self.saida.getvalue())
        self.assertNotIn('Traceback', self.saida.getvalue())

    def test_google_seletor_relativo_falha_sem_navegador_ou_fallback(self):
        antes = self.local_env.read_bytes()
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': 'fixture-nao-expor.env'}), \
                patch.object(agenda, 'autorizacao') as autorizar:
            self.assertEqual(google.main(['--verificar'], interativo=False), 2)
        autorizar.assert_not_called()
        self.assertEqual(self.local_env.read_bytes(), antes)
        self.assertNotIn('fixture-nao-expor.env', self.saida.getvalue())
        self.assertNotIn('Traceback', self.saida.getvalue())

    def test_ollama_seletor_relativo_falha_sem_rede_ou_fallback(self):
        antes = self.local_env.read_bytes()
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': 'fixture-nao-expor.env'}), \
                patch.object(ollama, 'listar_catalogo') as catalogo:
            self.assertEqual(ollama.main(['--listar']), 2)
        catalogo.assert_not_called()
        self.assertEqual(self.local_env.read_bytes(), antes)
        self.assertNotIn('fixture-nao-expor.env', self.saida.getvalue())
        self.assertNotIn('Traceback', self.saida.getvalue())


if __name__ == '__main__':
    unittest.main()
