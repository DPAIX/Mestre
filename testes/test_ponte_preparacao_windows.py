"""Aberturas oficiais simuladas: nenhum navegador, macro ou serviço real."""
import importlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ponte_preparacao_windows as ponte


class PontePreparacaoWindows(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name).resolve()
        self.win = self.raiz / 'Windows'; (self.win / 'System32').mkdir(parents=True)
        self.programa = self.win / 'System32' / 'rundll32.exe'; self.programa.write_bytes(b'fixture')
        ambiente = {'SYSTEMROOT': str(self.win), 'PATH': 'caminho-ficticio',
            'TELEGRAM_TOKEN': 'FIXTURE_SEGREDO_BOT', 'GEMINI_API_KEY': 'FIXTURE_SEGREDO_API',
            'NINE_ROUTER_API_KEY': 'FIXTURE_SEGREDO_GATEWAY', 'HTTP_PROXY': 'FIXTURE_PROXY',
            'PYTHONPATH': 'FIXTURE_INJECAO', 'NODE_OPTIONS': 'FIXTURE_INJECAO'}
        for alvo, nome, valor in ((ponte, '_ABERTAS', set()), (ponte.sys, 'platform', 'win32')):
            p = patch.object(alvo, nome, valor); p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, ambiente, clear=True); p.start(); self.addCleanup(p.stop)

    def test_importacao_e_plano_nao_leem_arquivos_ou_abrem_processos(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('Não ler configuração.')), \
                patch.object(ponte.subprocess, 'Popen') as abrir, patch.object(ponte.shutil, 'which') as which:
            importlib.reload(ponte)
            plano = ponte.plano_ajudas(['9router_contas', 'gemini_chave'])
        abrir.assert_not_called(); which.assert_not_called()
        self.assertEqual(len(plano), 2)
        self.assertFalse(plano[0]['conexao_testada'])

    def test_autorizacao_estrita_e_alvos_fechados_antes_de_abrir(self):
        with patch.object(ponte, '_abridor_windows') as programa, patch.object(ponte.subprocess, 'Popen') as abrir:
            for confirmado in (False, None, 1, 'sim'):
                with self.subTest(confirmado=confirmado), self.assertRaises(PermissionError):
                    ponte.abrir_ajudas(['gemini_chave'], confirmado=confirmado)
            for alvos in ('gemini_chave', ['https://invasor.example'], ['9router_contas;calc'], [None]):
                with self.subTest(alvos=alvos), self.assertRaises(ValueError):
                    ponte.abrir_ajudas(alvos, confirmado=True)
        programa.assert_not_called(); abrir.assert_not_called()

    def test_abertura_usa_urls_fixas_sem_shell_chaves_proxy_ou_codigo(self):
        with patch.object(ponte.subprocess, 'Popen') as abrir:
            resultado = ponte.abrir_ajudas(['9router_contas', 'gemini_chave'], confirmado=True)
        self.assertEqual(abrir.call_count, 2)
        self.assertEqual(abrir.call_args_list[0].args[0], [str(self.programa), 'url.dll,FileProtocolHandler',
            'http://127.0.0.1:20128/dashboard/providers'])
        for chamada in abrir.call_args_list:
            self.assertIs(chamada.kwargs['shell'], False)
            self.assertNotIn('FIXTURE_SEGREDO', repr(chamada)); self.assertNotIn('FIXTURE_PROXY', repr(chamada))
            self.assertNotIn('FIXTURE_INJECAO', repr(chamada))
        self.assertEqual(resultado['aberturas_solicitadas'], 2)
        self.assertTrue(all(r['acao_na_conta_pendente'] for r in resultado['itens']))
        self.assertTrue(all(not r['conexao_testada'] for r in resultado['itens']))

    def test_repeticoes_deduplicam_e_reabertura_e_explicita(self):
        with patch.object(ponte.subprocess, 'Popen') as abrir:
            primeiro = ponte.abrir_ajudas(['gemini_chave', 'gemini_chave'], confirmado=True)
            segundo = ponte.abrir_ajudas(['gemini_chave'], confirmado=True)
            terceiro = ponte.abrir_ajudas(['gemini_chave'], confirmado=True, reabrir=True)
        self.assertEqual(abrir.call_count, 2)
        self.assertEqual(primeiro['aberturas_solicitadas'], 1)
        self.assertEqual(segundo['itens'][0]['estado'], 'ja_solicitada')
        self.assertEqual(terceiro['aberturas_solicitadas'], 1)

    def test_erro_de_abertura_nao_e_sucesso_e_nao_expoe_excecao(self):
        with patch.object(ponte.subprocess, 'Popen', side_effect=OSError('FIXTURE_SEGREDO')) as abrir:
            resultado = ponte.abrir_ajudas(['telegram_token'], confirmado=True)
        abrir.assert_called_once(); self.assertEqual(resultado['aberturas_solicitadas'], 0)
        self.assertEqual(resultado['itens'][0]['estado'], 'abertura_pendente')
        self.assertNotIn('FIXTURE_SEGREDO', repr(resultado))

    def test_robotask_apenas_metadados_sem_ler_tarefas_ou_executar_macros(self):
        aplicativo = self.raiz / 'RoboTask.exe'; aplicativo.write_bytes(b'fixture')
        with patch.object(ponte.shutil, 'which', return_value=str(aplicativo)), \
                patch.object(Path, 'read_bytes', side_effect=AssertionError('Não ler tarefas.')), \
                patch.object(Path, 'read_text', side_effect=AssertionError('Não ler tarefas.')), \
                patch.object(ponte.subprocess, 'Popen') as abrir:
            resultado = ponte.detectar_robotask()
        self.assertTrue(resultado['executavel_localizado']); self.assertFalse(resultado['macros_auditadas'])
        self.assertNotIn(str(aplicativo), repr(resultado)); abrir.assert_not_called()

    def test_fora_windows_nao_abre_telas(self):
        with patch.object(ponte.sys, 'platform', 'linux'), patch.object(ponte.subprocess, 'Popen') as abrir:
            with self.assertRaises(RuntimeError): ponte.abrir_ajudas(['gemini_chave'], confirmado=True)
        abrir.assert_not_called()

    def test_abridor_redirecionado_e_recusado(self):
        with patch.object(ponte, '_regular_sem_redirecionamento', return_value=False), \
                patch.object(ponte.subprocess, 'Popen') as abrir:
            with self.assertRaises(RuntimeError): ponte.abrir_ajudas(['gemini_chave'], confirmado=True)
        abrir.assert_not_called()

    def test_lista_vazia_nao_requer_abridor_e_nao_inicia_nada(self):
        with patch.object(ponte, '_abridor_windows') as programa, patch.object(ponte.subprocess, 'Popen') as abrir:
            resultado = ponte.abrir_ajudas([], confirmado=True)
        programa.assert_not_called(); abrir.assert_not_called()
        self.assertEqual(resultado['aberturas_solicitadas'], 0)


if __name__ == '__main__': unittest.main()
