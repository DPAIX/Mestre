import ctypes
from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import ajustar_autodeteccao_proxy as modulo


IDENTIDADE = "a" * 64


class AjusteProxyTests(unittest.TestCase):
    def setUp(self):
        self.temporario = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporario.cleanup)
        self.backup = Path(self.temporario.name) / modulo.NOME_BACKUP
        self.patches = [
            patch.object(modulo, "_windows", return_value=True),
            patch.object(modulo, "_identidade", return_value=IDENTIDADE),
            patch.object(modulo, "_trava", side_effect=lambda _: nullcontext()),
            patch.object(modulo, "_arquivo_backup", return_value=self.backup),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def criar_backup(self, identidade=IDENTIDADE, original=9):
        return modulo._criar_backup(self.backup, identidade, original)

    def test_destino_preserva_outros_bits_e_garante_modo_direto(self):
        for antes, esperado in [(9, 1), (8, 1), (0x109, 0x101), (0x108, 0x101)]:
            with self.subTest(antes=antes):
                self.assertEqual(modulo._destino(antes), esperado)

    def test_aplica_com_backup_minimo_e_workers_separados(self):
        with patch.object(modulo, "_ler_estado", side_effect=[9, 9, 1]), patch.object(
            modulo, "_executar_worker", return_value="ok"
        ) as worker:
            resultado = modulo.ajustar("desativar")
        self.assertEqual(resultado["estado"], "aplicado")
        self.assertEqual(resultado["atualizacao"], "solicitada")
        dados = json.loads(self.backup.read_text())
        self.assertEqual(set(dados), {"formato", "identidade", "flags_original", "flags_esperado"})
        self.assertEqual((dados["flags_original"], dados["flags_esperado"]), (9, 1))
        self.assertEqual(worker.call_args_list[0].args, (["--worker-set", "9", "1", IDENTIDADE], 8))
        self.assertEqual(worker.call_args_list[1].args, (["--worker-notify"], 3))

    def test_reaplicar_nao_sobrescreve_backup_nem_chama_api(self):
        self.criar_backup()
        original = self.backup.read_bytes()
        with patch.object(modulo, "_ler_estado", return_value=1), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("desativar")["estado"], "ja_aplicado")
        worker.assert_not_called()
        self.assertEqual(self.backup.read_bytes(), original)
        with self.assertRaises(FileExistsError):
            self.criar_backup()

    def test_restauracao_usa_flags_originais_sem_apagar_backup(self):
        self.criar_backup()
        original = self.backup.read_bytes()
        with patch.object(modulo, "_ler_estado", side_effect=[1, 1, 9]), patch.object(
            modulo, "_executar_worker", return_value="ok"
        ) as worker:
            self.assertEqual(modulo.ajustar("restaurar")["estado"], "restaurado")
        self.assertEqual(worker.call_args_list[0].args, (["--worker-set", "1", "9", IDENTIDADE], 8))
        self.assertEqual(self.backup.read_bytes(), original)

    def test_restauracao_recusa_estado_modificado_e_backup_ausente(self):
        with patch.object(modulo, "_ler_estado", return_value=1), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("restaurar")["estado"], "backup_ausente")
        self.criar_backup()
        with patch.object(modulo, "_ler_estado", return_value=0x101), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("restaurar")["estado"], "configuracao_alterada")
        worker.assert_not_called()

    def test_mudanca_antes_do_worker_aborta_sem_escrita(self):
        with patch.object(modulo, "_ler_estado", side_effect=[9, 0x109]), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("desativar")["estado"], "configuracao_alterada")
        worker.assert_not_called()
        self.assertTrue(self.backup.is_file())

    def test_timeout_sem_mudanca_nao_repete_nem_notifica(self):
        with patch.object(modulo, "_ler_estado", side_effect=[9, 9, 9]), patch.object(
            modulo, "_executar_worker", return_value="tempo_esgotado"
        ) as worker:
            resultado = modulo.ajustar("desativar")
        self.assertEqual(resultado, {"estado": "inalterado", "tentativa": "tempo_esgotado"})
        self.assertEqual(worker.call_count, 1)

    def test_timeout_depois_de_aplicar_ainda_confere_e_notifica(self):
        with patch.object(modulo, "_ler_estado", side_effect=[9, 9, 1]), patch.object(
            modulo, "_executar_worker", side_effect=["tempo_esgotado", "tempo_esgotado"]
        ) as worker:
            resultado = modulo.ajustar("desativar")
        self.assertEqual(resultado["estado"], "aplicado")
        self.assertEqual(resultado["atualizacao"], "pendente")
        self.assertEqual(worker.call_count, 2)

    def test_estado_imprevisto_apos_api_fica_incerto_sem_notify(self):
        for leitura in [0x101, OSError("segredo-simulado")]:
            with self.subTest(leitura=type(leitura).__name__):
                if self.backup.exists():
                    self.backup.unlink()
                with patch.object(modulo, "_ler_estado", side_effect=[9, 9, leitura]), patch.object(
                    modulo, "_executar_worker", return_value="ok"
                ) as worker:
                    self.assertEqual(modulo.ajustar("desativar")["estado"], "incerto")
                self.assertEqual(worker.call_count, 1)

    def test_politica_da_maquina_impede_backup_e_worker(self):
        with patch.object(modulo, "_ler_estado", side_effect=modulo.FalhaProxy("proxy_da_maquina")), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("desativar")["estado"], "proxy_da_maquina")
        self.assertFalse(self.backup.exists())
        worker.assert_not_called()

    def test_backup_outro_usuario_ou_flags_incompativeis_recusado(self):
        self.criar_backup(identidade="b" * 64)
        with patch.object(modulo, "_ler_estado", return_value=1), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("restaurar")["estado"], "backup_incompativel")
        worker.assert_not_called()
        for invalido in [True, -1, 4, 0x100000000]:
            with self.subTest(flags=invalido), self.assertRaises(modulo.FalhaProxy):
                modulo._validar_backup({"formato": 1, "identidade": IDENTIDADE,
                                       "flags_original": invalido, "flags_esperado": 1}, IDENTIDADE)

    def test_links_e_backup_corrompido_falham_sem_api(self):
        alvo = Path(self.temporario.name) / "outro"
        alvo.write_text("privado-simulado")
        try:
            self.backup.symlink_to(alvo)
        except OSError:
            return
        with self.assertRaises(modulo.FalhaProxy):
            modulo._ler_backup(self.backup, IDENTIDADE)
        self.backup.unlink()
        self.backup.write_text("JSON invalido: privado-simulado")
        with patch.object(modulo, "_ler_estado", return_value=1), patch.object(modulo, "_executar_worker") as worker:
            self.assertEqual(modulo.ajustar("restaurar")["estado"], "falha_local")
        worker.assert_not_called()

    def test_worker_isolado_sem_segredos_shell_ou_saida_crua(self):
        python = Path(self.temporario.name) / "python.exe"
        with patch.object(modulo, "_python_worker", return_value=python), patch.dict(
            os.environ, {"TELEGRAM_TOKEN": "SEGREDO_TESTE", "NODE_OPTIONS": "nao-herdar",
                         "PYTHONPATH": "nao-herdar", "SYSTEMROOT": "Windows"}, clear=True
        ), patch.object(modulo.subprocess, "run", return_value=types.SimpleNamespace(returncode=0)) as executar:
            self.assertEqual(modulo._executar_worker(["--worker-notify"], 3), "ok")
        args, opcoes = executar.call_args
        self.assertEqual(args[0][:4], [str(python), "-I", "-S", "-E"])
        self.assertIs(opcoes["shell"], False)
        self.assertEqual(opcoes["timeout"], 3)
        self.assertEqual(opcoes["env"], {"SYSTEMROOT": "Windows"})
        self.assertEqual(opcoes["stdout"], subprocess.DEVNULL)
        self.assertEqual(opcoes["stderr"], subprocess.DEVNULL)
        with patch.object(modulo, "_python_worker", return_value=python), patch.object(
            modulo.subprocess, "run", side_effect=subprocess.TimeoutExpired("somente-filho", 8)
        ) as executar:
            self.assertEqual(modulo._executar_worker(["--worker-notify"], 8), "tempo_esgotado")
        self.assertEqual(executar.call_count, 1)

    def test_api_recebe_somente_opcao_flags_e_trabalhador_revalida(self):
        setter = Mock(return_value=1)
        dll = types.SimpleNamespace(InternetSetOptionW=setter)
        with patch.object(modulo, "_ler_estado", return_value=9), patch.object(modulo, "_dll", return_value=dll):
            self.assertEqual(modulo._definir_flags(9, 1, IDENTIDADE), 0)
        _, opcao_api, ponteiro, tamanho = setter.call_args.args
        Opcao, Lista = modulo._estruturas()
        lista = ctypes.cast(ponteiro, ctypes.POINTER(Lista)).contents
        self.assertEqual(opcao_api, 75)
        self.assertEqual(tamanho, ctypes.sizeof(Lista))
        self.assertEqual(lista.quantidade, 1)
        self.assertIsNone(lista.conexao)
        self.assertEqual(lista.opcoes[0].opcao, 1)
        self.assertEqual(lista.opcoes[0].valor.numero, 1)
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual((ctypes.sizeof(Opcao), ctypes.sizeof(Lista)), (16, 32))
        setter.reset_mock()
        with patch.object(modulo, "_ler_estado", return_value=1), patch.object(modulo, "_dll", return_value=dll):
            self.assertEqual(modulo._definir_flags(9, 1, IDENTIDADE), 21)
        setter.assert_not_called()

    def test_cli_nao_expoe_excecoes_e_recusa_flags_worker_arbitrarias(self):
        saida = io.StringIO()
        with patch.object(modulo, "_identidade", side_effect=ValueError("TOKEN_PRIVADO_SIMULADO")), patch("sys.stdout", saida):
            self.assertEqual(modulo.main(["--desativar"]), 1)
        self.assertNotIn("TOKEN_PRIVADO_SIMULADO", saida.getvalue())
        self.assertIn("RESULTADO_PROXY=falha_local", saida.getvalue())
        with patch.object(modulo, "_definir_flags") as alterar:
            self.assertEqual(modulo.main(["--worker-set", "9", "2", IDENTIDADE]), 23)
            self.assertEqual(modulo.main(["--worker-set", "9999999999", "1", IDENTIDADE]), 23)
        alterar.assert_not_called()


