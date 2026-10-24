"""Integrações Ollama com processos, PATH e ambiente simulados; sem agentes reais."""
import contextlib
import importlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import integracoes_agentes as agentes


class IntegracoesAgentesTeste(unittest.TestCase):
    def setUp(self):
        agentes._LANCAMENTOS.clear()
        self.addCleanup(agentes._LANCAMENTOS.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.exe = Path(self.tmp.name) / 'ollama.exe'
        self.exe.write_bytes(b'fixture-nao-executavel')
        self.exe = self.exe.resolve()
        self.ajuda = 'Supported integrations:\n' + '\n'.join(
            f'  {item.agente}    {item.nome}' for item in agentes.INTEGRACOES)
        self.processo = MagicMock()
        self.processo.poll.return_value = None
        for nome, alvo, valor in (
                ('run', agentes.subprocess, SimpleNamespace(returncode=0, stdout=self.ajuda)),):
            p = patch.object(alvo, nome, return_value=valor)
            setattr(self, nome, p.start())
            self.addCleanup(p.stop)
        p = patch.object(agentes.subprocess, 'Popen', return_value=self.processo)
        self.popen = p.start()
        self.addCleanup(p.stop)
        p = patch.object(agentes.shutil, 'which', return_value=str(self.exe))
        self.which = p.start()
        self.addCleanup(p.stop)
        p = patch.object(agentes.sys, 'platform', 'win32')
        p.start()
        self.addCleanup(p.stop)
        p = patch.dict(os.environ, {'PATH': 'fixture-path', 'SystemRoot': 'fixture-windows',
                                   'OLLAMA_URL': 'http://127.0.0.1:11434'}, clear=True)
        p.start()
        self.addCleanup(p.stop)

    def abrir(self, agente='claude', modelo='', configurar=False):
        return agentes.abrir_agente(agente, modelo, configurar, confirmado=True)

    def test_importacao_nao_consulta_path_executa_ou_instala(self):
        importlib.reload(agentes)
        self.which.assert_not_called()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_catalogo_contem_todos_aplicativos_da_imagem_com_ids_oficiais(self):
        itens = agentes.catalogo_agentes()
        self.assertEqual({item['agente'] for item in itens}, {
            'claude', 'opencode', 'hermes', 'hermes-desktop', 'copilot', 'cline',
            'dsh', 'pi', 'openclaw', 'chatgpt', 'codex', 'omp', 'droid', 'qwen'})
        self.assertEqual(len(itens), 14)
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_aliases_resolvem_sem_aceitar_comandos(self):
        for texto, esperado in [('Claude Code', 'claude'), ('Copilot CLI', 'copilot'),
                                ('DeepSeek Harness', 'dsh'), ('Qwen Code', 'qwen'),
                                ('hermes-desktop', 'hermes-desktop'), ('Oh My Pi', 'omp'),
                                ('codex-app', 'chatgpt'), ('  CoDeX   CLI  ', 'codex')]:
            with self.subTest(texto=texto):
                self.assertEqual(agentes.validar_agente(texto), esperado)
        for invalido in ('claude --yes', 'codex; calc', '../hermes', 'cline\ncalc',
                         '-config', 'qwen3.8:27b', 'gemma4:31b-cloud', '', None, ['pi']):
            with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                agentes.validar_agente(invalido)

    def test_plano_e_puro_aceita_modelo_opcional_e_informa_efeitos_reais(self):
        for modelo in (None, ''):
            plano = agentes.preparar_lancamento('Claude Code', modelo)
            self.assertEqual(set(plano), {'agente', 'modelo', 'configurar', 'descricao'})
            self.assertEqual(plano['agente'], 'claude')
            self.assertEqual(plano['modelo'], '')
            self.assertFalse(plano['configurar'])
            self.assertIn('instalar', plano['descricao'])
            self.assertIn('login', plano['descricao'])
        self.which.assert_not_called()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_nuvem_exige_aviso_sem_alegar_modelo_instalado(self):
        plano = agentes.preparar_lancamento('Pi', 'gemma4:31b-cloud', True)
        self.assertEqual(plano['modelo'], 'gemma4:31b-cloud')
        self.assertTrue(plano['configurar'])
        self.assertIn('nuvem', plano['descricao'])
        self.assertIn('conta', plano['descricao'])
        self.assertNotIn('modelo instalado', plano['descricao'])

    def test_descricao_cabe_no_plano_mesmo_com_tag_maxima_sem_corta_la(self):
        modelo = 'q' * 194 + '-cloud'
        for item in agentes.INTEGRACOES:
            with self.subTest(agente=item.agente):
                plano = agentes.preparar_lancamento(item.agente, modelo, True)
                self.assertEqual(plano['modelo'], modelo)
                self.assertIn(modelo, plano['descricao'])
                self.assertLessEqual(len(plano['descricao']), 500)
                self.assertIn('nuvem', plano['descricao'])
                self.assertIn('instalar', plano['descricao'])
                self.assertIn('permissões', plano['descricao'])

    def test_dados_de_plano_invalidos_nunca_chegam_a_subprocesso(self):
        for modelo in ('llama3.2; calc', 'x\ny', '--yes', 'modelo "x"', 'a' * 201, [], True):
            with self.subTest(modelo=modelo), self.assertRaises(ValueError):
                self.abrir(modelo=modelo)
        for configurar in (None, 1, 'false'):
            with self.subTest(configurar=configurar), self.assertRaises(ValueError):
                self.abrir(configurar=configurar)
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_path_e_menu_nao_sao_prova_de_instalacao(self):
        self.which.side_effect = lambda nome: str(self.exe) if nome in ('ollama', 'claude') else None
        itens = {item['agente']: item for item in agentes.catalogo_agentes()}
        self.assertEqual(itens['claude']['estado'], 'comando_no_path')
        self.assertEqual(itens['codex']['estado'], 'nao_localizado_no_path')
        self.assertEqual(itens['chatgpt']['estado'], 'verificar_no_lancador')
        self.assertNotIn('instalado', itens['claude'])
        resumo = agentes.resumo_agentes()
        self.assertIn('não são modelos participantes', resumo)
        self.assertIn('não comprovam funcionamento', resumo)
        itens['claude']['nome'] = 'alterado'
        self.assertEqual(agentes.catalogo_agentes()[0]['nome'], 'Claude Code')
        self.run.assert_not_called()

    def test_confirmacao_estrita_antes_de_verificar_ou_abrir(self):
        for confirmado in (False, None, 1, 'sim'):
            with self.subTest(confirmado=confirmado), self.assertRaises(PermissionError):
                agentes.abrir_agente('claude', confirmado=confirmado)
        self.which.assert_not_called()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_fora_windows_nao_executa_lancador(self):
        with patch.object(agentes.sys, 'platform', 'linux'), self.assertRaisesRegex(RuntimeError, 'Windows'):
            self.abrir()
        self.which.assert_not_called()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_script_cmd_e_binario_ausente_sao_recusados(self):
        self.which.return_value = None
        with self.assertRaisesRegex(RuntimeError, 'não localizado'):
            self.abrir()
        falso = self.exe.with_suffix('.cmd')
        falso.write_text('fixture', encoding='utf-8')
        self.which.return_value = str(falso)
        with self.assertRaisesRegex(RuntimeError, 'scripts de shell'):
            self.abrir()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_abertura_usa_allowlist_console_separado_sem_shell_yes_ou_prompt(self):
        texto = self.abrir('Claude Code', 'llama3.2:latest')
        self.run.assert_called_once()
        ajuda = self.run.call_args
        self.assertEqual(ajuda.args[0], [str(self.exe), 'launch', '--help'])
        self.assertEqual(ajuda.kwargs['timeout'], 5)
        self.assertIs(ajuda.kwargs['shell'], False)
        self.assertEqual(ajuda.kwargs['stdin'], subprocess.DEVNULL)
        self.popen.assert_called_once()
        chamada = self.popen.call_args
        self.assertEqual(chamada.args[0], [str(self.exe), 'launch', 'claude', '--model', 'llama3.2:latest'])
        self.assertIs(chamada.kwargs['shell'], False)
        self.assertTrue(chamada.kwargs['close_fds'])
        self.assertEqual(chamada.kwargs['creationflags'], 0x10)
        self.assertEqual(chamada.kwargs['cwd'], str(agentes.BASE))
        self.assertNotIn('--yes', chamada.args[0])
        self.assertNotIn('--', chamada.args[0])
        self.assertIn('não comprova', texto)

    def test_configuracao_nao_adiciona_opcoes_arbitrarias(self):
        self.abrir('deepseek harness', 'gemma4:31b-cloud', True)
        self.assertEqual(self.popen.call_args.args[0],
                         [str(self.exe), 'launch', 'dsh', '--model', 'gemma4:31b-cloud', '--config'])

    def test_modelo_vazio_delega_escolha_interativa_sem_tag_fabricada(self):
        self.abrir('qwen')
        self.assertEqual(self.popen.call_args.args[0], [str(self.exe), 'launch', 'qwen'])

    def test_ambiente_filho_nao_herda_chaves_do_assistente(self):
        with patch.dict(os.environ, {'TELEGRAM_TOKEN': 'fixture-segredo-bot',
                                    'OPENAI_API_KEY': 'fixture-segredo-openai',
                                    'ANTHROPIC_API_KEY': 'fixture-segredo-claude',
                                    'GITHUB_TOKEN': 'fixture-segredo-github',
                                    'OLLAMA_API_KEY': 'fixture-segredo-ollama',
                                    'PYTHONPATH': 'fixture-codigo', 'NODE_OPTIONS': 'fixture-codigo',
                                    'OLLAMA_NO_CLOUD': 'true', 'OLLAMA_URL': 'http://127.0.0.1:11435'}):
            self.abrir()
        for chamada in (self.run.call_args, self.popen.call_args):
            ambiente = chamada.kwargs['env']
            self.assertEqual(ambiente['PATH'], 'fixture-path')
            self.assertEqual({k.upper():v for k,v in ambiente.items()}['SYSTEMROOT'], 'fixture-windows')
            self.assertEqual(ambiente['OLLAMA_HOST'], 'http://127.0.0.1:11435')
            self.assertEqual(ambiente['OLLAMA_NO_CLOUD'], '1')
            self.assertNotIn('fixture-segredo', repr(ambiente))
            self.assertNotIn('PYTHONPATH', ambiente)
            self.assertNotIn('NODE_OPTIONS', ambiente)

    def test_endpoint_remoto_e_recusado_antes_de_executar(self):
        with patch.dict(os.environ, {'OLLAMA_URL': 'http://example.invalid:11434'}), self.assertRaises(ValueError):
            self.abrir()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_ajuda_incompativel_erro_ou_grande_nao_abre_nem_vaza_resposta(self):
        for retorno in (SimpleNamespace(returncode=1, stdout='fixture-segredo'),
                        SimpleNamespace(returncode=0, stdout='Usage: launch'),
                        SimpleNamespace(returncode=0, stdout='x' * (agentes.LIMITE_AJUDA + 1))):
            with self.subTest(retorno=retorno.returncode):
                self.run.return_value = retorno
                with self.assertRaisesRegex(RuntimeError, 'não confirma') as erro:
                    self.abrir()
                self.assertNotIn('fixture-segredo', str(erro.exception))
        self.popen.assert_not_called()

    def test_timeout_ou_falha_ajuda_nao_repete_nem_vaza_saida(self):
        for falha in (subprocess.TimeoutExpired('fixture', 5, output='fixture-segredo'),
                      OSError('fixture-segredo')):
            with self.subTest(falha=type(falha).__name__):
                self.run.reset_mock()
                self.run.side_effect = falha
                with self.assertRaisesRegex(RuntimeError, '5 segundos') as erro:
                    self.abrir()
                self.assertNotIn('fixture-segredo', str(erro.exception))
                self.run.assert_called_once()
        self.popen.assert_not_called()

    def test_erro_de_abertura_e_explicito_sem_detalhe_bruto(self):
        self.popen.side_effect = OSError('fixture-segredo')
        with self.assertRaisesRegex(RuntimeError, 'não abriu') as erro:
            self.abrir()
        self.assertNotIn('fixture-segredo', str(erro.exception))
        self.assertFalse(agentes._LANCAMENTOS)

    def test_mesmo_agente_ativo_nao_dispara_segunda_janela(self):
        self.abrir('claude')
        texto = self.abrir('Claude Code', 'gemma4:31b-cloud')
        self.popen.assert_called_once()
        self.assertIn('Já existe', texto)
        self.assertNotIn('instalado', texto)

    def test_processo_finalizado_pode_ser_aberto_explicitamente_de_novo(self):
        self.abrir('claude')
        self.processo.poll.return_value = 0
        self.abrir('claude')
        self.assertEqual(self.popen.call_count, 2)

    def test_cli_listar_nao_pergunta_nem_abre(self):
        with contextlib.redirect_stdout(io.StringIO()) as saida, patch('builtins.input') as entrada:
            self.assertEqual(agentes.main(['--listar']), 0)
        self.assertIn('Claude Code', saida.getvalue())
        entrada.assert_not_called()
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_cli_cancelar_e_escolha_invalida_encerram_sem_loop(self):
        for entradas in ([''], ['invalido', ''], ['claude', '', 'nao']):
            with self.subTest(entradas=entradas), contextlib.redirect_stdout(io.StringIO()), \
                    patch('builtins.input', side_effect=entradas) as entrada:
                codigo = agentes.main([])
                self.assertIn(codigo, (0, 1))
                self.assertLessEqual(entrada.call_count, 3)
        self.run.assert_not_called()
        self.popen.assert_not_called()

    def test_cli_confirmacao_explicita_abre_uma_vez_sem_prompt_de_tarefa(self):
        with contextlib.redirect_stdout(io.StringIO()), patch('builtins.input') as entrada:
            self.assertEqual(agentes.main(['--agente', 'codex', '--modelo', 'llama3.2:latest', '--confirmar']), 0)
        entrada.assert_not_called()
        self.popen.assert_called_once()
        self.assertEqual(self.popen.call_args.args[0], [str(self.exe), 'launch', 'codex', '--model', 'llama3.2:latest'])


if __name__ == '__main__':
    unittest.main()
