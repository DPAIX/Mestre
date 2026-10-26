from contextlib import nullcontext
import io
import os
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

import diagnosticar_ncsi as modulo


class SondaNcsiTests(unittest.TestCase):
    def resposta(self, conteudo, status=200, retorno=0):
        def executar(comando, **opcoes):
            self.comando = comando
            self.opcoes = opcoes
            self.temporario = Path(comando[comando.index("--output") + 1])
            self.temporario.write_bytes(conteudo)
            return types.SimpleNamespace(stdout=modulo.MARCADOR + str(status).zfill(3).encode(),
                                         returncode=retorno)
        return executar

    def test_requisicao_publica_fixa_sem_proxy_credenciais_ou_redirect(self):
        with patch.object(modulo.subprocess, "run", side_effect=self.resposta(modulo.CONTEUDO)), patch.dict(
            os.environ, {"SYSTEMROOT": "Windows", "LOCALAPPDATA": "perfil",
                         "HTTPS_PROXY": "segredo", "TELEGRAM_TOKEN": "segredo",
                         "CURL_HOME": "config-nao-carregar"}, clear=True
        ):
            sonda = modulo._sondar(4, Path("curl.exe"))
        self.assertEqual(sonda, {"estado": "consultado", "http": 200,
                                "conteudo_esperado": True, "codigo_curl": 0})
        self.assertEqual(self.comando[1:5], ["-q", "-4", "--noproxy", "*"])
        self.assertEqual(self.comando[-1], modulo.DESTINOS[4])
        self.assertNotIn("--location", self.comando)
        self.assertEqual(self.opcoes["timeout"], 7)
        self.assertIs(self.opcoes["shell"], False)
        self.assertEqual(self.opcoes["stderr"], subprocess.DEVNULL)
        self.assertEqual(self.opcoes["env"], {"SYSTEMROOT": "Windows", "LOCALAPPDATA": "perfil"})
        self.assertFalse(self.temporario.exists())

    def test_body_privado_nao_exibido_e_corpo_exato_necessario(self):
        for corpo, status, retorno in [(b"TOKEN_PRIVADO_SIMULADO", 200, 0),
            (modulo.CONTEUDO + b"\n", 200, 0), (modulo.CONTEUDO, 302, 0),
            (modulo.CONTEUDO, 200, 63), (b"x" * 5000, 200, 0)]:
            with self.subTest(status=status, retorno=retorno), patch.object(
                modulo.subprocess, "run", side_effect=self.resposta(corpo, status, retorno)
            ):
                resultado = modulo._sondar(6, Path("curl.exe"))
            self.assertFalse(resultado["conteudo_esperado"])
            self.assertNotIn("TOKEN_PRIVADO", str(resultado))
        self.assertEqual(self.comando[-1], modulo.DESTINOS[6])

    def test_timeout_e_falha_do_proprio_filho_sao_fixos(self):
        for erro, estado in [(subprocess.TimeoutExpired("privado", 7), "tempo_esgotado"),
                             (OSError("privado"), "indisponivel")]:
            with self.subTest(estado=estado), patch.object(modulo.subprocess, "run", side_effect=erro) as executar:
                self.assertEqual(modulo._sondar(4, Path("curl.exe")), {"estado": estado})
            self.assertEqual(executar.call_count, 1)

    def test_saida_curl_nao_prevista_nao_vaza(self):
        for bruto, codigo in [(b"TOKEN_SIMULADO", 0),
            (modulo.MARCADOR + b"999", 0), (modulo.MARCADOR + b"200", -1),
            (modulo.MARCADOR + b"200TOKEN_SIMULADO", 0)]:
            with self.subTest(codigo=codigo), patch.object(modulo.subprocess, "run",
                return_value=types.SimpleNamespace(stdout=bruto, returncode=codigo)):
                self.assertEqual(modulo._sondar(4, Path("curl.exe")), {"estado": "resposta_invalida"})

    def test_registro_diferencia_ausente_tipo_e_destino_personalizado(self):
        fake = types.SimpleNamespace(REG_DWORD=4, REG_SZ=1)
        valores = {"EnableActiveProbing": (1, 4), "NoActiveProbe": (0, 4)}
        with patch.dict(sys.modules, {"winreg": fake}), patch.object(
            modulo, "_ler_valor", side_effect=lambda chave, nome: valores.get(nome)
        ):
            resultado = modulo._configuracao()
            self.assertEqual(resultado, {"sondas_ativas": "True", "politica_sem_sondas": "False",
                                        "destino_personalizado": "False"})
            valores["ActiveWebProbeHost"] = ("intranet-privada.invalid", 1)
            valores["EnableActiveProbing"] = ("1", 1)
            valores.pop("NoActiveProbe")
            resultado = modulo._configuracao()
            self.assertEqual(resultado["destino_personalizado"], "True")
            self.assertEqual(resultado["sondas_ativas"], "tipo_invalido")
            self.assertEqual(resultado["politica_sem_sondas"], "ausente")
            self.assertNotIn("intranet", str(resultado))

    def test_duas_sondas_usam_somente_endpoints_constantes(self):
        with patch.object(modulo, "_windows", return_value=True), patch.object(
            modulo, "_configuracao", return_value={"destino_personalizado": "True"}
        ), patch.object(modulo, "_curl_executavel", return_value=Path("curl.exe")), patch.object(
            modulo, "_sondar", side_effect=lambda familia, exe: {"estado": "consultado",
                "http": 200, "conteudo_esperado": True, "codigo_curl": 0}
        ) as sondar:
            resultado = modulo.diagnosticar()
        self.assertEqual(resultado["estado"], "concluido")
        self.assertEqual(set(resultado["sondas"]), {4, 6})
        self.assertEqual(sorted(chamada.args[0] for chamada in sondar.call_args_list), [4, 6])

    def test_fora_windows_e_cli_invalida_nao_criam_processos(self):
        with patch.object(modulo, "_windows", return_value=False), patch.object(
            modulo.subprocess, "run"
        ) as executar, patch("sys.stdout", new_callable=io.StringIO) as saida:
            self.assertEqual(modulo.main([]), 1)
            self.assertIn("NCSI_RESULTADO=execute_no_windows", saida.getvalue())
            self.assertEqual(modulo.main(["--qualquer"]), 1)
        executar.assert_not_called()

    def test_cli_emite_somente_recibos_sem_body(self):
        resultado = {"estado": "concluido", "configuracao": {"sondas_ativas": "True",
            "politica_sem_sondas": "ausente", "destino_personalizado": "False"},
            "sondas": {4: {"estado": "consultado", "http": 200, "conteudo_esperado": True,
                            "codigo_curl": 0}, 6: {"estado": "tempo_esgotado"}}}
        with patch.object(modulo, "diagnosticar", return_value=resultado), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as saida:
            self.assertEqual(modulo.main([]), 0)
        self.assertIn("NCSI_4_CONTEUDO_ESPERADO=True", saida.getvalue())
        self.assertIn("NCSI_6=tempo_esgotado", saida.getvalue())
        self.assertNotIn("http://", saida.getvalue())

    def test_cli_excecao_inesperada_nao_exibe_conteudo(self):
        with patch.object(modulo, "diagnosticar", side_effect=ValueError("TOKEN_PRIVADO_SIMULADO")), patch(
            "sys.stdout", new_callable=io.StringIO
        ) as saida:
            self.assertEqual(modulo.main([]), 1)
        self.assertEqual(saida.getvalue(), "NCSI_RESULTADO=falha_local\n")


if __name__ == "__main__":
    unittest.main()
