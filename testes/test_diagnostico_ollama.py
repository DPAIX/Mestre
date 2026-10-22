"""Diagnóstico independente com respostas fictícias e sockets só de loopback."""
from __future__ import annotations

import contextlib
import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostico_ollama as diagnostico


class DiagnosticoOllamaTeste(unittest.TestCase):
    def setUp(self):
        ambiente = patch.dict(os.environ, {}, clear=True)
        ambiente.start(); self.addCleanup(ambiente.stop)
        self.segredo = 'fixture-conteudo-privado-nao-exibir'
        self.metadados = {
            '/api/version': {'ok': True, 'dados': {'version': '0.40.7'}},
            '/api/tags': {'ok': True, 'dados': {'models': [
                {'name': 'llama3.2:latest', 'size': 3 * 1024**3},
                {'name': 'gemma4:31b-cloud', 'size': 0}]}},
            '/api/ps': {'ok': True, 'dados': {'models': []}},
        }

    def coletar(self, *, testar_cpu=False, respostas=None):
        respostas = self.metadados if respostas is None else respostas
        def consultar(url, rota, **opcoes):
            return copy.deepcopy(respostas[rota])
        with patch.object(diagnostico, 'memoria_local', return_value={
                'ok': True, 'total_gib': 16, 'livre_gib': 8}), \
                patch.object(diagnostico, 'gpu_local', return_value={
                    'ok': False, 'categoria': 'ferramenta_ausente'}), \
                patch.object(diagnostico, 'versao_cli', return_value={'ok': False}), \
                patch.object(diagnostico, 'consultar', side_effect=consultar) as consulta:
            relatorio = diagnostico.coletar(testar_cpu=testar_cpu)
        return relatorio, consulta

    def servidor_http(self, respostas):
        pedidos = []
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def atender(self):
                tamanho = int(self.headers.get('Content-Length', '0'))
                corpo = self.rfile.read(tamanho) if tamanho else b''
                pedidos.append({'metodo': self.command, 'rota': self.path, 'corpo': corpo})
                codigo, cabecalhos, resposta = respostas.get(
                    self.path, (404, {}, b'fixture-rota-ausente'))
                self.send_response(codigo)
                for nome, valor in cabecalhos.items():
                    self.send_header(nome, valor)
                self.send_header('Content-Length', str(len(resposta)))
                self.end_headers()
                try:
                    self.wfile.write(resposta)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            do_GET = atender
            do_POST = atender

        servidor = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=lambda: servidor.serve_forever(poll_interval=0.01), daemon=True)
        thread.start()
        def encerrar():
            servidor.shutdown()
            servidor.server_close()
            thread.join(timeout=2)
        self.addCleanup(encerrar)
        return f'http://127.0.0.1:{servidor.server_port}', pedidos

    def servidor_lento(self, cabecalho_incompleto):
        servidor = socket.socket()
        servidor.bind(('127.0.0.1', 0))
        servidor.listen(1)
        servidor.settimeout(2)
        encerrar = threading.Event()
        iniciou = threading.Event()
        def atender():
            try:
                conexao, _ = servidor.accept()
                with conexao:
                    conexao.settimeout(1)
                    conexao.recv(8192)
                    inicio = (b'HTTP/1.1 200 OK\r\nX-Fixture-Lento: ' if cabecalho_incompleto
                              else b'HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n{')
                    conexao.sendall(inicio)
                    iniciou.set()
                    fim = time.monotonic() + 1.2
                    while not encerrar.wait(0.025) and time.monotonic() < fim:
                        conexao.sendall(b' ')
            except OSError:
                pass
        thread = threading.Thread(target=atender, daemon=True)
        thread.start()
        def limpar():
            encerrar.set()
            servidor.close()
            thread.join(timeout=2)
        self.addCleanup(limpar)
        return f'http://127.0.0.1:{servidor.getsockname()[1]}', iniciou

    def test_url_aceita_so_ip_literal_loopback_e_normaliza_ipv6(self):
        for entrada, esperado in (
                ('http://127.0.0.1:11434/', 'http://127.0.0.1:11434'),
                ('https://127.0.0.2', 'https://127.0.0.2:443'),
                ('http://[0:0:0:0:0:0:0:1]:11434', 'http://[::1]:11434')):
            with self.subTest(entrada=entrada):
                self.assertEqual(diagnostico.validar_url(entrada), esperado)

    def test_url_remota_host_credencial_caminho_e_porta_invalida_nao_abrem_conexao(self):
        invalidas = (None, 5, '', 'http://localhost:11434', 'https://example.invalid',
                     'http://192.168.1.2:11434', 'http://127.0.0.1:0',
                     'http://127.0.0.1:65536', 'http://127.0.0.1:abc',
                     'http://usuario:segredo@127.0.0.1:11434',
                     'http://127.0.0.1:11434/api/tags', 'http://127.0.0.1?x',
                     'http://127.0.0.1#x', 'http://[::1%25eth0]',
                     ' http://127.0.0.1', 'http://127.0.0.1\n', 'ftp://127.0.0.1')
        with patch.object(diagnostico.http.client, 'HTTPConnection') as conectar:
            for url in invalidas:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    diagnostico.consultar(url, '/api/version')
            conectar.assert_not_called()

    def test_prazo_e_rota_invalidos_sao_rejeitados_antes_de_conectar(self):
        with patch.object(diagnostico.http.client, 'HTTPConnection') as conectar:
            for prazo in (0, -1, 31, True, '3', float('nan'), float('inf')):
                with self.subTest(prazo=prazo), self.assertRaises(ValueError):
                    diagnostico.consultar(diagnostico.URL_PADRAO, '/api/version', timeout=prazo)
            with self.assertRaises(ValueError):
                diagnostico.consultar(diagnostico.URL_PADRAO, '/api/pull')
            conectar.assert_not_called()

    def test_consulta_direta_ignora_proxy_do_ambiente(self):
        url, pedidos = self.servidor_http({'/api/version': (200, {}, b'{"version":"0.40.7"}')})
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://127.0.0.1:1',
                                    'HTTPS_PROXY': 'http://127.0.0.1:1',
                                    'ALL_PROXY': 'http://127.0.0.1:1', 'NO_PROXY': ''}):
            resultado = diagnostico.consultar(url, '/api/version')
        self.assertEqual(resultado, {'ok': True, 'dados': {'version': '0.40.7'}})
        self.assertEqual([(p['metodo'], p['rota']) for p in pedidos], [('GET', '/api/version')])

    def test_redirect_nao_e_seguido_nem_expoe_corpo_ou_cabecalhos(self):
        respostas = {}
        url, pedidos = self.servidor_http(respostas)
        respostas['/api/version'] = (302, {'Location': url + '/destino',
                                         'Authorization': self.segredo}, self.segredo.encode())
        respostas['/destino'] = (200, {}, b'{"version":"0.40.7"}')
        resultado = diagnostico.consultar(url, '/api/version')
        self.assertEqual(resultado, {'ok': False, 'categoria': 'http', 'codigo': 302})
        self.assertEqual([p['rota'] for p in pedidos], ['/api/version'])
        self.assertNotIn(self.segredo, json.dumps(resultado))

    def test_resposta_grande_json_invalido_e_schema_nao_objeto_sao_controlados(self):
        respostas = {}
        url, _ = self.servidor_http(respostas)
        casos = ((b'x' * (diagnostico.LIMITE_RESPOSTA + 1), 'resposta_grande'),
                 (b'\xff', 'resposta_invalida'), (b'{incompleto', 'resposta_invalida'),
                 (b'[1,2,3]', 'resposta_invalida'), (b'null', 'resposta_invalida'))
        for bruto, categoria in casos:
            respostas['/api/tags'] = (200, {}, bruto)
            with self.subTest(categoria=categoria, tamanho=len(bruto)):
                self.assertEqual(diagnostico.consultar(url, '/api/tags'),
                                 {'ok': False, 'categoria': categoria})

    def test_nan_infinity_e_overflow_decimal_nao_sao_aceitos_como_json_finito(self):
        respostas = {}
        url, _ = self.servidor_http(respostas)
        for valor in ('NaN', 'Infinity', '-Infinity', '1e999', '-1e999'):
            respostas['/api/tags'] = (200, {}, ('{"size":' + valor + '}').encode())
            with self.subTest(valor=valor):
                self.assertEqual(diagnostico.consultar(url, '/api/tags'),
                                 {'ok': False, 'categoria': 'resposta_invalida'})

    def test_deadline_total_interrompe_cabecalhos_e_corpo_que_pingam_bytes(self):
        for cabecalho in (True, False):
            with self.subTest(cabecalho=cabecalho):
                url, iniciou = self.servidor_lento(cabecalho)
                inicio = time.monotonic()
                resultado = diagnostico.consultar(url, '/api/version', timeout=0.16)
                duracao = time.monotonic() - inicio
                self.assertTrue(iniciou.is_set())
                self.assertEqual(resultado, {'ok': False, 'categoria': 'timeout'})
                self.assertLess(duracao, 0.8, 'Bytes parciais não podem renovar o prazo total.')

    def test_conexao_fechada_prematuramente_nao_expoe_erro_bruto(self):
        with patch.object(diagnostico.http.client.HTTPConnection, 'connect',
                          side_effect=OSError(self.segredo)):
            resultado = diagnostico.consultar(diagnostico.URL_PADRAO, '/api/version')
        self.assertEqual(resultado, {'ok': False, 'categoria': 'conexao'})
        self.assertNotIn(self.segredo, json.dumps(resultado))

    def test_padrao_faz_so_tres_gets_sem_geracao_nem_leitura_ou_escrita_de_arquivos(self):
        ambiente = os.environ.copy()
        with patch('builtins.open', side_effect=AssertionError('Não acessar arquivos')), \
                patch.object(io, 'open', side_effect=AssertionError('Não acessar arquivos')), \
                patch.object(diagnostico.subprocess, 'run', side_effect=AssertionError('Não executar processos')):
            relatorio, consulta = self.coletar()
        self.assertEqual([c.args[1] for c in consulta.call_args_list],
                         ['/api/version', '/api/tags', '/api/ps'])
        self.assertTrue(all(not c.kwargs for c in consulta.call_args_list))
        self.assertEqual(relatorio['teste_cpu'], {'executado': False})
        self.assertEqual(os.environ.copy(), ambiente)
        self.assertIn('não comprovam geração', ' '.join(relatorio['orientacoes']))

    def test_relatorio_filtra_campos_brutos_hosts_prompts_e_credenciais(self):
        respostas = copy.deepcopy(self.metadados)
        for item in respostas.values():
            item['dados']['api_key'] = self.segredo
            item['dados']['prompt'] = self.segredo
            item['dados']['stdout'] = self.segredo
        respostas['/api/tags']['dados']['models'][0].update({
            'template': self.segredo, 'system': self.segredo,
            'details': {'remote_host': self.segredo, 'client_secret': self.segredo}})
        respostas['/api/ps']['dados']['models'] = [{
            'name': 'qwen3.5:4b', 'size': 3 * 1024**3, 'size_vram': 1024**3,
            'context_length': 1024, 'remote_model': self.segredo, 'details': {'token': self.segredo}}]
        relatorio, _ = self.coletar(respostas=respostas)
        texto = json.dumps(relatorio, allow_nan=False)
        self.assertNotIn(self.segredo, texto)
        for campo in ('api_key', 'prompt', 'stdout', 'template', 'system', 'remote_host', 'remote_model', 'client_secret'):
            self.assertNotIn('"' + campo + '"', texto)
        self.assertEqual(relatorio['servico'], {'ok': True, 'versao': '0.40.7'})
        self.assertIs(relatorio['catalogo']['modelos'][0]['nuvem'], True)
        carregado = relatorio['carregados']['modelos'][0]
        self.assertEqual(carregado['vram_gib'], 1.0)
        self.assertEqual(carregado['contexto'], 1024)

    def test_schemas_estranhos_e_numeros_gigantes_nao_quebram_relatorio(self):
        respostas = copy.deepcopy(self.metadados)
        respostas['/api/version']['dados']['version'] = {'segredo': self.segredo}
        respostas['/api/tags']['dados']['models'] = [None, self.segredo,
            {'name': 'nome invalido ' + self.segredo},
            {'name': 'llama3.2:latest', 'size': 10**400, 'details': [self.segredo]}]
        respostas['/api/ps']['dados']['models'] = {'segredo': self.segredo}
        relatorio, _ = self.coletar(respostas=respostas)
        self.assertEqual(relatorio['servico'], {'ok': False, 'categoria': 'resposta_invalida'})
        self.assertEqual(relatorio['carregados'], {'ok': False, 'categoria': 'resposta_invalida'})
        self.assertEqual(relatorio['catalogo']['modelos'], [
            {'nome': 'llama3.2:latest', 'nuvem': False, 'tamanho_gib': None}])
        self.assertNotIn(self.segredo, json.dumps(relatorio, allow_nan=False))

    def test_teste_cpu_local_uma_chamada_com_limites_e_sem_expor_texto_gerado(self):
        respostas = copy.deepcopy(self.metadados)
        respostas['/api/chat'] = {'ok': True, 'dados': {
            'message': {'content': self.segredo}, 'context': self.segredo, 'api_key': self.segredo}}
        relatorio, consulta = self.coletar(testar_cpu=True, respostas=respostas)
        chamadas = [c for c in consulta.call_args_list if c.args[1] == '/api/chat']
        self.assertEqual(len(chamadas), 1)
        self.assertEqual(chamadas[0].kwargs, {
            'timeout': 30, 'payload': {'model': 'llama3.2:latest', 'stream': False, 'keep_alive': 0,
                'messages': [{'role': 'user', 'content': 'Responda apenas OK.'}],
                'options': {'num_gpu': 0, 'num_ctx': 1024, 'num_predict': 8}}})
        self.assertIs(relatorio['teste_cpu']['executado'], True)
        self.assertIs(relatorio['teste_cpu']['ok'], True)
        self.assertIs(relatorio['teste_cpu']['gpu_solicitada'], False)
        self.assertNotIn(self.segredo, json.dumps(relatorio, allow_nan=False))

    def test_cpu_exige_tag_exata_local_sem_download_nem_fallback_cloud(self):
        casos = ([], [{'name': 'llama3.2'}], [{'name': 'llama3.2:latest-cloud'}],
                 [{'name': 'llama3.2:latest', 'remote_model': 'llama-remoto'}],
                 [{'name': 'llama3.2:latest', 'details': {'remote_host': 'fixture-cloud'}}],
                 [{'name': 'llama3.2:latest'}, {'name': 'llama3.2:latest', 'remote_host': 'fixture-cloud'}])
        for modelos in casos:
            respostas = copy.deepcopy(self.metadados)
            respostas['/api/tags']['dados']['models'] = modelos
            with self.subTest(modelos=modelos):
                relatorio, consulta = self.coletar(testar_cpu=True, respostas=respostas)
                self.assertEqual(relatorio['teste_cpu'], {
                    'executado': False, 'categoria': 'modelo_local_nao_confirmado'})
                self.assertEqual([c.args[1] for c in consulta.call_args_list],
                                 ['/api/version', '/api/tags', '/api/ps'])

    def test_timeout_cpu_e_resposta_sem_texto_nao_repetem_geracao(self):
        for retorno in ({'ok': False, 'categoria': 'timeout'},
                        {'ok': True, 'dados': {'message': {'content': '   '}}}):
            respostas = copy.deepcopy(self.metadados)
            respostas['/api/chat'] = retorno
            with self.subTest(retorno=retorno):
                relatorio, consulta = self.coletar(testar_cpu=True, respostas=respostas)
                self.assertIs(relatorio['teste_cpu']['executado'], True)
                self.assertIs(relatorio['teste_cpu']['ok'], False)
                self.assertEqual(relatorio['teste_cpu']['categoria'],
                                 'timeout' if not retorno['ok'] else 'sem_texto')
                self.assertEqual(sum(c.args[1] == '/api/chat' for c in consulta.call_args_list), 1)
                self.assertEqual(consulta.call_count, 4)

    def test_flag_cpu_nao_booleana_e_url_remota_nao_iniciam_hardware_ou_rede(self):
        with patch.object(diagnostico, 'memoria_local') as memoria, \
                patch.object(diagnostico, 'gpu_local') as gpu, \
                patch.object(diagnostico, 'consultar') as consulta:
            for valor in (1, 'on', None):
                with self.subTest(valor=valor), self.assertRaises(ValueError):
                    diagnostico.coletar(testar_cpu=valor)
            with self.assertRaises(ValueError):
                diagnostico.coletar('https://example.invalid')
            memoria.assert_not_called(); gpu.assert_not_called(); consulta.assert_not_called()

    def test_subprocesso_gpu_tem_prazo_shell_desativado_e_ambiente_sem_segredos(self):
        comando = ['fixture-nvidia-smi', '--query-gpu=memory.total']
        retorno = SimpleNamespace(returncode=0, stdout=self.segredo, stderr=self.segredo)
        with patch.dict(os.environ, {'PATH': 'fixture-path', 'SystemRoot': 'fixture-windows',
                                    'OPENAI_API_KEY': self.segredo, 'PYTHONPATH': self.segredo,
                                    'OLLAMA_MODEL': self.segredo}), \
                patch.object(diagnostico.subprocess, 'run', return_value=retorno) as executar:
            self.assertIs(diagnostico._executar(comando), retorno)
        executar.assert_called_once()
        self.assertEqual(executar.call_args.args, (comando,))
        opcoes = executar.call_args.kwargs
        self.assertEqual(opcoes['timeout'], 5)
        self.assertIs(opcoes['shell'], False)
        self.assertEqual(opcoes['stdin'], subprocess.DEVNULL)
        # os.environ normaliza nomes para maiúsculas no Windows.
        self.assertEqual({chave.upper():valor for chave,valor in opcoes['env'].items()},
                         {'PATH':'fixture-path','SYSTEMROOT':'fixture-windows'})
        self.assertNotIn(self.segredo, json.dumps(opcoes['env']))

    def test_timeout_ou_falta_de_ferramenta_gpu_nao_expoem_saida_bruta(self):
        erro = subprocess.TimeoutExpired(['fixture-gpu'], 5, output=self.segredo, stderr=self.segredo)
        for falha in (erro, OSError(self.segredo)):
            with self.subTest(falha=type(falha).__name__), \
                    patch.object(diagnostico.subprocess, 'run', side_effect=falha):
                self.assertIsNone(diagnostico._executar(['fixture-gpu']))
        with patch.object(diagnostico.shutil, 'which', return_value=None), \
                patch.object(diagnostico, '_executar') as executar:
            self.assertEqual(diagnostico.gpu_local(), {'ok': False, 'categoria': 'ferramenta_ausente'})
            executar.assert_not_called()

    def test_subprocesso_cli_usa_url_loopback_explicita_sem_herdar_host_externo(self):
        with patch.dict(os.environ, {'OLLAMA_HOST': 'http://192.168.1.2:11434',
                                    'OPENAI_API_KEY': self.segredo}), \
                patch.object(diagnostico.subprocess, 'run') as executar:
            diagnostico._executar(['fixture-ollama', '--version'], url='http://127.0.0.1:11435')
            self.assertEqual(executar.call_args.kwargs['env'], {'OLLAMA_HOST': 'http://127.0.0.1:11435'})
            executar.reset_mock()
            with self.assertRaises(ValueError):
                diagnostico._executar(['fixture-ollama', '--version'], url='https://example.invalid')
            executar.assert_not_called()

    def test_versao_cli_prioriza_cliente_e_descarta_saida_e_erros_brutos(self):
        retorno = SimpleNamespace(returncode=0, stdout=(
            'ollama version is 0.39.1\n' + self.segredo),
            stderr='Warning: client version is 0.40.7\n' + self.segredo)
        with patch.object(diagnostico.shutil, 'which', return_value='fixture-ollama'), \
                patch.object(diagnostico, '_executar', return_value=retorno) as executar:
            resultado = diagnostico.versao_cli('http://127.0.0.1:11435')
        self.assertEqual(resultado, {'ok': True, 'versao_informada': '0.40.7'})
        executar.assert_called_once_with(['fixture-ollama', '--version'], url='http://127.0.0.1:11435')
        self.assertNotIn(self.segredo, json.dumps(resultado))
        retorno.stdout = self.segredo
        retorno.stderr = self.segredo
        with patch.object(diagnostico.shutil, 'which', return_value='fixture-ollama'), \
                patch.object(diagnostico, '_executar', return_value=retorno):
            self.assertEqual(diagnostico.versao_cli(), {'ok': False, 'categoria': 'versao_nao_identificada'})

    def test_cli_ausente_ou_com_timeout_nao_persiste_nem_expoe_resultado_bruto(self):
        with patch.object(diagnostico.shutil, 'which', return_value=None), \
                patch.object(diagnostico, '_executar') as executar:
            self.assertEqual(diagnostico.versao_cli(), {'ok': False, 'categoria': 'ferramenta_ausente'})
            executar.assert_not_called()
        for retorno in (None, SimpleNamespace(returncode=1, stdout=self.segredo, stderr=self.segredo)):
            with self.subTest(retorno=retorno is None), \
                    patch.object(diagnostico.shutil, 'which', return_value='fixture-ollama'), \
                    patch.object(diagnostico, '_executar', return_value=retorno):
                self.assertEqual(diagnostico.versao_cli(), {'ok': False, 'categoria': 'consulta_indisponivel'})

    def test_gpu_filtra_csv_e_retorna_so_metricas_conhecidas(self):
        retorno = SimpleNamespace(returncode=0, stdout=(
            '8192,4096,25,570.42\n' + self.segredo + '\n'
            '4096,2048,10,550.11\n1,2,3,Authorization=' + self.segredo), stderr=self.segredo)
        with patch.object(diagnostico.shutil, 'which', return_value='fixture-nvidia-smi'), \
                patch.object(diagnostico, '_executar', return_value=retorno) as executar:
            resultado = diagnostico.gpu_local()
        self.assertEqual(resultado, {'ok': True, 'placas': [
            {'vram_total_mib': 8192, 'vram_livre_mib': 4096, 'uso_percentual': 25, 'driver': '570.42'},
            {'vram_total_mib': 4096, 'vram_livre_mib': 2048, 'uso_percentual': 10, 'driver': '550.11'}]})
        self.assertNotIn(self.segredo, json.dumps(resultado))
        self.assertEqual(executar.call_args.args[0], [
            'fixture-nvidia-smi', '--query-gpu=memory.total,memory.free,utilization.gpu,driver_version',
            '--format=csv,noheader,nounits'])

    def test_memoria_posix_usa_apenas_sysconf_e_falha_de_forma_controlada(self):
        valores = {'SC_PAGE_SIZE': 4096, 'SC_PHYS_PAGES': 4 * 1024**2, 'SC_AVPHYS_PAGES': 2 * 1024**2}
        with patch.object(diagnostico.sys, 'platform', 'linux'), \
                patch.object(diagnostico.os, 'sysconf', side_effect=valores.__getitem__, create=True):
            self.assertEqual(diagnostico.memoria_local(), {'ok': True, 'total_gib': 16.0, 'livre_gib': 8.0})
        with patch.object(diagnostico.sys, 'platform', 'linux'), \
                patch.object(diagnostico.os, 'sysconf', side_effect=OSError(self.segredo), create=True):
            self.assertEqual(diagnostico.memoria_local(), {'ok': False})

    def test_memoria_windows_inclui_commit_sem_chamar_api_real(self):
        def consultar_memoria(ponteiro):
            memoria = ponteiro._obj
            memoria.fisica_total = 16 * 1024**3
            memoria.fisica_livre = 3 * 1024**3
            memoria.pagina_total = 24 * 1024**3
            memoria.pagina_livre = 5 * 1024**3
            return 1
        kernel = SimpleNamespace(GlobalMemoryStatusEx=consultar_memoria)
        with patch.object(diagnostico.sys, 'platform', 'win32'), \
                patch.object(diagnostico.ctypes, 'windll', SimpleNamespace(kernel32=kernel), create=True):
            self.assertEqual(diagnostico.memoria_local(), {
                'ok': True, 'total_gib': 16.0, 'livre_gib': 3.0,
                'commit_limite_gib': 24.0, 'commit_disponivel_gib': 5.0})

    def test_cli_url_invalida_nao_imprime_credencial_nem_traceback(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida), patch.object(diagnostico, 'gpu_local') as gpu:
            codigo = diagnostico.main(['--url', 'http://usuario:' + self.segredo + '@127.0.0.1'])
        self.assertEqual(codigo, 2)
        self.assertNotIn(self.segredo, saida.getvalue())
        self.assertNotIn('Traceback', saida.getvalue())
        gpu.assert_not_called()


if __name__ == '__main__':
    unittest.main()
