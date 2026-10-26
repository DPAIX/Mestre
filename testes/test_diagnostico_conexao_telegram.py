"""Sonda Telegram com processos e respostas simulados; sem API ou credenciais."""
from contextlib import nullcontext, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import diagnosticar_conexao_telegram as app


LINHA4 = ('TELEGRAM_4=TIMEOUT_12s;ETAPA=DNS;MS=12001;DNS_OS=PENDENTE;'
          'DNS_PUBLICO=149.154.167.220;DNS=-;TCP=-;TLS=-')
LINHA6 = ('TELEGRAM_6=HTTP_302;ETAPA=HTTP;MS=260;DNS_OS=2001:67c:4e8:f004::9;'
          'DNS_PUBLICO=2001:67c:4e8:f004::9;DNS=60;TCP=130;TLS=260')
SAIDA = LINHA4 + '\n' + LINHA6 + '\n'


class DiagnosticoConexaoTelegram(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.node = Path(self.tmp.name) / 'node.exe'
        self.node.write_text('fixture')
        for p in (
            patch.object(app, '_WINDOWS', True),
            patch.object(app, '_reserva', side_effect=lambda: nullcontext()),
            patch.object(app.shutil, 'which', return_value=str(self.node)),
            patch.dict(os.environ, {'PATH': 'fixturepath', 'SYSTEMROOT': 'fixture-system',
                'TEMP': self.tmp.name, 'TMP': self.tmp.name,
                'TELEGRAM_TOKEN': 'SEGREDO_FIXTURE', 'NODE_OPTIONS': '-r invasor',
                'NODE_PATH': 'fixture-modules', 'HTTP_PROXY': 'fixture-proxy',
                'MEUCONTROLEPC_ENV': 'fixture-env'}, clear=True)):
            p.start()
            self.addCleanup(p.stop)

    def executar(self, resposta=None, erro=None):
        resposta = resposta or SimpleNamespace(returncode=0, stdout=SAIDA)
        version = SimpleNamespace(returncode=0, stdout='v24.12.0\n')
        chamadas = []
        def run(args, **kwargs):
            chamadas.append((args, kwargs))
            if len(chamadas) == 1:
                return version
            arquivo = Path(args[1])
            self.assertTrue(arquivo.is_file())
            self.assertEqual(arquivo.read_text(encoding='utf-8'), app.SCRIPT_JS)
            if erro:
                raise erro
            return resposta
        with patch.object(app.subprocess, 'run', side_effect=run) as processo:
            resultado = app.diagnosticar()
        return resultado, chamadas, processo

    def test_runner_escreve_somente_sonda_temporaria_e_remove_ao_terminar(self):
        resultado, chamadas, processo = self.executar()
        self.assertEqual(resultado, {'estado': 'concluido', 'linhas': [LINHA4, LINHA6]})
        self.assertEqual(processo.call_count, 2)
        self.assertEqual(chamadas[0][0], [str(self.node.resolve()), '--version'])
        self.assertEqual(chamadas[1][0][0], str(self.node.resolve()))
        self.assertFalse(Path(chamadas[1][0][1]).exists())
        self.assertEqual(chamadas[1][1]['timeout'], 16)
        self.assertEqual(chamadas[0][1]['timeout'], 5)
        for _, kwargs in chamadas:
            self.assertFalse(kwargs['shell'])
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(kwargs['stderr'], subprocess.DEVNULL)
            self.assertEqual(kwargs['env'], {'PATH': 'fixturepath', 'SYSTEMROOT': 'fixture-system',
                'TEMP': self.tmp.name, 'TMP': self.tmp.name})

    def test_codigo_fixo_nao_carrega_bot_ou_credenciais(self):
        self.assertIn('https://api.telegram.org/', app.SCRIPT_JS)
        for proibido in ('getMe', 'getUpdates', 'getWebhookInfo', 'sendMessage',
                         'TELEGRAM_TOKEN', '.env', 'readFile', 'child_process'):
            self.assertNotIn(proibido, app.SCRIPT_JS)

    def test_timeout_externo_descarta_saida_parcial_privada(self):
        erro = subprocess.TimeoutExpired('SEGREDO_FIXTURE', 16, output='SEGREDO_FIXTURE')
        with self.assertRaises(app.FalhaDiagnostico) as capturado:
            self.executar(erro=erro)
        self.assertEqual(str(capturado.exception), 'DIAGNOSTICO=TEMPO_TOTAL_ESGOTADO_16S')

    def test_falha_do_filho_nao_imprime_saida(self):
        for resposta, erro in ((SimpleNamespace(returncode=1, stdout='SEGREDO_FIXTURE'), None),
                (None, OSError('SEGREDO_FIXTURE')),
                (None, UnicodeError('SEGREDO_FIXTURE'))):
            with self.subTest(erro=type(erro).__name__), self.assertRaises(app.FalhaDiagnostico) as capturado:
                self.executar(resposta, erro)
            self.assertNotIn('SEGREDO_FIXTURE', str(capturado.exception))

    def test_node_fallback_usa_somente_caminho_fixo_confirmado(self):
        with patch.object(app.shutil, 'which', return_value=None), \
                patch.object(app, 'NODE_FALLBACK', self.node), \
                patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stdout='v22.0.0')):
            self.assertEqual(app._node(app._ambiente()), self.node.resolve())

    def test_node_ausente_ou_relativo_nao_executa(self):
        for caminho in ('node.exe', str(self.node.parent / 'outro.exe'), str(self.node.parent / 'ausente' / 'node.exe')):
            with self.subTest(caminho=caminho), \
                    patch.object(app.shutil, 'which', return_value=caminho), \
                    patch.object(app.subprocess, 'run') as run, \
                    self.assertRaises(app.FalhaDiagnostico):
                app._node(app._ambiente())
            run.assert_not_called()

    def test_node_antigo_saida_extra_e_erro_sao_recusados(self):
        for retorno, texto in ((0, 'v20.0.0'), (0, 'v24.0.0\nSEGREDO_FIXTURE'),
                               (1, 'v24.0.0'), (0, 'SEGREDO_FIXTURE')):
            with self.subTest(texto=texto), \
                    patch.object(app.subprocess, 'run', return_value=SimpleNamespace(returncode=retorno, stdout=texto)), \
                    self.assertRaises(app.FalhaDiagnostico) as capturado:
                app._node(app._ambiente())
            self.assertEqual(str(capturado.exception), 'DIAGNOSTICO=NODE_22_OU_SUPERIOR_NECESSARIO')

    def test_timeout_versao_e_erro_nao_vazam_argumentos(self):
        for erro in (subprocess.TimeoutExpired('SEGREDO_FIXTURE', 5), OSError('SEGREDO_FIXTURE')):
            with self.subTest(erro=type(erro).__name__), \
                    patch.object(app.subprocess, 'run', side_effect=erro), \
                    self.assertRaises(app.FalhaDiagnostico) as capturado:
                app._node(app._ambiente())
            self.assertEqual(str(capturado.exception), 'DIAGNOSTICO=VERSAO_NODE_INDISPONIVEL')

    def test_linux_nao_cria_pasta_ou_executa(self):
        with patch.object(app, '_WINDOWS', False), \
                patch.object(app.tempfile, 'TemporaryDirectory') as pasta, \
                patch.object(app.subprocess, 'run') as processo, \
                self.assertRaises(app.FalhaDiagnostico):
            app.diagnosticar()
        pasta.assert_not_called()
        processo.assert_not_called()

    def test_somente_duas_linhas_e_esquema_fechado(self):
        ruins = ('SEGREDO_FIXTURE', SAIDA + 'EXTRA=SEGREDO_FIXTURE\n',
            SAIDA.replace('ETAPA=DNS', 'ETAPA=SEGREDO_FIXTURE'),
            SAIDA.replace('TELEGRAM_4=', 'TELEGRAM_6=', 1),
            SAIDA.replace('MS=12001', 'MS=-1'),
            SAIDA.replace('DNS=-', 'DNS=nan'),
            SAIDA.replace('DNS_OS=PENDENTE', 'DNS_OS=https://privado.invalid/segredo'),
            SAIDA.replace('DNS_OS=PENDENTE', 'DNS_OS=127.0.0.1'),
            SAIDA.replace('DNS_OS=PENDENTE', 'DNS_OS=192.168.1.1'),
            SAIDA.replace('DNS_OS=2001:67c:4e8:f004::9', 'DNS_OS=fd00::1'),
            SAIDA.replace('TIMEOUT_12s', 'ERROR_SEGREDO_FIXTURE'),
            SAIDA.replace('MS=12001', 'MS=12\x1b31'),
            LINHA4 + 'x' * app.MAX_LINHA + '\n' + LINHA6)
        for saida in ruins:
            with self.subTest(saida=saida[:80]), self.assertRaises(app.FalhaDiagnostico) as capturado:
                app._linhas_publicas(saida)
            self.assertNotIn('SEGREDO_FIXTURE', str(capturado.exception))

    def test_erros_reais_tls_e_dns_continuam_visiveis(self):
        for erro in ('CERT_HAS_EXPIRED', 'ENOTFOUND', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE', 'ETIMEDOUT'):
            saida = SAIDA.replace('TIMEOUT_12s', erro)
            self.assertEqual(app._linhas_publicas(saida)[0].split(';')[0], 'TELEGRAM_4=' + erro)
        self.assertEqual(app._linhas_publicas(SAIDA.replace('DNS_OS=PENDENTE', 'DNS_OS=LOCAL_OU_PRIVADO'))[0],
            LINHA4.replace('DNS_OS=PENDENTE', 'DNS_OS=LOCAL_OU_PRIVADO'))

    def test_main_nao_printa_stdout_privado_em_falha(self):
        with patch.object(app, 'diagnosticar', side_effect=OSError('SEGREDO_FIXTURE')), \
                redirect_stdout(StringIO()) as saida:
            self.assertEqual(app.main([]), 1)
        self.assertNotIn('SEGREDO_FIXTURE', saida.getvalue())

    def test_main_sucesso_exibe_somente_duas_linhas(self):
        with patch.object(app, 'diagnosticar', return_value={'estado':'concluido','linhas':[LINHA4,LINHA6]}), \
                redirect_stdout(StringIO()) as saida:
            self.assertEqual(app.main([]), 0)
        self.assertEqual(saida.getvalue().count('TELEGRAM_'), 2)
        self.assertEqual(saida.getvalue(), SAIDA)

    def test_salvar_grava_somente_relatorio_validado_no_pacote(self):
        with patch.object(app, '__file__', str(Path(self.tmp.name) / 'diagnosticar_conexao_telegram.py')):
            app._salvar_resultado([LINHA4, LINHA6])
        alvo = Path(self.tmp.name) / 'RESULTADO_TELEGRAM.txt'
        self.assertEqual(alvo.read_bytes(), SAIDA.encode('utf-8'))
        self.assertFalse(list(Path(self.tmp.name).glob('.resultado-telegram-*.tmp')))

    def test_salvar_recusa_destino_diretorio(self):
        alvo = Path(self.tmp.name) / 'RESULTADO_TELEGRAM.txt'
        alvo.mkdir()
        with patch.object(app, '__file__', str(alvo.parent / 'diagnosticar_conexao_telegram.py')), \
                self.assertRaises(app.FalhaDiagnostico):
            app._salvar_resultado([LINHA4, LINHA6])
        self.assertFalse(list(alvo.parent.glob('.resultado-telegram-*.tmp')))

    def test_salvar_recusa_symlink_preservando_destino(self):
        fora = Path(self.tmp.name) / 'fora.txt'
        fora.write_text('fixture preservada')
        alvo = Path(self.tmp.name) / 'RESULTADO_TELEGRAM.txt'
        try:
            alvo.symlink_to(fora)
        except (OSError, NotImplementedError):
            self.skipTest('Symlink indisponível.')
        with patch.object(app, '__file__', str(alvo.parent / 'diagnosticar_conexao_telegram.py')), \
                self.assertRaises(app.FalhaDiagnostico):
            app._salvar_resultado([LINHA4, LINHA6])
        self.assertEqual(fora.read_text(), 'fixture preservada')

    def test_main_salvar_abre_somente_relatorio_gerado_e_recusa_args_extras(self):
        with patch.object(app, 'diagnosticar', return_value={'estado':'concluido','linhas':[LINHA4,LINHA6]}), \
                patch.object(app, '_salvar_resultado') as salvar, redirect_stdout(StringIO()) as saida:
            self.assertEqual(app.main(['--salvar']), 0)
            salvar.assert_called_once_with([LINHA4, LINHA6])
        self.assertEqual(saida.getvalue(), SAIDA)
        with patch.object(app, 'diagnosticar') as diagnosticar, redirect_stdout(StringIO()) as saida:
            self.assertEqual(app.main(['SEGREDO_FIXTURE']), 1)
        diagnosticar.assert_not_called()
        self.assertEqual(saida.getvalue(), 'DIAGNOSTICO=OPCAO_INVALIDA\n')


class ReservaWindowsDiagnostico(unittest.TestCase):
    def kernel(self, espera=0):
        kernel = Mock()
        kernel.CreateMutexW.return_value = 123
        kernel.WaitForSingleObject.return_value = espera
        return kernel

    def test_mutex_ocupado_recusa_entrada_e_fecha_handle(self):
        kernel = self.kernel(258)
        with patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True), \
                self.assertRaises(app.FalhaDiagnostico) as capturado:
            with app._reserva():
                self.fail('Não pode entrar com mutex ocupado.')
        self.assertEqual(str(capturado.exception), 'DIAGNOSTICO=OUTRA_CONSULTA_EM_EXECUCAO')
        kernel.ReleaseMutex.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)

    def test_excecao_libera_mutex_sem_encerrar_programas(self):
        kernel = self.kernel()
        with patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True), \
                self.assertRaisesRegex(ValueError, 'fixture'):
            with app._reserva():
                raise ValueError('fixture')
        kernel.ReleaseMutex.assert_called_once_with(123)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_reserva_falha_sem_handle_nao_tenta_fechar(self):
        kernel = self.kernel()
        kernel.CreateMutexW.return_value = 0
        with patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True), \
                self.assertRaises(app.FalhaDiagnostico):
            with app._reserva():
                self.fail('Não há reserva.')
        kernel.CloseHandle.assert_not_called()


class JavaScriptDiagnosticoPublico(unittest.TestCase):
    def test_sintaxe_do_script_fixo_sem_rede(self):
        node = shutil.which('node') or shutil.which('node.exe')
        if not node:
            self.skipTest('Node não disponível para validar sintaxe.')
        with tempfile.TemporaryDirectory() as pasta:
            arquivo = Path(pasta) / 'sonda.cjs'
            arquivo.write_text(app.SCRIPT_JS, encoding='utf-8')
            resultado = subprocess.run([node, '--check', str(arquivo)], capture_output=True,
                text=True, encoding='utf-8', timeout=5, env=app._ambiente())
        self.assertEqual(resultado.returncode, 0, resultado.stderr)


if __name__ == '__main__':
    unittest.main()
