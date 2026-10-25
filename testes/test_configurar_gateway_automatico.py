"""Preparação 9Router com banco/credenciais fictícios; nenhuma geração real."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configurar_gateway_automatico as gateway


CHAVE_FICTICIA = 'fixture-dedicada-nao-real'
ID_FICTICIO = '00000000-0000-4000-8000-000000000001'


class PreparacaoGateway(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raiz = self.base / '9router'
        (self.raiz / 'db').mkdir(parents=True)
        (self.raiz / 'auth').mkdir()
        (self.raiz / 'machine-id').write_text('fixture-machine-id', encoding='utf-8')
        (self.raiz / 'auth' / 'cli-secret').write_text('fixture-cli-secret', encoding='utf-8')
        self.env = self.base / 'config' / '.env'
        self.env.parent.mkdir()
        self.env.write_text('OUTRO=preservar\nNINE_ROUTER_API_KEY=fixture-anterior\n', encoding='utf-8')
        self.db = self.raiz / 'db' / 'data.sqlite'
        with sqlite3.connect(self.db) as db:
            db.executescript('''
                CREATE TABLE _meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO _meta VALUES('schemaVersion','2');
                CREATE TABLE apiKeys(id TEXT,key TEXT,name TEXT,isActive INTEGER,accessRestricted INTEGER,accessAllow TEXT);
                CREATE TABLE combos(id TEXT,name TEXT,kind TEXT,models TEXT);
                CREATE TABLE providerConnections(id TEXT,provider TEXT,isActive INTEGER,authType TEXT,data TEXT);
                INSERT INTO providerConnections VALUES('fixture-conn','gemini-cli',1,'oauth','{"accessToken":"fixture-oauth-nao-real"}');
                INSERT INTO combos VALUES('fixture-combo','Minha Equipe','llm','["gc/gemini-flash"]');
            ''')
        ambiente = patch.dict(os.environ, {}, clear=True)
        ambiente.start();self.addCleanup(ambiente.stop)
        self.original_db = hashlib.sha256(self.db.read_bytes()).digest()

    def configurar(self, **opcoes):
        return gateway.configurar_gateway(caminho_env=self.env, diretorio_gateway=self.raiz,
                                            autorizado=True, **opcoes)

    def nova_chave(self):
        return {'name': gateway.NOME_CHAVE, 'key': CHAVE_FICTICIA, 'id': ID_FICTICIO}

    def chave_existente(self):
        return dict(self.nova_chave(), isActive=True)

    def rede_criacao(self, modelos=None):
        return [
            {'keys': [{'name': 'Default Key', 'key': 'fixture-exposta-nao-reusar', 'isActive': True},
                      {'name': 'Assistente', 'key': 'fixture-tambem-nao-reusar', 'isActive': True}]},
            self.nova_chave(),
            {'data': [{'id': ident} for ident in (modelos or ['Minha Equipe'])]},
        ]

    def assert_sem_segredos(self, resultado):
        publico = json.dumps(resultado)
        for valor in (CHAVE_FICTICIA, 'fixture-anterior', 'fixture-cli-secret',
                      'fixture-oauth-nao-real', 'fixture-exposta-nao-reusar', 'fixture-tambem-nao-reusar'):
            self.assertNotIn(valor, publico)
        self.assertEqual(hashlib.sha256(self.db.read_bytes()).digest(), self.original_db)
        self.assertFalse(resultado['geracao_testada'])

    def test_autorizacao_estrita_antes_de_qualquer_leitura(self):
        with patch.object(gateway, '_opcoes') as ler:
            for autorizado in (False, None, 1, 'sim'):
                with self.assertRaises(PermissionError):
                    gateway.configurar_gateway(autorizado=autorizado)
            ler.assert_not_called()

    def test_planejamento_nao_consulta_rede_nem_segredos(self):
        bruto = self.env.read_bytes()
        with patch.object(gateway, '_requisicao') as rede, patch.object(gateway, '_token_cli') as token:
            resultado = gateway.planejar_gateway(caminho_env=self.env, diretorio_gateway=self.raiz)
        self.assertEqual(resultado['modelo'], 'Minha Equipe')
        self.assertFalse(resultado['configurado']);self.assertFalse(resultado['chave_configurada'])
        rede.assert_not_called();token.assert_not_called()
        self.assertEqual(self.env.read_bytes(), bruto);self.assert_sem_segredos(resultado)

    def test_cria_chave_apenas_pela_api_e_guarda_sem_exibir(self):
        stdout = StringIO()
        with redirect_stdout(stdout), patch.object(gateway, '_requisicao', side_effect=self.rede_criacao()) as rede:
            resultado = self.configurar()
        self.assertTrue(resultado['configurado']);self.assertTrue(resultado['chave_configurada'])
        self.assertEqual(resultado['modelo'], 'Minha Equipe')
        self.assertEqual(stdout.getvalue(), '')
        self.assertEqual([c.args[2] for c in rede.call_args_list], ['/api/keys', '/api/keys', '/v1/models'])
        self.assertEqual(rede.call_args_list[1].kwargs, {'corpo': {'name': gateway.NOME_CHAVE}})
        self.assertEqual(rede.call_args_list[2].kwargs, {'chave': CHAVE_FICTICIA})
        env = self.env.read_text(encoding='utf-8')
        self.assertIn('OUTRO=preservar', env)
        self.assertIn('NINE_ROUTER_API_KEY=' + CHAVE_FICTICIA, env)
        self.assertIn('NINE_ROUTER_HABILITADO=1', env)
        self.assertNotIn('fixture-anterior', env)
        self.assertEqual(os.environ['NINE_ROUTER_API_KEY'], CHAVE_FICTICIA)
        recibo = self.env.parent / '.meucontrolepc_9router_chave.json'
        self.assertEqual(json.loads(recibo.read_text())['id'], ID_FICTICIO)
        self.assertNotIn(CHAVE_FICTICIA, recibo.read_text())
        self.assert_sem_segredos(resultado)

    def test_repetir_reaproveita_so_dedicada_com_comprovante_sem_criar_outra(self):
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao()):self.configurar()
        with patch.object(gateway, '_requisicao', side_effect=[{'keys': [self.chave_existente()]}, {'data': [{'id': 'Minha Equipe'}]}]) as rede:
            resultado = self.configurar()
        self.assertTrue(resultado['configurado']);self.assertEqual(rede.call_count, 2)
        self.assertTrue(all('corpo' not in c.kwargs for c in rede.call_args_list))
        self.assert_sem_segredos(resultado)

    def test_chave_de_nome_dedicado_sem_comprovante_nao_e_reusada(self):
        original = self.env.read_bytes()
        with patch.object(gateway, '_requisicao', return_value={'keys': [self.chave_existente()]}) as rede:
            resultado = self.configurar()
        self.assertFalse(resultado['configurado']);self.assertFalse(resultado['chave_configurada'])
        self.assertIn('comprovante', resultado['pendencias'][0]);self.assertEqual(rede.call_count, 1)
        self.assertEqual(self.env.read_bytes(), original);self.assert_sem_segredos(resultado)

    def test_timeout_de_criacao_nao_repete_post_e_reconcilia_resposta_perdida(self):
        with patch.object(gateway, '_requisicao', side_effect=[{'keys': []}, TimeoutError(CHAVE_FICTICIA)]) as rede:
            resultado = self.configurar()
        marcador = self.env.parent / '.meucontrolepc_9router_chave_pendente.json'
        self.assertTrue(marcador.exists());self.assertFalse(resultado['configurado'])
        self.assertNotIn(CHAVE_FICTICIA, marcador.read_text())
        with patch.object(gateway, '_requisicao', return_value={'keys': []}) as rede:
            repetido = self.configurar()
        self.assertEqual(rede.call_count, 1);self.assertIn('sem confirmação', repetido['pendencias'][0])
        with patch.object(gateway, '_requisicao', side_effect=[{'keys': [self.chave_existente()]}, {'data': [{'id': 'Minha Equipe'}]}]) as rede:
            recuperado = self.configurar()
        self.assertTrue(recuperado['configurado']);self.assertFalse(marcador.exists())
        self.assertEqual(rede.call_count, 2);self.assert_sem_segredos(resultado)

    def test_post_recusado_por_autenticacao_libera_marcador_para_retoma_login(self):
        erro = gateway._Pendente('Login administrativo pendente.', categoria='autenticacao')
        with patch.object(gateway, '_requisicao', side_effect=[{'keys': []}, erro]):
            resultado = self.configurar()
        self.assertFalse(resultado['configurado'])
        self.assertFalse((self.env.parent / '.meucontrolepc_9router_chave_pendente.json').exists())
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao()):
            retomado = self.configurar()
        self.assertTrue(retomado['configurado']);self.assert_sem_segredos(resultado)

    def test_trava_nativa_abrange_get_post_e_persistencia(self):
        lock = self.raiz / '.meucontrolepc_9router_configurando.lock'
        fd = gateway._adquirir_trava(lock)
        try:
            with patch.object(gateway, '_requisicao') as rede:
                resultado = self.configurar()
        finally:os.close(fd)
        rede.assert_not_called();self.assertIn('andamento', resultado['pendencias'][0])
        # A trava persistente em disco não impede retomar quando o processo sai.
        self.assertTrue(lock.exists())
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao()):
            retomado = self.configurar()
        self.assertTrue(retomado['configurado'])

    def test_modelo_manual_preservado_inclusive_quando_ausente_no_catalogo(self):
        self.env.write_text('OUTRO=preservar\nNINE_ROUTER_MODEL=Minha escolha manual\n', encoding='utf-8')
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(['Minha escolha manual', 'gc/gemini-flash'])):
            resultado = self.configurar(selecionar_recomendado=True)
        self.assertEqual(resultado['modelo'], 'Minha escolha manual');self.assertTrue(resultado['configurado'])
        with patch.object(gateway, '_requisicao', side_effect=[{'keys': [self.chave_existente()]}, {'data': [{'id': 'gc/gemini-flash'}]}]):
            ausente = self.configurar(selecionar_recomendado=True)
        self.assertFalse(ausente['configurado']);self.assertEqual(ausente['modelo'], 'Minha escolha manual')
        self.assertIn('NINE_ROUTER_MODEL=Minha escolha manual', self.env.read_text())

    def test_id_que_mudaria_no_leitor_env_nao_e_gravado(self):
        original = self.env.read_bytes()
        with patch.object(gateway, '_requisicao') as rede:
            resultado = self.configurar(modelo="'combo'")
        self.assertFalse(resultado['configurado']);rede.assert_not_called()
        self.assertEqual(self.env.read_bytes(), original)

    def test_credencial_json_invalida_nao_falha_nem_habilita_recomendacao(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM combos')
            db.execute("UPDATE providerConnections SET data='fora-de-json'")
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(['gc/gemini-flash'])):
            resultado = self.configurar(selecionar_recomendado=True)
        self.assertFalse(resultado['configurado']);self.assertEqual(resultado['modelo'], '')

    def test_combo_com_nome_do_assistente_tem_preferencia_sem_adivinhar(self):
        with sqlite3.connect(self.db) as db:
            db.execute('INSERT INTO combos VALUES(?,?,?,?)', ('x', 'Assistente', 'llm', '["gc/gemini-flash"]'))
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(['Assistente', 'Minha Equipe'])):
            resultado = self.configurar()
        self.assertEqual(resultado['modelo'], 'Assistente');self.assertTrue(resultado['configurado'])

    def test_recomendacao_so_compacto_do_provedor_ativo_credenciado(self):
        with sqlite3.connect(self.db) as db:db.execute('DELETE FROM combos')
        modelos = ['openai/gpt-mini', 'gc/gemini-pro', 'gc/gemini-flash-preview',
                   'gc/gemini-flash', 'gc/gemini-flash-tts', 'desconhecido/flash']
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(modelos)):
            resultado = self.configurar(selecionar_recomendado=True)
        self.assertTrue(resultado['configurado']);self.assertEqual(resultado['modelo'], 'gc/gemini-flash')
        self.assertEqual(resultado['modelo_origem'], 'recomendado_compacto')
        self.assertEqual(gateway._recomendado(list(reversed(modelos)), ['gemini-cli']), resultado['modelo'])

    def test_sem_mapeamento_de_provedor_retorna_seletor_publico_limitado(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM combos')
            db.execute("UPDATE providerConnections SET provider='desconhecido'")
        modelos = ['desconhecido/modelo-' + str(i) for i in range(5438)]
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(modelos)):
            resultado = self.configurar(selecionar_recomendado=True)
        self.assertFalse(resultado['configurado']);self.assertTrue(resultado['chave_configurada'])
        self.assertEqual(len(resultado['modelos']), 1000)
        self.assertEqual(resultado['modelo'], '')

    def test_provedor_ativo_sem_credencial_nao_serve_para_recomendar(self):
        with sqlite3.connect(self.db) as db:
            db.execute('DELETE FROM combos')
            db.execute("UPDATE providerConnections SET data='{}'")
        with patch.object(gateway, '_requisicao', side_effect=self.rede_criacao(['gc/gemini-flash'])):
            resultado = self.configurar(selecionar_recomendado=True)
        self.assertFalse(resultado['configurado']);self.assertEqual(resultado['modelo'], '')

    def test_recomendacao_prioriza_versao_estavel_recente_em_vez_de_id_lexico(self):
        modelos=['gc/gemini-1.5-flash','gc/gemini-2.0-flash','gc/gemini-2.5-flash',
                 'gc/gemini-3.1-flash-preview']
        self.assertEqual(gateway._recomendado(modelos,['gemini-cli']),'gc/gemini-2.5-flash')

    def test_recusa_reparse_windows_mesmo_sem_link_posix(self):
        meta=MagicMock(st_mode=0o100600,st_file_attributes=0x400)
        with patch.object(gateway.Path,'lstat',return_value=meta), \
             patch.object(gateway.stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400,create=True):
            with self.assertRaises(gateway._Pendente):gateway._seguro(self.env)

    def test_sem_provedor_ativo_nao_acessa_autenticacao_nem_cria_chave(self):
        with sqlite3.connect(self.db) as db:db.execute('UPDATE providerConnections SET isActive=0')
        with patch.object(gateway, '_token_cli') as token, patch.object(gateway, '_requisicao') as rede:
            resultado = self.configurar()
        self.assertFalse(resultado['configurado']);token.assert_not_called();rede.assert_not_called()

    def test_schema_desconhecido_nao_usa_api_nem_modifica_env(self):
        original = self.env.read_bytes()
        with sqlite3.connect(self.db) as db:db.execute("UPDATE _meta SET value='3' WHERE key='schemaVersion'")
        with patch.object(gateway, '_requisicao') as rede:
            resultado = self.configurar()
        rede.assert_not_called();self.assertIn('esquema', resultado['pendencias'][0])
        self.assertEqual(self.env.read_bytes(), original)

    def test_sem_cli_oficial_nao_cria_segredo_ou_finge_sucesso(self):
        (self.raiz / 'auth' / 'cli-secret').unlink()
        with patch.object(gateway, '_requisicao') as rede:resultado = self.configurar()
        rede.assert_not_called();self.assertFalse(resultado['configurado'])
        self.assertFalse((self.raiz / 'auth' / 'cli-secret').exists());self.assert_sem_segredos(resultado)

    def test_recusa_symlink_no_env_banco_auth_sidecar_e_diretorio(self):
        alvo = self.base / 'alvo'
        alvo.write_text('fixture', encoding='utf-8')
        for caminho in (self.env, self.db, self.raiz / 'auth' / 'cli-secret', Path(str(self.db) + '-wal')):
            with self.subTest(caminho=caminho.name):
                original = caminho.read_bytes() if caminho.exists() else None
                caminho.unlink(missing_ok=True)
                try:caminho.symlink_to(alvo)
                except (OSError, NotImplementedError):
                    if original is not None:caminho.write_bytes(original)
                    self.skipTest('Criação de link simbólico indisponível.')
                try:
                    with patch.object(gateway, '_requisicao') as rede:resultado = self.configurar()
                    rede.assert_not_called();self.assertFalse(resultado['configurado'])
                finally:
                    caminho.unlink()
                    if original is not None:caminho.write_bytes(original)
        link = self.base / 'link-9router'
        link.symlink_to(self.raiz, target_is_directory=True)
        with patch.object(gateway, '_requisicao') as rede:
            resultado = gateway.configurar_gateway(caminho_env=self.env, diretorio_gateway=link, autorizado=True)
        rede.assert_not_called();self.assertFalse(resultado['configurado'])

    def test_trava_retorna_pendencia_sem_bloquear(self):
        gateway._TRAVA.acquire()
        try:
            with patch.object(gateway, '_opcoes') as ler:resultado = self.configurar()
        finally:gateway._TRAVA.release()
        self.assertIn('andamento', resultado['pendencias'][0]);ler.assert_not_called()

    def test_token_identico_ao_contrato_oficial_cli(self):
        esperado = hashlib.sha256(b'fixture-machine-id9r-cli-authfixture-cli-secret').hexdigest()[:16]
        self.assertEqual(gateway._token_cli(self.raiz), esperado)


class TransporteGateway(unittest.TestCase):
    def setUp(self):
        self.opener = MagicMock()
        self.patch = patch.object(gateway.urllib.request, 'build_opener', return_value=self.opener)
        self.build = self.patch.start();self.addCleanup(self.patch.stop)

    def test_get_post_apenas_loopback_sem_proxy_sem_redirecionamento(self):
        self.opener.open.side_effect = [BytesIO(b'{"keys":[]}'), BytesIO(b'{"id":"fixture"}')]
        gateway._requisicao(gateway.URL_PADRAO, 'fixture-cli', '/api/keys')
        gateway._requisicao(gateway.URL_PADRAO, 'fixture-cli', '/api/keys', corpo={'name': gateway.NOME_CHAVE})
        pedido = self.opener.open.call_args.args[0]
        self.assertEqual(pedido.full_url, 'http://127.0.0.1:20128/api/keys')
        self.assertEqual(pedido.method, 'POST')
        self.assertEqual(json.loads(pedido.data), {'name': gateway.NOME_CHAVE})
        self.assertEqual(pedido.get_header('X-9r-cli-token'), 'fixture-cli')
        self.assertEqual(self.opener.open.call_args.kwargs, {'timeout': 4})
        self.assertEqual(self.build.call_args.args[0].proxies, {})
        self.assertIsInstance(self.build.call_args.args[1], gateway._SemRedirecionamento)
        self.assertIsNone(self.build.call_args.args[1].redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_rejeita_destino_remoto_e_rotas_de_geracao(self):
        for url in ('https://example.com/v1', 'http://localhost:20128/v1'):
            with self.assertRaises(Exception):gateway._requisicao(url, 'fixture', '/api/keys')
        with self.assertRaises(gateway._Pendente):gateway._requisicao(gateway.URL_PADRAO, 'fixture', '/v1/chat/completions')
        self.build.assert_not_called()

    def test_http_auth_erro_json_e_resposta_grande_nao_vazam_segredos(self):
        for status in (401, 403, 500, 302):
            self.opener.open.side_effect = urllib.error.HTTPError('http://127.0.0.1', status, CHAVE_FICTICIA, {}, BytesIO(CHAVE_FICTICIA.encode()))
            with self.assertRaises(gateway._Pendente) as cm:
                gateway._requisicao(gateway.URL_PADRAO, 'fixture', '/api/keys')
            self.assertNotIn(CHAVE_FICTICIA, str(cm.exception))
            if status in (401, 403):self.assertIn('administrativa', str(cm.exception))
        self.opener.open.side_effect = None
        for bruto in (b'{"keys":[],"keys":[]}', b'{"keys":NaN}', b'[]', b' ' * (gateway.MAX_JSON + 1)):
            self.opener.open.return_value = BytesIO(bruto)
            with self.assertRaises(gateway._Pendente):gateway._requisicao(gateway.URL_PADRAO, 'fixture', '/api/keys')

    def test_catalogo_envia_cli_e_chave_dedicada_juntos(self):
        self.opener.open.return_value = BytesIO(b'{"data":[]}')
        gateway._requisicao(gateway.URL_PADRAO, 'fixture-cli', '/v1/models', chave=CHAVE_FICTICIA)
        pedido = self.opener.open.call_args.args[0]
        self.assertEqual(pedido.get_header('Authorization'), 'Bearer ' + CHAVE_FICTICIA)
        self.assertEqual(pedido.get_header('X-9r-cli-token'), 'fixture-cli')
        self.assertEqual(pedido.method, 'GET');self.assertIsNone(pedido.data)


class ContratoHTTPReal(unittest.TestCase):
    def test_loopback_real_contrato_cli_post_chave_e_catalogo_sem_inferencia(self):
        pedidos = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):pass
            def responder(self, obj, status=200):
                bruto = json.dumps(obj).encode()
                self.send_response(status);self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(bruto)));self.end_headers();self.wfile.write(bruto)
            def do_GET(self):
                pedidos.append((self.command, self.path, self.headers.get('x-9r-cli-token'), self.headers.get('Authorization')))
                self.responder({'keys': []} if self.path == '/api/keys' else {'data': [{'id': 'gc/gemini-flash'}]})
            def do_POST(self):
                pedidos.append((self.command, self.path, self.headers.get('x-9r-cli-token'), self.headers.get('Authorization')))
                self.rfile.read(int(self.headers['Content-Length']))
                self.responder({'id': ID_FICTICIO, 'name': gateway.NOME_CHAVE, 'key': CHAVE_FICTICIA}, 201)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
        try:
            url = 'http://127.0.0.1:' + str(server.server_port) + '/v1'
            gateway._requisicao(url, 'fixture-cli', '/api/keys')
            gateway._requisicao(url, 'fixture-cli', '/api/keys', corpo={'name': gateway.NOME_CHAVE})
            gateway._requisicao(url, 'fixture-cli', '/v1/models', chave=CHAVE_FICTICIA)
        finally:server.shutdown();server.server_close();thread.join(timeout=3)
        self.assertEqual([p[:2] for p in pedidos], [('GET', '/api/keys'), ('POST', '/api/keys'), ('GET', '/v1/models')])
        self.assertTrue(all(p[2] == 'fixture-cli' for p in pedidos))
        self.assertEqual(pedidos[-1][3], 'Bearer ' + CHAVE_FICTICIA)


if __name__ == '__main__':unittest.main()
