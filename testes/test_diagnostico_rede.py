"""Regressões com dados fictícios, sem consultas ao Windows ou à rede real."""
from __future__ import annotations

import base64
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnostico_rede as diag


def amostra():
    return {'sistema': {'estado': 'consultado', 'adaptadores': [
        {'indice': 4, 'estado': 'Up', 'recebidos': 1000, 'enviados': 2000}],
        'proxy': {}}, 'sondas': {'tcp_a': {'conectou': True},
        'tcp_b': {'conectou': False}, 'dns': {'resolveu': True, 'estado': 'consultado'}}}


class DiagnosticoRedeTeste(unittest.TestCase):
    def test_esquema_descarta_identificadores_e_segredos(self):
        privado = 'fixture-privada-usuario@example.invalid:senha'
        dados = {
            'hostname': privado,
            'adaptadores': [{'indice': 4, 'estado': 'Up', 'recebidos': 100, 'enviados': 200,
                             'mac': privado, 'SSID': privado, 'IP': privado}],
            'gateways': [{'indice': 4, 'responde': True, 'endereco': privado}],
            'processos': [{'nome': 'ollama', 'pid': 123, 'cpu_segundos': 1.5,
                          'memoria_bytes': 600, 'CommandLine': privado}],
            'proxy': {'manual': True, 'tipo': 'loopback', 'pac_configurado': True,
                      'ProxyServer': privado, 'AutoConfigURL': privado},
            'recursos': {'ram_total_kib': 1000, 'ram_livre_kib': 300, 'cpu_percentual': 10,
                         'username': privado}}
        filtrado = diag._filtrar_sistema(dados)
        self.assertNotIn(privado, json.dumps(filtrado))
        self.assertEqual(filtrado['proxy'], {'manual': True, 'tipo': 'loopback', 'pac_configurado': True})
        self.assertEqual(filtrado['processos'][0]['nome'], 'ollama')

    def test_tipos_invalidos_nao_entram_no_relatorio(self):
        dados = {'adaptadores': [{'indice': True}, {'indice': 3, 'estado': 'segredo',
                    'recebidos': float('nan'), 'enviados': 10**400}],
                 'gateways': [{'indice': 3, 'responde': 'segredo'}],
                 'processos': [{'nome': {}, 'pid': 3}, {'nome': 'browser-privado', 'pid': 4}],
                 'recursos': {'cpu_percentual': float('inf'), 'ram_livre_kib': -1},
                 'proxy': {'tipo': 'https://segredo', 'manual': 'segredo'}}
        filtrado = diag._filtrar_sistema(dados)
        self.assertNotIn('segredo', json.dumps(filtrado, allow_nan=False))
        self.assertEqual(filtrado['adaptadores'], [{'indice': 3, 'estado': 'Unknown',
                         'recebidos': None, 'enviados': None}])
        self.assertEqual(filtrado['processos'], [])
        self.assertEqual(filtrado['recursos'], {})
        self.assertEqual(diag._filtrar_sistema([]), {'estado': 'resposta_invalida'})

    def test_listas_de_coleta_sao_limitadas(self):
        filtrado = diag._filtrar_sistema({'adaptadores': [{'indice': n} for n in range(100)],
            'gateways': [{'indice': n} for n in range(100)],
            'processos': [{'nome': 'node', 'pid': n} for n in range(100)]})
        self.assertEqual([len(filtrado[k]) for k in ('adaptadores', 'gateways', 'processos')], [32, 2, 32])

    def powershell(self, resultado=None, erro=None):
        resultado = resultado or SimpleNamespace(returncode=0, stdout=b'{"campo":"ficticio"}')
        with patch.object(diag.sys, 'platform', 'win32'), \
             patch.dict(os.environ, {'SystemRoot': r'C:\Windows', 'PATH': 'fixturepath',
                       'SECRET_API_KEY': 'fixture-segredo', 'HTTP_PROXY': 'fixture-proxy'}, clear=True), \
             patch.object(diag.Path, 'is_file', return_value=True), \
             patch.object(diag.subprocess, 'run', return_value=resultado, side_effect=erro) as executar:
            retorno = diag._powershell(diag._DNS_PS, 2)
        return retorno, executar

    def test_powershell_fixado_sem_shell_perfis_ou_ambiente_privado(self):
        retorno, executar = self.powershell()
        self.assertEqual(retorno, ({'campo': 'ficticio'}, 'consultado'))
        args, opcoes = executar.call_args
        comando = args[0]
        self.assertEqual(Path(comando[0]).parts[-4:], ('System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'))
        self.assertIn('-NoProfile', comando)
        self.assertIn('-NonInteractive', comando)
        self.assertNotIn('-ExecutionPolicy', comando)
        self.assertEqual(base64.b64decode(comando[-1]).decode('utf-16le'), diag._DNS_PS)
        self.assertFalse(opcoes['shell'])
        self.assertEqual(opcoes['timeout'], 2)
        self.assertEqual(opcoes['stderr'], subprocess.DEVNULL)
        self.assertNotIn('SECRET_API_KEY', opcoes['env'])
        self.assertNotIn('HTTP_PROXY', opcoes['env'])

    def test_powershell_erros_nao_expoem_conteudo_privado(self):
        casos = [
            (SimpleNamespace(returncode=1, stdout=b'fixture-segredo'), None, 'consulta_indisponivel'),
            (SimpleNamespace(returncode=0, stdout=b'fixture-segredo'), None, 'consulta_indisponivel'),
            (SimpleNamespace(returncode=0, stdout=b'\xff'), None, 'consulta_indisponivel'),
            (SimpleNamespace(returncode=0, stdout=b'x' * (diag.MAX_SAIDA + 1)), None, 'resposta_invalida'),
            (None, subprocess.TimeoutExpired('fixture-segredo', 2), 'tempo_esgotado'),
            (None, OSError('fixture-segredo'), 'consulta_indisponivel')]
        for resultado, erro, estado in casos:
            with self.subTest(estado=estado):
                retorno, _ = self.powershell(resultado, erro)
                self.assertEqual(retorno, (None, estado))

    def test_powershell_ausente_nao_executa_outro_programa(self):
        with patch.object(diag.sys, 'platform', 'win32'), \
             patch.object(diag.Path, 'is_file', return_value=False), \
             patch.object(diag.subprocess, 'run') as executar:
            self.assertEqual(diag._powershell(diag._DNS_PS, 2), (None, 'powershell_ausente'))
        executar.assert_not_called()

    def test_linux_nao_faz_consultas_nem_escreve(self):
        with patch.object(diag.sys, 'platform', 'linux'), \
             patch.object(diag.subprocess, 'run') as executar, \
             patch.object(diag.socket, 'socket') as rede, \
             patch.object(diag, 'salvar') as salvar, contextlib.redirect_stdout(io.StringIO()) as texto:
            self.assertEqual(diag.main([]), 2)
            with self.assertRaises(RuntimeError):
                diag.monitorar()
            with self.assertRaises(RuntimeError):
                diag.coletar_amostra()
        self.assertIn('nenhuma consulta', texto.getvalue())
        executar.assert_not_called(); rede.assert_not_called(); salvar.assert_not_called()

    def test_tcp_direto_fecha_socket_sem_dns(self):
        with patch.object(diag.socket, 'socket') as abrir:
            self.assertTrue(diag._tcp('1.1.1.1', 0.6)['conectou'])
        abrir.assert_called_once_with(diag.socket.AF_INET, diag.socket.SOCK_STREAM)
        conexao = abrir.return_value.__enter__.return_value
        conexao.settimeout.assert_called_once_with(0.6)
        conexao.connect.assert_called_once_with(('1.1.1.1', 443))
        abrir.return_value.__exit__.assert_called_once()

    def test_tcp_falha_sem_mensagem_privada(self):
        with patch.object(diag.socket, 'socket', side_effect=OSError('fixture-segredo')):
            self.assertEqual(diag._tcp('1.1.1.1', 0.6), {'conectou': False, 'milissegundos': None})

    def test_coleta_somente_sondas_e_scripts_fixos(self):
        with patch.object(diag.sys, 'platform', 'win32'), \
             patch.object(diag, '_powershell', side_effect=[({}, 'consultado'),
                  ({'resolveu': True, 'IP': 'fixture-privado'}, 'consultado')]) as ps, \
             patch.object(diag, '_tcp', return_value={'conectou': True, 'milissegundos': 1}) as tcp:
            resultado = diag.coletar_amostra(restante=40)
        self.assertEqual([c.args[0] for c in ps.call_args_list], [diag._SISTEMA_PS, diag._DNS_PS])
        self.assertEqual([c.args[0] for c in tcp.call_args_list], ['1.1.1.1', '9.9.9.9'])
        self.assertEqual(resultado['sondas']['dns'], {'resolveu': True, 'estado': 'consultado'})
        self.assertNotIn('fixture-privado', json.dumps(resultado))
        self.assertTrue(all(c.args[1] <= 6 for c in ps.call_args_list))

    def test_taxas_por_interface_reinicio_contador_nao_negativa(self):
        antes, atual = amostra(), amostra()
        atual['sistema']['adaptadores'][0]['recebidos'] += 10 * 1024
        atual['sistema']['adaptadores'][0]['enviados'] = 1
        diag._taxas(antes, atual, 10)
        adaptador = atual['sistema']['adaptadores'][0]
        self.assertEqual(adaptador['recepcao_kib_s'], 1)
        self.assertNotIn('envio_kib_s', adaptador)

    def test_monitor_finitamente_amostra_sem_abrir_programas(self):
        agora = [0]
        def dormir(segundos):
            agora[0] += segundos
        with patch.object(diag.sys, 'platform', 'win32'), \
             patch.object(diag.time, 'monotonic', side_effect=lambda: agora[0]), \
             patch.object(diag.time, 'sleep', side_effect=dormir), \
             patch.object(diag, 'coletar_amostra', side_effect=lambda **_: amostra()) as coletar, \
             contextlib.redirect_stdout(io.StringIO()):
            relatorio = diag.monitorar(30)
        self.assertEqual(coletar.call_count, 3)
        self.assertEqual(relatorio['duracao_real_segundos'], 30)
        self.assertEqual([a['segundos'] for a in relatorio['amostras']], [0, 10, 20])

    def test_monitor_valida_duracao_antes_de_sondas(self):
        with patch.object(diag.sys, 'platform', 'win32'), patch.object(diag, 'coletar_amostra') as coletar:
            for invalido in (0, 29, 181, float('inf'), True, '90'):
                with self.subTest(invalido=invalido), self.assertRaises(ValueError):
                    diag.monitorar(invalido)
        coletar.assert_not_called()

    def test_resumo_nao_aponta_culpa_a_aplicativo(self):
        a = amostra()
        a['sistema']['proxy'] = {'manual': True, 'tipo': 'loopback', 'pac_configurado': False}
        resumo = diag.resumir({'amostras': [a]})
        self.assertIn('sem causa confirmada', resumo)
        self.assertIn('Proxy manual ou PAC observado', resumo)
        self.assertIn('não atribuem consumo a um aplicativo', resumo)
        self.assertNotIn('Ollama derrubou', resumo)

    def test_salva_somente_relatorios_na_pasta_propria(self):
        relatorio = {'formato': 1, 'amostras': [amostra()]}
        with tempfile.TemporaryDirectory() as temporario:
            pasta = Path(temporario) / 'diagnosticos_rede'
            arquivos = diag.salvar(relatorio, pasta)
            self.assertEqual(len(list(pasta.iterdir())), 2)
            self.assertEqual(json.loads(arquivos[0].read_text(encoding='utf-8')), relatorio)
            self.assertIn('Nenhum modelo/programa foi aberto', arquivos[1].read_text(encoding='utf-8'))

    def test_resumo_mostra_recursos_tempo_e_transicao_sem_identificadores(self):
        a, b = amostra(), amostra()
        a['segundos'], b['segundos'] = 4, 14
        a['sistema']['recursos'] = {'cpu_percentual': 10, 'ram_total_kib': 1024000, 'ram_livre_kib': 512000}
        b['sistema']['recursos'] = {'cpu_percentual': 25, 'ram_total_kib': 1024000, 'ram_livre_kib': 256000}
        b['sistema']['adaptadores'][0]['estado'] = 'Disconnected'
        b['sistema']['processos'] = [{'nome': 'tailscaled'}]
        b['sondas']['dns']['resolveu'] = False
        resumo = diag.resumir({'amostras': [a, b]})
        self.assertIn('CPU máxima 25.0%', resumo)
        self.assertIn('RAM livre mínima 250 MiB', resumo)
        self.assertIn('uso de RAM máximo 75.0%', resumo)
        self.assertIn('14s: interface 4, Up -> Disconnected', resumo)
        self.assertIn('4 | sim | não | sim', resumo)
        self.assertIn('14 | sim | não | não', resumo)
        self.assertIn('tailscaled', resumo)

    def test_consultas_indisponiveis_sao_distintas_de_listas_vazias(self):
        dados = diag._filtrar_sistema({'consultas': {'adaptadores': 'indisponivel',
            'proxy': 'consultado', 'recursos': 'mensagem-privada', 'usuario': 'mensagem-privada'},
            'processos': [{'nome': 'tailscaled', 'pid': 123}]})
        self.assertEqual(dados['consultas'], {'adaptadores': 'indisponivel', 'proxy': 'consultado'})
        self.assertNotIn('mensagem-privada', json.dumps(dados))
        self.assertEqual(dados['processos'][0]['nome'], 'tailscaled')
        a = amostra(); a['sistema'] = dados
        self.assertIn('consultas locais indisponíveis', diag.resumir({'amostras': [a]}))

    @unittest.skipUnless(sys.platform == 'win32', 'Análise sintática PowerShell somente no CI Windows.')
    def test_scripts_powershell_parseiam_sem_executar_sondas(self):
        executavel = shutil.which('powershell') or shutil.which('pwsh')
        if not executavel:
            self.skipTest('PowerShell não disponível.')
        for script in (diag._SISTEMA_PS, diag._DNS_PS):
            codigo = base64.b64encode(script.encode('utf-16le')).decode('ascii')
            validador = ("$s=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String('" + codigo + "')); "
                         "try {$null=[ScriptBlock]::Create($s); exit 0} catch {exit 1}")
            resultado = subprocess.run([executavel, '-NoLogo', '-NoProfile', '-NonInteractive',
                '-EncodedCommand', base64.b64encode(validador.encode('utf-16le')).decode('ascii')],
                shell=False, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=15, check=False)
            self.assertEqual(resultado.returncode, 0)


if __name__ == '__main__':
    unittest.main()
