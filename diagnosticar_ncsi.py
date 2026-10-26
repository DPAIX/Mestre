"""Sonda publica e finita do NCSI; nao altera a configuracao do Windows.

Nao usa configuracao do assistente, token, proxy, cookies ou destinos definidos
pelo usuario. As unicas requisicoes sao aos dois endpoints publicos padrao.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import ctypes
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


CHAVE_NCSI = r"SYSTEM\CurrentControlSet\Services\NlaSvc\Parameters\Internet"
CHAVE_POLITICA = r"SOFTWARE\Policies\Microsoft\Windows\NetworkConnectivityStatusIndicator"
PADROES = {
    "ActiveWebProbeHost": "www.msftconnecttest.com",
    "ActiveWebProbePath": "connecttest.txt",
    "ActiveWebProbeContent": "Microsoft Connect Test",
    "ActiveWebProbeHostV6": "ipv6.msftconnecttest.com",
    "ActiveWebProbePathV6": "connecttest.txt",
    "ActiveWebProbeContentV6": "Microsoft Connect Test",
}
DESTINOS = {
    4: "http://www.msftconnecttest.com/connecttest.txt",
    6: "http://ipv6.msftconnecttest.com/connecttest.txt",
}
CONTEUDO = b"Microsoft Connect Test"
MARCADOR = b"\nMEUCONTROLEPC_HTTP="
MAX_CORPO = 2048
PRAZO = 7
AMBIENTE = frozenset(("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE",
    "HOMEDRIVE", "HOMEPATH"))


def _windows() -> bool:
    return os.name == "nt"


def _ler_valor(chave, nome):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, chave, 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as k:
            return winreg.QueryValueEx(k, nome)
    except FileNotFoundError:
        return None


def _booleano(chave, nome) -> str:
    import winreg
    valor = _ler_valor(chave, nome)
    if valor is None:
        return "ausente"
    dado, tipo = valor
    if tipo != winreg.REG_DWORD or type(dado) is not int or dado not in (0, 1):
        return "tipo_invalido"
    return str(bool(dado))


def _configuracao() -> dict:
    import winreg
    resultado = {}
    for nome, chave, campo in (
        ("sondas_ativas", CHAVE_NCSI, "EnableActiveProbing"),
        ("politica_sem_sondas", CHAVE_POLITICA, "NoActiveProbe"),
    ):
        try:
            resultado[nome] = _booleano(chave, campo)
        except OSError:
            resultado[nome] = "indisponivel"
    personalizado = False
    try:
        for nome, padrao in PADROES.items():
            valor = _ler_valor(CHAVE_NCSI, nome)
            if valor is None:
                continue
            dado, tipo = valor
            if tipo != winreg.REG_SZ or not isinstance(dado, str):
                personalizado = True
                continue
            if nome.endswith("Host") or nome.endswith("HostV6"):
                igual = dado.lower().rstrip(".") == padrao
            else:
                igual = dado == padrao
            if not igual:
                personalizado = True
        resultado["destino_personalizado"] = str(personalizado)
    except OSError:
        resultado["destino_personalizado"] = "indisponivel"
    return resultado


def _sem_links(caminho: Path) -> None:
    for item in (caminho, *caminho.parents):
        dados = item.lstat()
        if stat.S_ISLNK(dados.st_mode) or getattr(dados, "st_file_attributes", 0) & 0x400:
            raise OSError("caminho_indisponivel")


def _curl_executavel() -> Path:
    kernel = ctypes.WinDLL("kernel32.dll", use_last_error=True, winmode=0x800)
    funcao = kernel.GetSystemDirectoryW
    funcao.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    funcao.restype = ctypes.c_uint32
    buffer = ctypes.create_unicode_buffer(32768)
    tamanho = funcao(buffer, len(buffer))
    if not 0 < tamanho < len(buffer):
        raise OSError("curl_indisponivel")
    arquivo = Path(buffer.value) / "curl.exe"
    if not arquivo.is_absolute() or not arquivo.is_file():
        raise OSError("curl_indisponivel")
    _sem_links(arquivo)
    return arquivo


def _sondar(familia: int, executavel: Path) -> dict:
    if familia not in DESTINOS:
        return {"estado": "argumento_invalido"}
    try:
        with tempfile.TemporaryDirectory(prefix="MeuControlePC-NCSI-") as pasta:
            corpo = Path(pasta) / "resposta.bin"
            comando = [str(executavel), "-q", "-" + str(familia), "--noproxy", "*",
                "--connect-timeout", "2", "--max-time", "5", "--max-filesize", str(MAX_CORPO),
                "--limit-rate", str(MAX_CORPO), "--silent", "--show-error",
                "--output", str(corpo), "--write-out", MARCADOR.decode("ascii") + "%{http_code}",
                DESTINOS[familia]]
            ambiente = {k: v for k, v in os.environ.items() if k.upper() in AMBIENTE}
            resposta = subprocess.run(comando, shell=False, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=ambiente,
                timeout=PRAZO, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # stdout e somente o template local --write-out; corpo nunca vai ao terminal.
            saida = resposta.stdout
            if (not isinstance(saida, bytes) or len(saida) > 128
                    or not re.fullmatch(re.escape(MARCADOR) + rb"\d{3}", saida)):
                return {"estado": "resposta_invalida"}
            codigo = int(saida[-3:])
            if codigo and not 100 <= codigo <= 599:
                return {"estado": "resposta_invalida"}
            retorno = resposta.returncode
            if type(retorno) is not int or not 0 <= retorno <= 255:
                return {"estado": "resposta_invalida"}
            bruto = b""
            if corpo.is_file():
                with corpo.open("rb") as origem:
                    bruto = origem.read(MAX_CORPO + 1)
            esperado = retorno == 0 and codigo == 200 and bruto == CONTEUDO
            return {"estado": "consultado", "http": codigo,
                    "conteudo_esperado": esperado, "codigo_curl": retorno}
    except subprocess.TimeoutExpired:
        # run() encerra e recolhe somente o curl criado nesta chamada.
        return {"estado": "tempo_esgotado"}
    except OSError:
        return {"estado": "indisponivel"}


def diagnosticar() -> dict:
    if not _windows():
        return {"estado": "execute_no_windows"}
    try:
        configuracao = _configuracao()
    except Exception:
        configuracao = {"sondas_ativas": "indisponivel", "politica_sem_sondas": "indisponivel",
                        "destino_personalizado": "indisponivel"}
    try:
        executavel = _curl_executavel()
    except Exception:
        return {"estado": "curl_indisponivel", "configuracao": configuracao}
    with ThreadPoolExecutor(max_workers=2) as executor:
        futuros = {familia: executor.submit(_sondar, familia, executavel) for familia in (4, 6)}
        sondas = {familia: futuro.result() for familia, futuro in futuros.items()}
    return {"estado": "concluido", "configuracao": configuracao, "sondas": sondas}


def main(argumentos=None) -> int:
    args = sys.argv[1:] if argumentos is None else argumentos
    if args:
        print("NCSI_RESULTADO=argumento_invalido")
        return 1
    try:
        resultado = diagnosticar()
    except Exception:
        print("NCSI_RESULTADO=falha_local")
        return 1
    print("NCSI_RESULTADO=" + resultado["estado"])
    for campo, nome in (("sondas_ativas", "NCSI_SONDAS_ATIVAS"),
                        ("politica_sem_sondas", "NCSI_POLITICA_SEM_SONDAS"),
                        ("destino_personalizado", "NCSI_DESTINO_PERSONALIZADO")):
        if campo in resultado.get("configuracao", {}):
            print(nome + "=" + resultado["configuracao"][campo])
    for familia, sonda in resultado.get("sondas", {}).items():
        prefixo = "NCSI_" + str(familia)
        print(prefixo + "=" + sonda["estado"])
        if sonda["estado"] == "consultado":
            print(prefixo + "_HTTP=" + str(sonda["http"]))
            print(prefixo + "_CONTEUDO_ESPERADO=" + str(sonda["conteudo_esperado"]))
            print(prefixo + "_CURL_CODIGO=" + str(sonda["codigo_curl"]))
    return 0 if resultado["estado"] == "concluido" else 1


if __name__ == "__main__":
    raise SystemExit(main())
