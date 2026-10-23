"""OAuth Google com arquivos fictícios e módulos simulados, sem rede/navegador."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agenda_google as agenda
import autorizar_google as autorizar


class GoogleAgendaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name) / 'projeto com espaço'
        self.base.mkdir()
        self.dados = self.base / 'dados_ficticios'
        self.dados.mkdir()
        self.token = self.dados / 'token_google.json'
        self.env = self.base / '.env'
        self.env.write_bytes(b'# preservar\r\nOUTRA_OPCAO=fixture-preservada\r\n')
        self.cliente = {
            'client_id': 'fixture-client-google', 'client_secret': 'fixture-secret-google',
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
        }
        self.cred = self.base / 'credentials.json'
        self.cred.write_text(json.dumps({'installed': self.cliente}), encoding='utf-8')
        for alvo, valor in ((agenda, self.base), (autorizar, self.base)):
            p = patch.object(alvo, 'BASE', valor)
            p.start(); self.addCleanup(p.stop)
        for nome, valor in (('DADOS', self.dados), ('TOKEN', self.token)):
            p = patch.object(agenda, nome, valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(agenda, 'registrar')
        self.registrar = p.start(); self.addCleanup(p.stop)
        p = patch.object(autorizar, 'ler_env')
        self.ler_env = p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {}, clear=True)
        p.start(); self.addCleanup(p.stop)
        self.saida = io.StringIO()
        p = contextlib.redirect_stdout(self.saida)
        p.__enter__(); self.addCleanup(p.__exit__, None, None, None)

    def mock_flow(self):
        pacote = types.ModuleType('google_auth_oauthlib')
        pacote.__path__ = []
        modulo = types.ModuleType('google_auth_oauthlib.flow')
        modulo.InstalledAppFlow = MagicMock()
        pacote.flow = modulo
        p = patch.dict(sys.modules, {'google_auth_oauthlib': pacote,
                                    'google_auth_oauthlib.flow': modulo})
        p.start(); self.addCleanup(p.stop)
        return modulo.InstalledAppFlow

    def mock_calendar(self):
        nomes = ('google', 'google.oauth2', 'google.oauth2.credentials',
                 'google.auth', 'google.auth.transport', 'google.auth.transport.requests',
                 'googleapiclient', 'googleapiclient.discovery')
        modulos = {nome: types.ModuleType(nome) for nome in nomes}
        for nome, modulo in modulos.items():
            modulo.__path__ = []
            if '.' in nome:
                pai, filho = nome.rsplit('.', 1)
                setattr(modulos[pai], filho, modulo)
        credenciais = MagicMock()
        requisicao = MagicMock()
        build = MagicMock()
        modulos['google.oauth2.credentials'].Credentials = credenciais
        modulos['google.auth.transport.requests'].Request = requisicao
        modulos['googleapiclient.discovery'].build = build
        p = patch.dict(sys.modules, modulos)
        p.start(); self.addCleanup(p.stop)
        return credenciais, requisicao, build

    def test_caminhos_relativos_aspas_variavel_independem_do_cwd(self):
        outro = self.base / 'outro'
        outro.mkdir()
        anterior = os.getcwd()
        try:
            os.chdir(outro)
            for nome in ('credentials.json', '"credentials.json"', "'credentials.json'"):
                with self.subTest(nome=nome):
                    self.assertEqual(agenda.validar_credenciais(nome), self.cred.resolve())
            with patch.dict(os.environ, {'GOOGLE_FIXTURE_DIR': str(self.base)}):
                self.assertEqual(agenda.validar_credenciais('%GOOGLE_FIXTURE_DIR%/credentials.json'),
                                 self.cred.resolve())
        finally:
            os.chdir(anterior)

    def test_descobre_arquivo_padrao_sem_substituir_configuracao_invalida(self):
        self.assertEqual(agenda.encontrar_credenciais(), self.cred.resolve())
        with patch.dict(os.environ, {'GOOGLE_OAUTH_CREDENTIALS': 'ausente.json'}):
            with self.assertRaises(agenda.FalhaAgenda):
                agenda.encontrar_credenciais()
            self.assertEqual(agenda.encontrar_credenciais(self.cred), self.cred.resolve())

    def test_rejeita_web_conta_servico_json_invalido_e_urls_externas(self):
        invalido = self.base / 'invalido.json'
        conteudos = [{'web': self.cliente}, {'type': 'service_account'}, {'installed': {}}, [],
                     {'installed': {**self.cliente, 'auth_uri': 'https://evil.invalid/oauth'}},
                     {'installed': {**self.cliente, 'token_uri': 'http://oauth2.googleapis.com/token'}},
                     {'installed': {**self.cliente, 'token_uri': 'https://fixture@oauth2.googleapis.com/token'}}]
        for conteudo in conteudos:
            with self.subTest(conteudo=conteudo):
                invalido.write_text(json.dumps(conteudo), encoding='utf-8')
                with self.assertRaises(agenda.FalhaAgenda) as erro:
                    agenda.validar_credenciais(invalido)
                self.assertNotIn(self.cliente['client_secret'], str(erro.exception))
        for bruto in (b'{JSON-invalido-fixture-secret-google', b'x' * (agenda.LIMITE_CREDENCIAIS + 1)):
            invalido.write_bytes(bruto)
            with self.assertRaises(agenda.FalhaAgenda) as erro:
                agenda.validar_credenciais(invalido)
            self.assertNotIn(self.cliente['client_secret'], str(erro.exception))

    def test_cli_verificar_nao_autoriza_nem_grava_configuracao(self):
        antes = self.env.read_bytes()
        with patch.object(agenda, 'autorizacao') as autorizar_conta:
            self.assertEqual(autorizar.main(['--verificar', str(self.cred)], arquivo_env=self.env), 0)
        autorizar_conta.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertFalse(self.token.exists())
        self.assertIn('Nenhuma conta', self.saida.getvalue())
        self.assertNotIn(self.cliente['client_secret'], self.saida.getvalue())
        self.ler_env.assert_called_once_with()

    def test_cli_escolha_explicita_preserva_outras_configuracoes(self):
        self.env.write_bytes(b'\xef\xbb\xbf# preservar\r\nOUTRA_OPCAO=fixture-preservada\r\n'
                             b'GOOGLE_OAUTH_CREDENTIALS=antigo\r\nGOOGLE_OAUTH_CREDENTIALS=duplicado\r\n')
        with patch.object(agenda, 'autorizacao', return_value=True) as autorizar_conta:
            self.assertEqual(autorizar.main([str(self.cred)], arquivo_env=self.env), 0)
        autorizar_conta.assert_called_once_with(self.cred.resolve())
        bruto = self.env.read_bytes()
        self.assertTrue(bruto.startswith(b'\xef\xbb\xbf'))
        texto = bruto.decode('utf-8-sig')
        self.assertIn('OUTRA_OPCAO=fixture-preservada\r\n', texto)
        self.assertEqual(texto.count('GOOGLE_OAUTH_CREDENTIALS='), 1)
        self.assertIn('GOOGLE_OAUTH_CREDENTIALS=' + str(self.cred.resolve()) + '\r\n', texto)
        self.assertNotIn(self.cliente['client_secret'], texto)

    def test_arquivo_explicito_invalido_preserva_env_e_nao_abre_fluxo(self):
        antes = self.env.read_bytes()
        invalido = self.base / 'conta_web.json'
        invalido.write_text(json.dumps({'web': self.cliente}), encoding='utf-8')
        with patch.object(agenda, 'autorizacao') as autorizar_conta:
            self.assertEqual(autorizar.main([str(invalido)], interativo=False, arquivo_env=self.env), 2)
        autorizar_conta.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertNotIn('Traceback', self.saida.getvalue())
        self.assertNotIn(self.cliente['client_secret'], self.saida.getvalue())

    def test_ausencia_e_cancelamento_nao_autorizam_nem_criam_env(self):
        self.cred.unlink()
        antes = self.env.read_bytes()
        with patch.object(agenda, 'autorizacao') as autorizar_conta, patch('builtins.input', return_value='') as entrada:
            self.assertEqual(autorizar.main([], interativo=False, arquivo_env=self.env), 2)
            entrada.assert_not_called()
            self.assertEqual(autorizar.main([], interativo=True, arquivo_env=self.env), 2)
            entrada.assert_called_once()
        autorizar_conta.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('Desktop app', self.saida.getvalue())
        self.assertNotIn('Traceback', self.saida.getvalue())

    def test_fluxo_oauth_salva_token_com_escopo_somente_leitura(self):
        instalado = self.mock_flow()
        flow = instalado.from_client_secrets_file.return_value
        texto = json.dumps({'token': 'fixture-oauth-token', 'refresh_token': 'fixture-refresh'})
        flow.run_local_server.return_value.to_json.return_value = texto
        self.assertTrue(agenda.autorizacao(self.cred))
        instalado.from_client_secrets_file.assert_called_once_with(str(self.cred.resolve()), agenda.ESCOPOS)
        self.assertEqual(agenda.ESCOPOS, ['https://www.googleapis.com/auth/calendar.readonly'])
        flow.run_local_server.assert_called_once_with(port=0)
        self.assertEqual(self.token.read_text(encoding='utf-8'), texto)
        self.assertEqual(list(self.dados.glob('.token_google.*.tmp')), [])
        self.assertNotIn('fixture-oauth-token', self.saida.getvalue())

    def test_falha_oauth_nao_expoe_erro_bruto_nem_apaga_token_anterior(self):
        anterior = b'{"token":"fixture-anterior"}'
        self.token.write_bytes(anterior)
        instalado = self.mock_flow()
        instalado.from_client_secrets_file.return_value.run_local_server.side_effect = RuntimeError('fixture-secret-google')
        self.assertEqual(autorizar.main([str(self.cred)], arquivo_env=self.env), 2)
        self.assertEqual(self.token.read_bytes(), anterior)
        self.assertNotIn('fixture-secret-google', self.saida.getvalue())
        self.assertNotIn('Traceback', self.saida.getvalue())
        self.assertNotIn('autorizado para consultas', self.saida.getvalue())
        self.registrar.assert_not_called()

    def test_falha_troca_atomica_preserva_token_e_remove_temporario(self):
        anterior = b'{"token":"fixture-anterior"}'
        self.token.write_bytes(anterior)
        with patch.object(agenda.os, 'replace', side_effect=OSError('fixture-erro')):
            with self.assertRaises(OSError):
                agenda._gravar_token('{"token":"fixture-novo"}')
        self.assertEqual(self.token.read_bytes(), anterior)
        self.assertEqual(list(self.dados.glob('.token_google.*.tmp')), [])

    def test_refresh_com_falha_preserva_token_e_nao_consulta_eventos(self):
        anterior = b'{"token":"fixture-anterior"}'
        self.token.write_bytes(anterior)
        classe, requisicao, build = self.mock_calendar()
        creds = classe.from_authorized_user_file.return_value
        creds.valid = False; creds.expired = True; creds.refresh_token = 'fixture-refresh'
        creds.refresh.side_effect = RuntimeError('fixture-secret-google')
        with self.assertRaises(agenda.FalhaAgenda) as erro:
            agenda.proximos_eventos()
        self.assertNotIn('fixture-secret-google', str(erro.exception))
        self.assertEqual(self.token.read_bytes(), anterior)
        requisicao.assert_called_once_with(); build.assert_not_called()

    def test_refresh_consulta_leitura_e_fecha_servico(self):
        self.token.write_text('{"token":"fixture-anterior"}', encoding='utf-8')
        classe, requisicao, build = self.mock_calendar()
        creds = classe.from_authorized_user_file.return_value
        creds.valid = False; creds.expired = True; creds.refresh_token = 'fixture-refresh'
        creds.refresh.side_effect = lambda pedido: setattr(creds, 'valid', True)
        creds.to_json.return_value = '{"token":"fixture-novo"}'
        servico = build.return_value
        servico.events.return_value.list.return_value.execute.return_value = {
            'items': [{'summary': 'Evento fictício', 'start': {'date': '2026-10-22'}, 'end': {'date': '2026-10-23'}}]}
        self.assertEqual(agenda.proximos_eventos(3), [{'titulo': 'Evento fictício', 'inicio': '2026-10-22', 'fim': '2026-10-23'}])
        kwargs = servico.events.return_value.list.call_args.kwargs
        self.assertEqual(kwargs['calendarId'], 'primary'); self.assertEqual(kwargs['maxResults'], 3)
        self.assertTrue(kwargs['singleEvents'])
        classe.from_authorized_user_file.assert_called_once_with(str(self.token), agenda.ESCOPOS)
        self.assertEqual(self.token.read_text(encoding='utf-8'), '{"token":"fixture-novo"}')
        servico.close.assert_called_once_with()


if __name__ == '__main__':
    unittest.main()
