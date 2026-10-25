"""Implantação em pastas fictícias, sem tocar instalação ou credenciais reais."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import implantacao_assistente as app


class ImplantacaoAssistente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve()
        self.origem = self.raiz/'pacote'; self.origem.mkdir()
        self.destino = self.raiz/'codigo'; self.destino.mkdir()
        self.backup = self.raiz/'backups_codigo'
        self.dados = self.raiz/'dados_privados'; self.dados.mkdir()
        self.manifesto = {}
        for nome in sorted(app.IDENTIDADE):
            self.fonte(nome, ('# Fonte nova de '+nome+'\n').encode())
            (self.destino/nome).write_bytes(('# Fonte anterior de '+nome+'\n').encode())
        self.antes = {n: (self.destino/n).read_bytes() for n in self.manifesto}

    def fonte(self, nome, conteudo):
        arquivo = self.origem/nome; arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(conteudo)
        self.manifesto[nome] = hashlib.sha256(conteudo).hexdigest()

    def instalar(self, **kwargs):
        return app.implantar(self.origem, self.destino, self.backup, self.manifesto,
                             autorizado=True, dados=self.dados, **kwargs)

    def test_plano_so_confere_metadados_sem_criar_diretorios(self):
        destino = self.raiz/'ainda_nao_existe'
        with patch.object(Path, 'read_bytes', side_effect=AssertionError('Plano não lê fontes.')):
            plano = app.planejar_implantacao(self.origem, destino, self.backup,
                                            self.manifesto, dados=self.dados)
        self.assertEqual(plano['destino'], destino)
        self.assertFalse(destino.exists()); self.assertFalse(self.backup.exists())

    def test_autorizacao_explicita_antes_de_ler_ou_alterar(self):
        with patch.object(app, 'planejar_implantacao') as planejar:
            for autorizado in (False, None, 1, 'sim'):
                with self.subTest(autorizado=autorizado), self.assertRaises(PermissionError):
                    app.implantar(self.origem, self.destino, self.backup, self.manifesto,
                                  autorizado=autorizado)
            planejar.assert_not_called()

    def test_implanta_com_backup_e_preserva_arquivos_nao_enumerados(self):
        for nome in ('.env', '.git/config', 'dados/vida.json', '.venv/python.exe',
                     'Models/modelo.bin', '__pycache__/privado.pyc', 'rascunho_usuario.py'):
            p = self.destino/nome; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b'fixture privada nao modificar')
        resultado = self.instalar()
        self.assertEqual(resultado['estado'], 'implantado')
        self.assertEqual(resultado['arquivos_alterados'], 3)
        backup = Path(resultado['backup'])
        for nome, anterior in self.antes.items():
            self.assertEqual((self.destino/nome).read_bytes(), (self.origem/nome).read_bytes())
            self.assertEqual((backup/'fontes'/nome).read_bytes(), anterior)
        self.assertEqual((self.destino/'.env').read_bytes(), b'fixture privada nao modificar')
        self.assertEqual((self.destino/'dados/vida.json').read_bytes(), b'fixture privada nao modificar')
        self.assertEqual((self.destino/'rascunho_usuario.py').read_bytes(), b'fixture privada nao modificar')
        self.assertFalse((backup/'fontes/.env').exists())
        self.assertTrue((backup/'manifesto_reversao.json').is_file())

    def test_repetir_e_idempotente_e_nao_cria_outro_backup(self):
        self.instalar(); existentes = sorted(self.backup.iterdir())
        resultado = self.instalar()
        self.assertEqual(resultado['estado'], 'ja_atualizado')
        self.assertIsNone(resultado['backup']); self.assertEqual(resultado['arquivos_alterados'], 0)
        self.assertEqual(sorted(self.backup.iterdir()), existentes)

    def test_origem_igual_destino_verifica_sem_auto_copia_ou_backup(self):
        with patch.object(app, '_gravar_atomico') as gravar:
            resultado = app.implantar(self.origem, self.origem, self.backup,
                                     self.manifesto, autorizado=True)
        self.assertEqual(resultado['estado'], 'verificado'); gravar.assert_not_called()
        self.assertFalse(self.backup.exists())

    def test_hash_corrompido_recusa_pacote_inteiro_antes_do_backup(self):
        (self.origem/'nucleo.py').write_text('# pacote modificado')
        with self.assertRaises(ValueError): self.instalar()
        self.assertFalse(self.backup.exists())
        for nome, anterior in self.antes.items(): self.assertEqual((self.destino/nome).read_bytes(), anterior)

    def test_fonte_ausente_ou_identidade_incompleta_recusa_antes_de_gravar(self):
        manifesto = {n: s for n, s in self.manifesto.items() if n != 'nucleo.py'}
        with self.assertRaises(ValueError): app.planejar_implantacao(self.origem, self.destino, self.backup, manifesto)
        (self.origem/'nucleo.py').unlink()
        with self.assertRaises(ValueError): self.instalar()
        self.assertFalse(self.backup.exists())

    def test_traversal_privados_ads_e_colisoes_windows_sao_recusados(self):
        for nome in ('../fora.py', '/fora.py', 'sub//a.py', 'sub/./a.py', 'x\\a.py',
                     'a.py:stream', 'dados/exemplo.py', '.git/config.py', '.env',
                     'exemplos/token.json', 'exemplos/client_secret_google.json',
                     '__pycache__/a.py', 'COM1.py', 'a.py.'):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                app.planejar_implantacao(self.origem, self.destino, self.backup,
                    {**self.manifesto, nome: '0'*64})
        with self.assertRaises(ValueError):
            app.planejar_implantacao(self.origem, self.destino, self.backup,
                {**self.manifesto, 'Nucleo.py': self.manifesto['nucleo.py']})

    def test_backup_dentro_fontes_ou_dados_e_recusado(self):
        for pasta in (self.origem/'backup', self.destino/'backup', self.dados/'backup'):
            with self.subTest(pasta=pasta), self.assertRaises(ValueError):
                app.planejar_implantacao(self.origem, self.destino, pasta, self.manifesto, dados=self.dados)
        with self.assertRaises(ValueError):
            app.planejar_implantacao(self.origem, self.origem/'subpasta', self.backup, self.manifesto)

    def test_falha_durante_copia_restaura_so_fontes_ja_alteradas(self):
        original = app._gravar_atomico
        def gravar(arquivo, conteudo):
            if arquivo == self.destino/'nucleo.py': raise OSError('fixture de falha')
            return original(arquivo, conteudo)
        with patch.object(app, '_gravar_atomico', side_effect=gravar):
            with self.assertRaises(app.FalhaImplantacao) as erro: self.instalar()
        self.assertTrue(erro.exception.reversao_completa)
        self.assertTrue(Path(erro.exception.backup).is_dir())
        for nome, anterior in self.antes.items(): self.assertEqual((self.destino/nome).read_bytes(), anterior)

    def test_rollback_preserva_edicao_concorrente_detectada(self):
        original = app._gravar_atomico
        def gravar(arquivo, conteudo):
            if arquivo == self.destino/'nucleo.py':
                (self.destino/'assistente_pc.py').write_bytes(b'# edicao concorrente do usuario')
                raise OSError('fixture de falha')
            return original(arquivo, conteudo)
        with patch.object(app, '_gravar_atomico', side_effect=gravar):
            with self.assertRaises(app.FalhaImplantacao) as erro: self.instalar()
        self.assertFalse(erro.exception.reversao_completa)
        self.assertIn('assistente_pc.py', erro.exception.conflitos)
        self.assertEqual((self.destino/'assistente_pc.py').read_bytes(), b'# edicao concorrente do usuario')
        self.assertEqual((self.destino/'caminhos_instalacao.py').read_bytes(), self.antes['caminhos_instalacao.py'])

    def test_falha_depois_do_replace_tambem_reverte_arquivo_concluido(self):
        original = app._gravar_atomico
        primeira_falha = [True]
        def gravar(arquivo, conteudo):
            original(arquivo, conteudo)
            if arquivo == self.destino/'nucleo.py' and primeira_falha[0]:
                primeira_falha[0] = False
                raise OSError('fixture apos replace')
        with patch.object(app, '_gravar_atomico', side_effect=gravar):
            with self.assertRaises(app.FalhaImplantacao) as erro: self.instalar()
        self.assertTrue(erro.exception.reversao_completa)
        for nome, anterior in self.antes.items(): self.assertEqual((self.destino/nome).read_bytes(), anterior)

    def test_interrupcao_remove_so_arquivos_novos_desta_implantacao(self):
        (self.destino/'assistente_pc.py').unlink()
        original = app._gravar_atomico
        def gravar(arquivo, conteudo):
            if arquivo == self.destino/'nucleo.py': raise KeyboardInterrupt()
            return original(arquivo, conteudo)
        with patch.object(app, '_gravar_atomico', side_effect=gravar):
            with self.assertRaises(app.FalhaImplantacao) as erro: self.instalar()
        self.assertTrue(erro.exception.reversao_completa)
        self.assertFalse((self.destino/'assistente_pc.py').exists())
        self.assertEqual((self.destino/'nucleo.py').read_bytes(), self.antes['nucleo.py'])

    def test_falha_em_backup_nao_toca_destino(self):
        with patch.object(app, '_gravar_atomico', side_effect=OSError('fixture')):
            with self.assertRaises(app.FalhaImplantacao) as erro: self.instalar()
        self.assertTrue(erro.exception.reversao_completa)
        for nome, anterior in self.antes.items(): self.assertEqual((self.destino/nome).read_bytes(), anterior)

    def test_copia_somente_extensoes_publicas_de_pacote(self):
        for nome in ('.env.exemplo', '.gitignore', '.github/workflows/testes.yml',
                     'requirements.txt', 'requirements-voz-local.txt',
                     'dados_iniciais/rotina.json', 'exemplos/exemplo.ipynb',
                     'testes/test_painel_frontend.js'):
            self.fonte(nome, b'fixture publica')
        resultado = self.instalar()
        self.assertEqual(resultado['arquivos_alterados'], len(self.manifesto))
        self.assertEqual((self.destino/'.env.exemplo').read_bytes(), b'fixture publica')

    def test_manifesto_json_publico_e_duplicatas_invalidas(self):
        arquivo = self.origem/'manifesto_instalacao.json'
        arquivo.write_text(json.dumps({'versao': 1, 'arquivos': self.manifesto}), encoding='utf8')
        resultado = app.implantar(self.origem, self.destino, self.backup, arquivo, autorizado=True)
        self.assertEqual(resultado['estado'], 'implantado')
        arquivo.write_text('{"versao":1,"versao":1,"arquivos":{}}')
        with self.assertRaises(ValueError): app.carregar_manifesto(arquivo)
        with self.assertRaises(ValueError): app.carregar_manifesto(self.origem/'.env')

    def test_link_em_fonte_destino_ou_ancestral_e_recusado(self):
        fora = self.raiz/'fora.py'; fora.write_bytes(b'arquivo externo')
        alvo = self.origem/'nucleo.py'; alvo.unlink()
        try: alvo.symlink_to(fora)
        except (OSError, NotImplementedError): self.skipTest('Sistema não permite criar symlink nesta sessão.')
        with self.assertRaises(ValueError): self.instalar()
        alvo.unlink(); self.fonte('nucleo.py', b'# fonte nova')
        destino = self.destino/'nucleo.py'; destino.unlink(); destino.symlink_to(fora)
        with self.assertRaises(ValueError): self.instalar()
        self.assertEqual(fora.read_bytes(), b'arquivo externo')
        destino.unlink(); destino.write_bytes(b'# antiga')
        ancestral = self.raiz/'codigo_link'; ancestral.symlink_to(self.destino, target_is_directory=True)
        with self.assertRaises(ValueError):
            app.planejar_implantacao(self.origem, ancestral/'subpasta', self.backup, self.manifesto)


if __name__ == '__main__': unittest.main()
