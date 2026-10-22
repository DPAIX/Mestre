"""Bootstrap com caminhos temporários; nenhum .env é lido ou filho executado."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import redirecionar_assistente as launcher


class RedirecionarAssistente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name).resolve()
        self.codigo = self.base / 'codigo atualizado'
        self.codigo.mkdir()
        nomes = set(launcher.FONTES_NECESSARIAS) | {x[0] for x in launcher.MODOS.values()}
        for nome in nomes:
            (self.codigo / nome).write_text('# arquivo fictício\n', encoding='utf-8')
        self.externo = self.base / 'instalacao externa'
        self.externo.mkdir()
        self.env = self.externo / '.env'
        self.env.write_text('SEGREDO_FICTICIO_NAO_LER=conteudo_privado\n', encoding='utf-8')
        self.dados = self.externo / 'dados'
        self.dados.mkdir()
        self.python = self.base / 'python escolhido.exe'
        self.python.touch()

    def plano(self, **kw):
        return launcher.plano_execucao(self.codigo, self.env, **kw)

    def args(self, *extras):
        return ['--codigo', str(self.codigo), '--env', str(self.env), *extras]

    def test_defaults_ficam_nos_caminhos_solicitados(self):
        self.assertEqual(launcher.CODIGO_PADRAO, r'C:\Users\Mestre\Documents\GitHub\Mestre')
        self.assertEqual(launcher.ENV_PADRAO, r'F:\MeuControlePC_v2\.env')

    def test_plano_usa_codigo_e_configuracao_externa_sem_alterar_ambiente(self):
        ambiente = {'PATH': 'exemplo', 'MEUCONTROLEPC_ENV': 'antigo', 'MEUCONTROLEPC_DADOS': 'antigo',
                    'PYTHONPATH': 'codigo_velho', 'PYTHONHOME': 'runtime_velho'}
        plano = self.plano(python=self.python, ambiente=ambiente)
        self.assertEqual(plano['cwd'], str(self.codigo.resolve()))
        self.assertEqual(plano['comando'], [str(self.python), str(self.codigo / 'assistente_pc.py')])
        self.assertEqual(plano['ambiente']['MEUCONTROLEPC_ENV'], str(self.env))
        self.assertEqual(plano['ambiente']['MEUCONTROLEPC_DADOS'], str(self.dados))
        self.assertNotIn('PYTHONPATH', plano['ambiente'])
        self.assertNotIn('PYTHONHOME', plano['ambiente'])
        self.assertEqual(ambiente['MEUCONTROLEPC_ENV'], 'antigo')

    def test_preferencia_python_codigo_externo_e_fallback(self):
        codigo_python = self.codigo / '.venv' / 'Scripts' / 'python.exe'
        externo_python = self.externo / '.venv' / 'Scripts' / 'python.exe'
        for p in (codigo_python, externo_python):
            p.parent.mkdir(parents=True)
            p.touch()
        self.assertEqual(self.plano()['python'], codigo_python)
        codigo_python.unlink()
        self.assertEqual(self.plano()['python'], externo_python)
        externo_python.unlink()
        self.assertEqual(self.plano()['python'], Path(sys.executable).resolve())

    def test_python_explicito_tem_prioridade_e_precisa_existir(self):
        self.assertEqual(self.plano(python=self.python)['python'], self.python)
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(python=self.base / 'ausente.exe')
        with patch.object(launcher.sys, 'version_info', (3, 10)):
            with self.assertRaises(launcher.FalhaRedirecionamento):
                self.plano()

    def test_arvore_antiga_sem_caminhos_instalacao_e_rejeitada(self):
        (self.codigo / 'caminhos_instalacao.py').unlink()
        with self.assertRaisesRegex(launcher.FalhaRedirecionamento, 'antiga'):
            self.plano()

    def test_paths_relativos_ou_env_ausente_nao_iniciam(self):
        for args in [('relativo', self.env), (self.codigo, 'relativo.env'), (self.codigo, self.externo / 'ausente.env')]:
            with self.subTest(args=args), self.assertRaises(launcher.FalhaRedirecionamento):
                launcher.plano_execucao(*args)
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(dados='dados')
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(python='python')

    def test_env_e_dados_nao_podem_ficar_dentro_do_codigo(self):
        env_interno = self.codigo / '.env'
        env_interno.touch()
        dados_internos = self.codigo / 'dados'
        dados_internos.mkdir()
        for kw in ({'arquivo_env': env_interno}, {'dados': dados_internos}):
            with self.subTest(kw=kw), self.assertRaises(launcher.FalhaRedirecionamento):
                launcher.plano_execucao(self.codigo, kw.get('arquivo_env', self.env), dados=kw.get('dados'))

    def test_destino_ausente_com_legado_no_codigo_nao_inicia_vazio(self):
        self.dados.rmdir()
        legado = self.codigo / 'dados'
        legado.mkdir()
        (legado / 'gestao_vida.json').write_text('NAO_LER_NEM_MOVER', encoding='utf-8')
        with patch.object(Path, 'read_text', side_effect=AssertionError('Leitura indevida')), \
                patch.object(Path, 'iterdir', side_effect=AssertionError('Enumeração indevida')):
            with self.assertRaisesRegex(launcher.FalhaRedirecionamento, 'iniciar vazio'):
                self.plano()
        self.assertFalse(self.dados.exists())
        self.assertTrue((legado / 'gestao_vida.json').is_file())

    def test_dados_explicitos_recuperam_pasta_externa_e_precisam_existir(self):
        alternativos = self.base / 'dados preservados'
        alternativos.mkdir()
        self.assertEqual(self.plano(dados=alternativos)['dados'], alternativos)
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(dados=self.base / 'ainda nao existe')
        arquivo = self.base / 'arquivo.json'
        arquivo.touch()
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(dados=arquivo)

    def test_primeiro_inicio_sem_legado_so_planeja_diretorio_novo(self):
        self.dados.rmdir()
        self.assertEqual(self.plano()['dados'], self.dados)
        self.assertFalse(self.dados.exists())

    def test_modos_tem_scripts_fixos_e_argumentos_controlados(self):
        for modo, esperado in [('painel', ['assistente_pc.py', '--somente-painel']),
                                ('diagnostico', ['assistente_pc.py', '--diagnostico']),
                                ('telegram', ['configurar_telegram.py']),
                                ('google', ['autorizar_google.py'])]:
            with self.subTest(modo=modo):
                plano = self.plano(modo=modo, python=self.python)
                self.assertEqual([Path(plano['comando'][1]).name, *plano['comando'][2:]], esperado)
        self.assertEqual(self.plano(modo='ollama', argumentos=['--modelo', 'mistral:latest'])['comando'][-2:], ['--modelo', 'mistral:latest'])
        self.assertEqual(self.plano(modo='inicio-automatico', argumentos=['--ativar'])['comando'][-1], '--ativar')

    def test_shell_script_ou_flag_nao_listados_sao_rejeitados(self):
        for modo, argumentos in [('start', ['-c', 'print(1)']), ('start', ['--migrar', '/qualquer']),
                                  ('ollama', ['--codigo', 'outro.py']), ('ollama', ['--modelo', '--listar']),
                                  ('ollama', ['--listar', '--modelo', 'mistral']), ('google', ['--executar']),
                                  ('telegram', ['-m', 'os']), ('inicio-automatico', [])]:
            with self.subTest(modo=modo, argumentos=argumentos), self.assertRaises(launcher.FalhaRedirecionamento):
                self.plano(modo=modo, argumentos=argumentos)
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(modo='shell')

    def test_verificar_nao_le_env_nem_dados_nem_inicia_child(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), patch.object(Path, 'read_text', side_effect=AssertionError('Leitura privada')), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('Leitura privada')), \
                patch.object(Path, 'iterdir', side_effect=AssertionError('Enumeração privada')), \
                patch.object(launcher.subprocess, 'run') as run:
            resultado = launcher.main(self.args('--verificar'))
        self.assertEqual(resultado, 0)
        run.assert_not_called()
        self.assertIn(str(self.env), saida.getvalue())
        self.assertNotIn('SEGREDO_FICTICIO_NAO_LER', saida.getvalue())
        self.assertNotIn('conteudo_privado', saida.getvalue())

    def test_verificar_apos_modo_ou_separador_nunca_chega_ao_child(self):
        for extras in (['painel', '--verificar'], ['telegram', '--', '--verificar']):
            with self.subTest(extras=extras), contextlib.redirect_stdout(io.StringIO()), patch.object(launcher.subprocess, 'run') as run:
                self.assertEqual(launcher.main(self.args(*extras)), 0)
                run.assert_not_called()

    def test_inicio_usa_subprocess_sem_shell_e_preserva_exit_code(self):
        run = Mock(return_value=Mock(returncode=7))
        with patch.object(launcher.subprocess, 'run', run):
            self.assertEqual(launcher.main(self.args('--python', str(self.python), 'painel')), 7)
        cmd = run.call_args.args[0]
        self.assertEqual(cmd, [str(self.python), str(self.codigo / 'assistente_pc.py'), '--somente-painel'])
        self.assertEqual(run.call_args.kwargs['cwd'], str(self.codigo))
        self.assertFalse(run.call_args.kwargs['shell'])
        self.assertFalse(run.call_args.kwargs['check'])
        self.assertEqual(run.call_args.kwargs['env']['MEUCONTROLEPC_ENV'], str(self.env))

    def test_script_do_modo_ausente_e_erro_de_processo_sao_controlados(self):
        (self.codigo / 'autorizar_google.py').unlink()
        with self.assertRaises(launcher.FalhaRedirecionamento):
            self.plano(modo='google')
        with patch.object(launcher.subprocess, 'run', side_effect=OSError('mensagem não divulgada')), \
                contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(launcher.main(self.args()), 2)
        self.assertNotIn('mensagem não divulgada', saida.getvalue())


if __name__ == '__main__':
    unittest.main()
