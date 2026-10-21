"""Configuração Ollama com .env temporário, HTTP e downloads simulados."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as local


class ConfiguracaoIALocal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = Path(self.temp.name) / '.env'
        self.env.write_text('# opções locais\nTELEGRAM_TOKEN=fixture-preservar\n', encoding='utf-8')
        ambiente = patch.dict(os.environ, {}, clear=True)
        ambiente.start()
        self.addCleanup(ambiente.stop)
        self.saida = io.StringIO()
        redirecionar = contextlib.redirect_stdout(self.saida)
        redirecionar.__enter__()
        self.addCleanup(redirecionar.__exit__, None, None, None)

    def test_url_restringe_ao_proprio_pc_sem_dns(self):
        for url in ('http://localhost:11434', 'http://192.168.1.1:11434',
                    'http://example.com', 'http://127.0.0.1@evil.example',
                    'http://user:senha@127.0.0.1:11434', 'http://127.0.0.1/api',
                    'http://127.0.0.1?x=1', 'http://127.0.0.1#x',
                    'http://127.0.0.1:0', 'http://[::1%eth0]:11434',
                    'file:///tmp/exemplo', 'http://127.0.0.1\n'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                local.validar_url(url)
        self.assertEqual(local.validar_url('http://127.0.0.1:11434/'), local.URL_PADRAO)
        self.assertEqual(local.validar_url('http://[::1]:11434'), 'http://[::1]:11434')

    def test_modelo_rejeita_argumentos_e_injecao(self):
        for modelo in ('', '--help', 'qwen; comando', 'qwen\nOLLAMA_HABILITADO=1',
                       'qwen && comando', '../modelo', 'a b', 'x' * 201):
            with self.subTest(modelo=modelo), self.assertRaises(ValueError):
                local.validar_modelo(modelo)
        self.assertEqual(local.validar_modelo('biblioteca/qwen2.5:3b'), 'biblioteca/qwen2.5:3b')

    def test_tags_consulta_curta_sem_proxy_e_fecha_resposta(self):
        resposta = io.BytesIO(json.dumps({'models': [{'name': local.MODELO_PADRAO}]}).encode())
        cliente = MagicMock()
        cliente.open.return_value = resposta
        with patch.object(local.urllib.request, 'build_opener', return_value=cliente) as construir:
            self.assertEqual(local.listar_modelos(), [local.MODELO_PADRAO])
        self.assertTrue(resposta.closed)
        self.assertEqual(cliente.open.call_args.args[0].full_url, local.URL_PADRAO + '/api/tags')
        self.assertEqual(cliente.open.call_args.kwargs['timeout'], local.TIMEOUT_CONSULTA)
        self.assertEqual(construir.call_args.args[0].proxies, {})
        self.assertIsInstance(construir.call_args.args[1], local.SemRedirecionamento)

    def test_redirecionamento_nao_e_seguido(self):
        self.assertIsNone(local.SemRedirecionamento().redirect_request(None, None, 302, '', {}, 'http://example.com'))

    def test_tags_invalidas_sao_falha_controlada(self):
        for corpo in (b'null', b'[]', b'{}', b'not json', b'\xff',
                      b'{"models":null}', b'{"models":[null]}',
                      b'{"models":[{"name":"nome\\nmalformado"}]}'):
            cliente = MagicMock()
            cliente.open.return_value = io.BytesIO(corpo)
            with self.subTest(corpo=corpo), patch.object(local.urllib.request, 'build_opener', return_value=cliente):
                with self.assertRaises(local.FalhaConfiguracao):
                    local.listar_modelos()

    def test_resposta_grande_e_limitada(self):
        resposta = io.BytesIO(b'x' * (local.LIMITE_RESPOSTA + 10))
        cliente = MagicMock()
        cliente.open.return_value = resposta
        with patch.object(local.urllib.request, 'build_opener', return_value=cliente):
            with self.assertRaises(local.FalhaConfiguracao):
                local.listar_modelos()
        self.assertTrue(resposta.closed)

    def test_http_error_e_fechado_sem_exibir_corpo(self):
        corpo = io.BytesIO(b'conteudo-local-nao-exibir')
        erro = HTTPError(local.URL_PADRAO, 503, 'Falha', {}, corpo)
        cliente = MagicMock()
        cliente.open.side_effect = erro
        with patch.object(local.urllib.request, 'build_opener', return_value=cliente):
            with self.assertRaises(local.FalhaConfiguracao) as exc:
                local.listar_modelos()
        self.assertTrue(corpo.closed)
        self.assertIn('HTTP 503', str(exc.exception))
        self.assertNotIn('conteudo-local', str(exc.exception))

    def test_servico_desligado_nao_grava_configuracao(self):
        antes = self.env.read_bytes()
        cliente = MagicMock()
        cliente.open.side_effect = URLError('mensagem-bruta-local')
        with patch.object(local.urllib.request, 'build_opener', return_value=cliente):
            self.assertEqual(local.main(['--modelo', local.MODELO_PADRAO], self.env), 2)
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('Instale e abra', self.saida.getvalue())
        self.assertNotIn('mensagem-bruta-local', self.saida.getvalue())

    def test_verificar_nao_escreve_nem_promete_inferencia(self):
        antes = self.env.read_bytes()
        with patch.object(local, 'listar_catalogo', return_value=[{'nome': local.MODELO_PADRAO, 'nuvem': False}]), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--verificar'], self.env), 0)
            baixar.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('ainda não testada', self.saida.getvalue())

    def test_verificar_modelo_ausente_indica_como_baixar(self):
        with patch.object(local, 'listar_catalogo', return_value=[]), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--verificar'], self.env), 2)
            baixar.assert_not_called()
        self.assertIn('ollama pull qwen2.5:3b', self.saida.getvalue())

    def test_modelo_ausente_nao_e_ativado(self):
        antes = self.env.read_bytes()
        with patch.object(local, 'listar_modelos', return_value=['outro:latest']):
            with self.assertRaises(local.FalhaConfiguracao):
                local.configurar_modelo(local.MODELO_PADRAO, caminho=self.env)
        self.assertEqual(self.env.read_bytes(), antes)

    def test_configuracao_preserva_demais_linhas_e_remove_duplicatas_locais(self):
        original = ('\ufeff# cabeçalho\r\nTELEGRAM_TOKEN=fixture-preservar\r\n'
                    'OPENAI_API_KEY=fixture-outro\r\nOLLAMA_MODEL=antigo\r\n'
                    'OLLAMA_MODEL=duplicado\r\n# OLLAMA_HABILITADO=0\r\n')
        self.env.write_bytes(original.encode('utf-8'))
        with patch.object(local, 'listar_modelos', return_value=[local.MODELO_PADRAO]):
            self.assertEqual(local.configurar_modelo(local.MODELO_PADRAO, caminho=self.env), local.MODELO_PADRAO)
        bruto = self.env.read_bytes()
        self.assertTrue(bruto.startswith(b'\xef\xbb\xbf'))
        self.assertIn(b'TELEGRAM_TOKEN=fixture-preservar\r\n', bruto)
        self.assertIn(b'OPENAI_API_KEY=fixture-outro\r\n', bruto)
        texto = bruto.decode('utf-8-sig')
        self.assertEqual(texto.count('OLLAMA_MODEL='), 1)
        self.assertIn('# OLLAMA_HABILITADO=0\r\n', texto)
        self.assertEqual(local.valores_env(self.env), {
            'OLLAMA_HABILITADO': '1', 'OLLAMA_URL': local.URL_PADRAO, 'OLLAMA_MODEL': local.MODELO_PADRAO,
        })

    def test_alias_sem_tag_usa_modelo_latest_instalado(self):
        with patch.object(local, 'listar_modelos', return_value=['gemma3:latest']):
            local.configurar_modelo('gemma3', caminho=self.env)
        self.assertEqual(local.valores_env(self.env)['OLLAMA_MODEL'], 'gemma3:latest')

    def test_falha_atomica_preserva_original_e_remove_temporario(self):
        antes = self.env.read_bytes()
        with patch.object(local.os, 'replace', side_effect=PermissionError('simulado')):
            with self.assertRaises(PermissionError):
                local.atualizar_env(local.MODELO_PADRAO, caminho=self.env)
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertEqual(list(self.env.parent.glob('.env.ollama.*.tmp')), [])

    def test_download_e_explicito_sem_shell_e_revalida_presenca(self):
        resultado = MagicMock(returncode=0)
        with patch.object(local, 'listar_modelos', side_effect=[[], [local.MODELO_PADRAO]]) as tags, \
                patch.object(local.shutil, 'which', return_value='/fixture/ollama'), \
                patch.object(local.subprocess, 'run', return_value=resultado) as executar:
            local.baixar_modelo(local.MODELO_PADRAO, caminho=self.env)
        self.assertEqual(tags.call_count, 2)
        self.assertEqual(executar.call_args.args[0], ['/fixture/ollama', 'pull', local.MODELO_PADRAO])
        self.assertFalse(executar.call_args.kwargs['shell'])
        self.assertEqual(executar.call_args.kwargs['timeout'], local.TIMEOUT_DOWNLOAD)
        self.assertEqual(executar.call_args.kwargs['env']['OLLAMA_HOST'], local.URL_PADRAO)
        self.assertEqual(local.valores_env(self.env)['OLLAMA_HABILITADO'], '1')

    def test_timeout_de_download_nao_ativa_modelo(self):
        antes = self.env.read_bytes()
        with patch.object(local, 'listar_modelos', return_value=[]), \
                patch.object(local.shutil, 'which', return_value='/fixture/ollama'), \
                patch.object(local.subprocess, 'run', side_effect=subprocess.TimeoutExpired('ollama', local.TIMEOUT_DOWNLOAD)):
            self.assertEqual(local.main(['--baixar-modelo', local.MODELO_PADRAO], self.env), 2)
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('pode continuar', self.saida.getvalue())

    def test_pull_terminado_sem_modelo_nao_e_sucesso(self):
        antes = self.env.read_bytes()
        with patch.object(local, 'listar_modelos', return_value=[]), \
                patch.object(local.shutil, 'which', return_value='/fixture/ollama'), \
                patch.object(local.subprocess, 'run', return_value=MagicMock(returncode=0)):
            with self.assertRaises(local.FalhaConfiguracao):
                local.baixar_modelo(local.MODELO_PADRAO, caminho=self.env)
        self.assertEqual(self.env.read_bytes(), antes)

    def test_catalogo_classifica_nuvem_por_sufixo_ou_metadados_e_remove_duplicatas(self):
        dados = {'models': [
            {'name': 'qwen3.5:4b'},
            {'name': 'gemma4:31b-cloud'},
            {'name': 'outro:cloud'},
            {'name': 'alias:latest', 'remote_model': 'gemma4:31b'},
            {'name': 'segundo:latest', 'details': {'remote_host': 'https://nao-consultar.example'}},
            {'name': 'alias:latest'},
        ]}
        cliente = MagicMock()
        cliente.open.return_value = io.BytesIO(json.dumps(dados).encode())
        with patch.object(local.urllib.request, 'build_opener', return_value=cliente):
            catalogo = local.listar_catalogo()
        self.assertEqual(catalogo, [
            {'nome': 'qwen3.5:4b', 'nuvem': False},
            {'nome': 'gemma4:31b-cloud', 'nuvem': True},
            {'nome': 'outro:cloud', 'nuvem': True},
            {'nome': 'alias:latest', 'nuvem': True},
            {'nome': 'segundo:latest', 'nuvem': True},
        ])
        self.assertEqual(cliente.open.call_count, 1)
        self.assertNotIn('nao-consultar.example', repr(catalogo))
        self.assertTrue(local.modelo_em_nuvem('MODELO:CLOUD'))
        self.assertFalse(local.modelo_em_nuvem('cloud/local:4b'))

    def test_listar_nao_altera_env_nem_baixa_e_informa_cloud(self):
        antes = self.env.read_bytes()
        catalogo = [{'nome': 'qwen3.5:4b', 'nuvem': False}, {'nome': 'gemma4:31b-cloud', 'nuvem': True}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--listar'], self.env), 0)
            baixar.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('qwen3.5:4b — local', self.saida.getvalue())
        self.assertIn('internet, conta e cota', self.saida.getvalue())
        self.assertNotIn('disponível no disco', self.saida.getvalue())

    def test_verificar_cloud_nao_promete_modelo_no_disco_nem_inferencia(self):
        catalogo = [{'nome': 'gemma4:31b-cloud', 'nuvem': True}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo):
            self.assertTrue(local.verificar('gemma4:31b-cloud'))
        self.assertIn('cloud, com execução remota', self.saida.getvalue())
        self.assertIn('ainda não testada', self.saida.getvalue())
        self.assertNotIn('no disco', self.saida.getvalue())

    def test_usar_existente_reaproveita_local_sem_pull_nem_cloud_automatico(self):
        catalogo = [{'nome': 'gemma4:31b-cloud', 'nuvem': True}, {'nome': 'qwen3.5:4b', 'nuvem': False}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--usar-existente'], self.env), 0)
            baixar.assert_not_called()
        self.assertEqual(local.valores_env(self.env)['OLLAMA_MODEL'], 'qwen3.5:4b')
        self.assertIn('Nenhum modelo adicional foi baixado', self.saida.getvalue())

    def test_usar_existente_preserva_modelo_local_configurado(self):
        self.env.write_text('OLLAMA_MODEL=qwen3.5:4b\n', encoding='utf-8')
        catalogo = [{'nome': local.MODELO_PADRAO, 'nuvem': False}, {'nome': 'qwen3.5:4b', 'nuvem': False}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo):
            self.assertEqual(local.main(['--usar-existente'], self.env), 0)
        self.assertEqual(local.valores_env(self.env)['OLLAMA_MODEL'], 'qwen3.5:4b')

    def test_usar_existente_so_cloud_nao_grava_configuracao_nem_baixa(self):
        antes = self.env.read_bytes()
        catalogo = [{'nome': 'alias:latest', 'nuvem': True}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--usar-existente'], self.env), 3)
            baixar.assert_not_called()
        self.assertEqual(self.env.read_bytes(), antes)
        self.assertIn('Nenhum modelo local', self.saida.getvalue())

    def test_cloud_so_e_ativado_por_nome_explicito(self):
        with patch.object(local, 'listar_modelos', return_value=['gemma4:31b-cloud']), patch.object(local.subprocess, 'run') as baixar:
            self.assertEqual(local.main(['--modelo', 'gemma4:31b-cloud'], self.env), 0)
            baixar.assert_not_called()
        self.assertEqual(local.valores_env(self.env)['OLLAMA_MODEL'], 'gemma4:31b-cloud')
        self.assertIn('precisam de internet, conta e cota', self.saida.getvalue())

    def test_interativo_prefere_local_presente_em_vez_de_modelo_padrao_ausente(self):
        catalogo = [{'nome': 'gemma4:31b-cloud', 'nuvem': True}, {'nome': 'qwen3.5:4b', 'nuvem': False}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo), patch('builtins.input', return_value='') as entrada:
            self.assertEqual(local.main([], self.env), 0)
        self.assertIn('[qwen3.5:4b]', entrada.call_args.args[0])
        self.assertEqual(local.valores_env(self.env)['OLLAMA_MODEL'], 'qwen3.5:4b')

    def test_interativo_so_cloud_enter_cancela_sem_alterar_configuracao(self):
        antes = self.env.read_bytes()
        catalogo = [{'nome': 'gemma4:31b-cloud', 'nuvem': True}]
        with patch.object(local, 'listar_catalogo', return_value=catalogo), patch('builtins.input', return_value=''):
            self.assertEqual(local.main([], self.env), 2)
        self.assertEqual(self.env.read_bytes(), antes)


if __name__ == '__main__':
    unittest.main()
