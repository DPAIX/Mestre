"""Configuração, persistência e reinício isolados da árvore de fontes."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import caminhos_instalacao as caminhos
import nucleo
import startup_windows as startup


class CaminhosInstalacaoTeste(unittest.TestCase):
    def setUp(self):
        self.ambiente_original = os.environ.copy()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pasta = Path(self.tmp.name).resolve()
        self.codigo = self.pasta / 'codigo separado'
        self.codigo.mkdir()
        self.privado = self.pasta / 'configuracao privada'
        self.privado.mkdir()
        self.env = self.privado / '.env'
        self.env.write_text('FIXTURE_REDIRECIONAMENTO=valor-ficticio\n', encoding='utf-8')
        self.ambiente = patch.dict(os.environ, {}, clear=True)
        self.ambiente.start()
        self.addCleanup(self.ambiente.stop)

    def test_sem_seletor_preserva_instalacao_existente(self):
        self.assertEqual(caminhos.arquivo_env(self.codigo), self.codigo / '.env')
        self.assertEqual(caminhos.diretorio_dados(self.codigo), self.codigo / 'dados')

    def test_configuracao_externa_define_dados_sem_depender_do_cwd(self):
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env)}):
            self.assertEqual(caminhos.arquivo_env(self.codigo), self.env.resolve())
            self.assertEqual(caminhos.diretorio_dados(self.codigo), self.privado / 'dados')
            alternativo = self.pasta / 'outros dados'
            with patch.dict(os.environ, {'MEUCONTROLEPC_DADOS': str(alternativo)}):
                self.assertEqual(caminhos.diretorio_dados(self.codigo), alternativo.resolve())

    def test_seletores_relativos_vazios_e_controles_sao_rejeitados(self):
        for nome, resolver in (('MEUCONTROLEPC_ENV', caminhos.arquivo_env),
                               ('MEUCONTROLEPC_DADOS', caminhos.diretorio_dados)):
            for valor in ('', 'relativo/.env', 'C:relativo', 'x\ny'):
                with self.subTest(nome=nome, valor=repr(valor)), patch.dict(os.environ, {nome: valor}):
                    with self.assertRaises(ValueError):
                        resolver(self.codigo)

    def test_env_externo_ausente_nao_faz_fallback_para_codigo(self):
        (self.codigo / '.env').write_text('FIXTURE_REDIRECIONAMENTO=local\n', encoding='utf-8')
        with patch.object(nucleo, 'BASE', self.codigo), patch.dict(os.environ, {
            'MEUCONTROLEPC_ENV': str(self.privado / 'ausente.env')
        }):
            with self.assertRaisesRegex(RuntimeError, 'externo'):
                nucleo.ler_env()
            self.assertNotIn('FIXTURE_REDIRECIONAMENTO', os.environ)

    def test_leitura_externa_nao_carrega_arquivo_do_codigo_ou_redefine_diretorios(self):
        self.env.write_text('FIXTURE_REDIRECIONAMENTO=externo\nMEUCONTROLEPC_DADOS=/nao-usar\n', encoding='utf-8')
        (self.codigo / '.env').write_text('FIXTURE_SO_NO_CODIGO=nao-carregar\n', encoding='utf-8')
        with patch.object(nucleo, 'BASE', self.codigo), patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env)}):
            nucleo.ler_env()
            self.assertEqual(os.environ['FIXTURE_REDIRECIONAMENTO'], 'externo')
            self.assertNotIn('FIXTURE_SO_NO_CODIGO', os.environ)
            self.assertNotIn('MEUCONTROLEPC_DADOS', os.environ)

    def test_processo_segue_tendo_prioridade_sobre_env(self):
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env),
                                    'FIXTURE_REDIRECIONAMENTO': 'processo'}):
            nucleo.ler_env()
            self.assertEqual(os.environ['FIXTURE_REDIRECIONAMENTO'], 'processo')

    def copiar_fontes_isoladas(self):
        # Nunca percorre/copia .env, dados, ambientes virtuais ou symlinks da
        # instalação em que a suíte foi iniciada. Os imports usam só esta cópia.
        origem = Path(nucleo.__file__).resolve().parent
        for modulo in origem.glob('*.py'):
            if modulo.is_file() and not modulo.is_symlink():
                shutil.copy2(modulo, self.codigo / modulo.name)
        (self.codigo / '.env').write_text('FIXTURE_SO_NO_CODIGO=nao-carregar\n', encoding='utf-8')
        return self.codigo

    def validar_imports_reais(self, fontes):
        dados = self.privado / 'dados'
        # Preserva apenas variáveis de execução do Python/Windows, sem herdar
        # configurações de provedores nem diretórios de módulos do usuário.
        runtime = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT',
                   'TEMP', 'TMP', 'TMPDIR', 'LANG', 'LC_ALL', 'LC_CTYPE'}
        ambiente = {nome: valor for nome, valor in self.ambiente_original.items()
                    if nome.upper() in runtime}
        ambiente.update({'MEUCONTROLEPC_ENV': str(self.env), 'MEUCONTROLEPC_DADOS': str(dados)})
        programa = (
            'import json,os,sys; sys.path.insert(0,sys.argv[1]); '
            'import nucleo,agenda_google,assistente_pc; '
            'nucleo.ler_env(); nucleo.gravar_json("fixture_redirecionamento.json",{"valor":3}); '
            'print(json.dumps({"base":str(nucleo.BASE),"dados":str(nucleo.DADOS),'
            '"token":str(agenda_google.TOKEN),"app_dados":str(assistente_pc.DADOS),'
            '"modulos":[nucleo.__file__,agenda_google.__file__,assistente_pc.__file__],'
            '"env_externo":os.getenv("FIXTURE_REDIRECIONAMENTO"),'
            '"env_local":os.getenv("FIXTURE_SO_NO_CODIGO")}))'
        )
        # A árvore comparada contém somente cópias de fontes e fixtures criadas
        # pelo próprio teste. -I evita PYTHONPATH/user-site e -B evita __pycache__.
        antes = {p.relative_to(fontes): p.read_bytes() for p in fontes.rglob('*') if p.is_file()}
        resultado = subprocess.run([sys.executable, '-I', '-B', '-c', programa, str(fontes)],
                                   cwd=self.pasta, env=ambiente, capture_output=True,
                                   text=True, check=True, timeout=30)
        meta = json.loads(resultado.stdout)
        self.assertEqual(Path(meta['base']), fontes)
        self.assertTrue(all(Path(modulo).resolve().parent == fontes for modulo in meta['modulos']))
        self.assertEqual(Path(meta['dados']), dados)
        self.assertEqual(Path(meta['app_dados']), dados)
        self.assertEqual(Path(meta['token']), dados / 'token_google.json')
        self.assertEqual(meta['env_externo'], 'valor-ficticio')
        self.assertIsNone(meta['env_local'])
        self.assertEqual(json.loads((dados / 'fixture_redirecionamento.json').read_text(encoding='utf-8')), {'valor': 3})
        depois = {p.relative_to(fontes): p.read_bytes() for p in fontes.rglob('*') if p.is_file()}
        self.assertEqual(depois, antes, 'Os imports não devem gravar nem alterar arquivos junto ao código.')

    def test_imports_reais_gravam_somente_no_destino_externo(self):
        fontes = self.copiar_fontes_isoladas()
        self.validar_imports_reais(fontes)
        self.assertFalse((fontes / 'dados').exists())

    def test_imports_reais_preservam_arquivos_preexistentes_junto_ao_codigo(self):
        fontes = self.copiar_fontes_isoladas()
        local = fontes / 'dados'
        local.mkdir()
        fixture = local / 'fixture_redirecionamento.json'
        fixture.write_text('{"valor":"fixture anterior preservada"}\n', encoding='utf-8')
        (local / 'outro_estado.json').write_text('{"fixture":"outro arquivo preservado"}\n', encoding='utf-8')
        self.validar_imports_reais(fontes)

    def test_status_mede_espaco_do_destino_de_dados_ainda_nao_criado(self):
        from collections import namedtuple
        disco = namedtuple('disco', 'total used free')(100, 0, 100)
        with patch.object(nucleo, 'DADOS', self.privado / 'a-criar' / 'dados'), \
                patch.object(nucleo.shutil, 'disk_usage', return_value=disco) as medir:
            nucleo.resumo_status()
            medir.assert_called_once_with(self.privado)

    def test_startup_preserva_caminhos_externos_sem_copiar_credenciais(self):
        (self.privado / 'dados').mkdir()
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env)}), \
                patch.object(Path, 'read_text', side_effect=AssertionError('Nao ler configuracao')):
            texto = startup.texto_inicio(self.codigo, self.privado / 'python.exe')
        self.assertIn('redirecionar_assistente.py', texto)
        self.assertIn(str(self.env), texto)
        self.assertIn(str(self.privado / 'dados'), texto)
        self.assertNotIn('valor-ficticio', texto)
        self.assertIn('DisableDelayedExpansion', texto)

    def test_primeiro_logon_pode_criar_destino_padrao_sem_dados_explicitos(self):
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env)}):
            texto = startup.texto_inicio(self.codigo, self.privado / 'python.exe')
        self.assertNotIn('--dados', texto)
        self.assertIn(str(self.env), texto)

    def test_startup_gravado_reutiliza_redirecionador(self):
        destino = self.pasta / 'Startup' / 'MeuControlePC_inicio_ao_logar.cmd'
        with patch.dict(os.environ, {'MEUCONTROLEPC_ENV': str(self.env)}), \
                patch.object(startup, 'destino', return_value=destino), \
                patch.object(sys, 'argv', ['startup_windows.py', '--ativar']), \
                contextlib.redirect_stdout(io.StringIO()):
            startup.main()
        conteudo = destino.read_text(encoding='utf-8')
        self.assertIn('--env', conteudo)
        self.assertIn(str(self.env), conteudo)
        self.assertIn('redirecionar_assistente.py', conteudo)

    def test_startup_escapa_percentuais_e_rejeita_linhas_executaveis(self):
        texto = startup.texto_inicio(self.codigo / '100%teste% !')
        self.assertIn('100%%teste%% !', texto)
        for valor in ('caminho\ncomando', 'caminho"comando'):
            with self.assertRaises(ValueError):
                startup.texto_inicio(valor)


if __name__ == '__main__':
    unittest.main()
