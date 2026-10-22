"""Configuração, persistência e reinício isolados da árvore de fontes."""
import contextlib
import io
import json
import os
from pathlib import Path
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
        self.pasta = Path(self.tmp.name)
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

    def test_imports_reais_gravam_somente_no_destino_externo(self):
        dados = self.privado / 'dados'
        ambiente = self.ambiente_original.copy()
        ambiente.update({'MEUCONTROLEPC_ENV': str(self.env), 'MEUCONTROLEPC_DADOS': str(dados)})
        programa = (
            'import json,nucleo,agenda_google,assistente_pc; '
            'nucleo.ler_env(); nucleo.gravar_json("fixture_redirecionamento.json",{"valor":3}); '
            'print(json.dumps({"base":str(nucleo.BASE),"dados":str(nucleo.DADOS),'
            '"token":str(agenda_google.TOKEN),"app_dados":str(assistente_pc.DADOS)}))'
        )
        fontes = Path(nucleo.__file__).resolve().parent
        resultado = subprocess.run([sys.executable, '-c', programa], cwd=fontes,
                                   env=ambiente, capture_output=True, text=True, check=True)
        meta = json.loads(resultado.stdout)
        self.assertEqual(Path(meta['base']), fontes)
        self.assertEqual(Path(meta['dados']), dados)
        self.assertEqual(Path(meta['app_dados']), dados)
        self.assertEqual(Path(meta['token']), dados / 'token_google.json')
        self.assertEqual(json.loads((dados / 'fixture_redirecionamento.json').read_text()), {'valor': 3})
        self.assertFalse((fontes / 'dados' / 'fixture_redirecionamento.json').exists())

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