class LeituraRegistroTests(unittest.TestCase):
    def test_leitura_valida_tipo_flags_politica_e_proxy_manual(self):
        valores = {"ProxySettingsPerUser": (1, 4), "ProxyEnable": (0, 4),
                   "DefaultConnectionSettings": (b"\0" * 8 + struct.pack("<I", 9), 3)}
        modulo_reg = types.SimpleNamespace(HKEY_LOCAL_MACHINE=1, HKEY_CURRENT_USER=2,
                                          KEY_READ=1, KEY_WOW64_64KEY=2,
                                          REG_DWORD=4, REG_BINARY=3)
        modulo_reg.OpenKey = lambda *args: nullcontext("chave-simulada")
        modulo_reg.QueryValueEx = lambda chave, nome: valores[nome]
        with patch.dict(sys.modules, {"winreg": modulo_reg}):
            self.assertEqual(modulo._ler_estado(), 9)
            valores["ProxySettingsPerUser"] = (0, 4)
            with self.assertRaisesRegex(modulo.FalhaProxy, "proxy_da_maquina"):
                modulo._ler_estado()
            valores["ProxySettingsPerUser"] = (1, 4)
            valores["ProxyEnable"] = (1, 4)
            with self.assertRaisesRegex(modulo.FalhaProxy, "configuracao_alterada"):
                modulo._ler_estado()
            valores["ProxyEnable"] = (0, 4)
            valores["DefaultConnectionSettings"] = (b"curto", 3)
            with self.assertRaisesRegex(modulo.FalhaProxy, "configuracao_incompativel"):
                modulo._ler_estado()


if __name__ == "__main__":
    unittest.main()
