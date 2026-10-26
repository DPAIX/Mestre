"""Teste reversivel da deteccao automatica de proxy do usuario Windows.

Nao consulta URLs, servidores ou credenciais. O registro e apenas lido; a
alteracao usa WinINet em um processo filho com prazo limitado.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys
import tempfile
from contextlib import contextmanager


BASE = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
POLITICA = r"Software\Policies\Microsoft\Windows\CurrentVersion\Internet Settings"
NOME_BACKUP = "autodeteccao_proxy_v1.json"
LIMITE_SET = 8
LIMITE_AVISO = 3
ETAPAS_SONDA = ("PYTHON_INICIADO", "IDENTIDADE_OK", "REGISTRO_OK",
                "WININET_CARREGADO", "QUERY_FLAGS_OK")
SEM_ETAPA = "NAO_CONFIRMADA"


class FalhaProxy(Exception):
    def __init__(self, codigo: str):
        self.codigo = codigo
        super().__init__(codigo)


def _windows() -> bool:
    return os.name == "nt"


def _dll(nome: str):
    return ctypes.WinDLL(nome, use_last_error=True, winmode=0x800)


def _identidade() -> str:
    """Hash do SID e da maquina; nenhum identificador cru e salvo ou exibido."""
    import winreg
    adv = _dll("advapi32.dll")
    kernel = _dll("kernel32.dll")
    adv.OpenProcessToken.argtypes = [ctypes.c_void_p, ctypes.c_uint32,
                                     ctypes.POINTER(ctypes.c_void_p)]
    adv.OpenProcessToken.restype = ctypes.c_int
    adv.GetTokenInformation.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                        ctypes.c_void_p, ctypes.c_uint32,
                                        ctypes.POINTER(ctypes.c_uint32)]
    adv.GetTokenInformation.restype = ctypes.c_int
    adv.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_void_p)]
    adv.ConvertSidToStringSidW.restype = ctypes.c_int
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    token = ctypes.c_void_p()
    sid_texto = ctypes.c_void_p()
    if not adv.OpenProcessToken(kernel.GetCurrentProcess(), 8, ctypes.byref(token)):
        raise FalhaProxy("identidade_indisponivel")
    try:
        tamanho = ctypes.c_uint32()
        adv.GetTokenInformation(token, 1, None, 0, ctypes.byref(tamanho))
        if not 0 < tamanho.value <= 65536:
            raise FalhaProxy("identidade_indisponivel")
        dados = ctypes.create_string_buffer(tamanho.value)
        if not adv.GetTokenInformation(token, 1, dados, tamanho.value,
                                        ctypes.byref(tamanho)):
            raise FalhaProxy("identidade_indisponivel")
        sid = ctypes.cast(dados, ctypes.POINTER(ctypes.c_void_p))[0]
        if not adv.ConvertSidToStringSidW(sid, ctypes.byref(sid_texto)):
            raise FalhaProxy("identidade_indisponivel")
        sid_valor = ctypes.wstring_at(sid_texto)
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Cryptography", 0,
                            winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as chave:
            maquina, tipo = winreg.QueryValueEx(chave, "MachineGuid")
        if tipo != winreg.REG_SZ or not isinstance(maquina, str) or not maquina:
            raise FalhaProxy("identidade_indisponivel")
        return hashlib.sha256((sid_valor + "|" + maquina).encode("utf-8")).hexdigest()
    finally:
        if sid_texto.value:
            kernel.LocalFree(sid_texto)
        if token.value:
            kernel.CloseHandle(token)


def _ler_estado() -> int:
    import winreg
    acesso = winreg.KEY_READ | winreg.KEY_WOW64_64KEY
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, POLITICA, 0, acesso) as k:
            try:
                valor, tipo = winreg.QueryValueEx(k, "ProxySettingsPerUser")
            except FileNotFoundError:
                valor, tipo = 1, winreg.REG_DWORD
            if tipo != winreg.REG_DWORD or type(valor) is not int:
                raise FalhaProxy("politica_incompativel")
            if valor == 0:
                raise FalhaProxy("proxy_da_maquina")
    except FileNotFoundError:
        pass
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE, 0, acesso) as k:
        manual, tipo = winreg.QueryValueEx(k, "ProxyEnable")
    if tipo != winreg.REG_DWORD or type(manual) is not int or manual != 0:
        raise FalhaProxy("configuracao_alterada")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, BASE + r"\Connections", 0,
                        acesso) as k:
        blob, tipo = winreg.QueryValueEx(k, "DefaultConnectionSettings")
    if tipo != winreg.REG_BINARY or not isinstance(blob, bytes) or not 12 <= len(blob) <= 65536:
        raise FalhaProxy("configuracao_incompativel")
    flags = struct.unpack_from("<I", blob, 8)[0]
    if flags & (2 | 4):
        raise FalhaProxy("configuracao_alterada")
    return flags


def _destino(flags: int) -> int:
    novo = flags & ~8
    if not novo & 15:
        novo |= 1  # Sem proxy manual/script, ainda deve existir o modo direto.
    return novo


def _sem_links(caminho: Path) -> None:
    for p in (caminho, *caminho.parents):
        if not p.exists() and not p.is_symlink():
            continue
        info = p.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise FalhaProxy("caminho_inseguro")


def _arquivo_backup() -> Path:
    raiz = Path(os.environ.get("LOCALAPPDATA", ""))
    if not raiz.is_absolute() or not raiz.is_dir():
        raise FalhaProxy("backup_indisponivel")
    _sem_links(raiz)
    pasta = raiz
    for nome in ("MeuControlePC", "reparo_proxy"):
        pasta = pasta / nome
        _sem_links(pasta)
        pasta.mkdir(exist_ok=True)
        _sem_links(pasta)
        if not pasta.is_dir():
            raise FalhaProxy("caminho_inseguro")
    arquivo = pasta / NOME_BACKUP
    _sem_links(arquivo)
    return arquivo


def _validar_backup(dados: object, identidade: str) -> dict:
    if not isinstance(dados, dict) or set(dados) != {
        "formato", "identidade", "flags_original", "flags_esperado"
    }:
        raise FalhaProxy("backup_incompativel")
    if type(dados["formato"]) is not int or dados["formato"] != 1 or dados["identidade"] != identidade:
        raise FalhaProxy("backup_incompativel")
    original = dados["flags_original"]
    esperado = dados["flags_esperado"]
    if (type(original) is not int or not 0 <= original <= 0xFFFFFFFF
            or type(esperado) is not int or original & 6 or not original & 8
            or esperado != _destino(original)):
        raise FalhaProxy("backup_incompativel")
    return dados


def _ler_backup(arquivo: Path, identidade: str) -> dict:
    _sem_links(arquivo)
    if not arquivo.is_file() or arquivo.stat().st_size > 2048:
        raise FalhaProxy("backup_incompativel")
    with arquivo.open("r", encoding="utf-8") as origem:
        return _validar_backup(json.load(origem), identidade)


def _criar_backup(arquivo: Path, identidade: str, original: int) -> dict:
    dados = _validar_backup({"formato": 1, "identidade": identidade,
                             "flags_original": original,
                             "flags_esperado": _destino(original)}, identidade)
    _sem_links(arquivo)
    # O_EXCL impede sobrescrever o backup original de uma execucao anterior.
    fd = os.open(arquivo, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as destino:
        json.dump(dados, destino, sort_keys=True)
        destino.flush()
        os.fsync(destino.fileno())
    return dados


@contextmanager
def _trava(identidade: str):
    kernel = _dll("kernel32.dll")
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, True, "Local\\MeuControlePCProxyAutoV1-" + identidade[:16])
    if not handle:
        raise FalhaProxy("trava_indisponivel")
    ocupado = ctypes.get_last_error() == 183
    try:
        if ocupado:
            raise FalhaProxy("ja_em_execucao")
        yield
    finally:
        if not ocupado:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _estruturas():
    class Tempo(ctypes.Structure):
        _fields_ = [("baixo", ctypes.c_uint32), ("alto", ctypes.c_uint32)]
    class Valor(ctypes.Union):
        _fields_ = [("numero", ctypes.c_uint32), ("texto", ctypes.c_void_p),
                    ("tempo", Tempo)]
    class Opcao(ctypes.Structure):
        _fields_ = [("opcao", ctypes.c_uint32), ("valor", Valor)]
    class Lista(ctypes.Structure):
        _fields_ = [("tamanho", ctypes.c_uint32), ("conexao", ctypes.c_wchar_p),
                    ("quantidade", ctypes.c_uint32), ("erro", ctypes.c_uint32),
                    ("opcoes", ctypes.POINTER(Opcao))]
    return Opcao, Lista


def _definir_flags(antes: int, depois: int, identidade: str) -> int:
    if _identidade() != identidade or _ler_estado() != antes:
        return 21
    # O trabalhador confere o estado novamente; nao recebe URL ou servidor.
    Opcao, Lista = _estruturas()
    opcao = Opcao()
    opcao.opcao = 1  # INTERNET_PER_CONN_FLAGS
    opcao.valor.numero = depois
    lista = Lista(ctypes.sizeof(Lista), None, 1, 0, ctypes.pointer(opcao))
    wininet = _dll("wininet.dll")
    funcao = wininet.InternetSetOptionW
    funcao.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    funcao.restype = ctypes.c_int
    _limpar_erro_nativo()
    if funcao(None, 75, ctypes.byref(lista), ctypes.sizeof(lista)):
        return 0
    _emitir_erro_nativo()
    return 22


def _numero_seguro(valor: object) -> int | None:
    return valor if type(valor) is int and -0x80000000 <= valor <= 0xFFFFFFFF else None


def _limpar_erro_nativo() -> None:
    if hasattr(ctypes, "set_last_error"):
        ctypes.set_last_error(0)


def _emitir_erro_nativo() -> None:
    erro = _numero_seguro(getattr(ctypes, "get_last_error", lambda: 0)())
    if erro is not None and erro >= 0:
        print("ERRO_NATIVO_PROXY=" + str(erro), flush=True)


def _sonda_worker() -> int:
    def etapa(nome: str) -> None:
        print("ETAPA_PROXY=" + nome, flush=True)
    etapa("PYTHON_INICIADO")
    _identidade()  # A identidade e lida, mas nunca emitida.
    etapa("IDENTIDADE_OK")
    _ler_estado()
    etapa("REGISTRO_OK")
    Opcao, Lista = _estruturas()
    opcao = Opcao()
    opcao.opcao = 10  # INTERNET_PER_CONN_FLAGS_UI: somente consulta.
    lista = Lista(ctypes.sizeof(Lista), None, 1, 0, ctypes.pointer(opcao))
    wininet = _dll("wininet.dll")
    etapa("WININET_CARREGADO")
    consultar = wininet.InternetQueryOptionW
    consultar.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                          ctypes.POINTER(ctypes.c_uint32)]
    consultar.restype = ctypes.c_int
    tamanho = ctypes.c_uint32(ctypes.sizeof(lista))
    _limpar_erro_nativo()
    if not consultar(None, 75, ctypes.byref(lista), ctypes.byref(tamanho)):
        _emitir_erro_nativo()
        return 22
    etapa("QUERY_FLAGS_OK")
    return 0


def _notificar() -> int:
    funcao = _dll("wininet.dll").InternetSetOptionW
    funcao.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32]
    funcao.restype = ctypes.c_int
    mudou = funcao(None, 39, None, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
    recarregou = funcao(None, 37, None, 0)  # INTERNET_OPTION_REFRESH
    return 0 if mudou and recarregou else 22


def _python_worker() -> Path:
    candidato = Path(getattr(sys, "_base_executable", sys.executable))
    if not candidato.is_absolute() or not candidato.is_file() or candidato.suffix.lower() != ".exe":
        raise FalhaProxy("python_indisponivel")
    _sem_links(candidato)
    return candidato


def _analisar_recibo(conteudo: bytes) -> dict:
    invalido = {"ultima_etapa": SEM_ETAPA, "recibo_valido": False}
    if not isinstance(conteudo, bytes) or len(conteudo) > 2048:
        return invalido
    try:
        linhas = conteudo.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return invalido
    etapas = []
    erro = None
    for linha in linhas:
        if not linha:
            continue
        if linha.startswith("ETAPA_PROXY="):
            nome = linha[len("ETAPA_PROXY="):]
            if len(etapas) >= len(ETAPAS_SONDA) or nome != ETAPAS_SONDA[len(etapas)]:
                return invalido
            etapas.append(nome)
        elif re.fullmatch(r"ERRO_NATIVO_PROXY=\d{1,10}", linha) and erro is None:
            erro = int(linha.split("=", 1)[1])
            if erro > 0xFFFFFFFF:
                return invalido
        else:
            return invalido
    resultado = {"ultima_etapa": etapas[-1] if etapas else SEM_ETAPA,
                 "recibo_valido": True}
    if erro is not None:
        resultado["erro_nativo"] = erro
    return resultado


def _executar_worker(argumentos: list[str], prazo: int) -> dict:
    python = _python_worker()
    fonte = Path(__file__).absolute()
    _sem_links(fonte)
    permitidas = ("SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "USERPROFILE",
                  "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "ALLUSERSPROFILE",
                  "HOMEDRIVE", "HOMEPATH", "USERNAME", "USERDOMAIN", "COMSPEC", "PATH")
    ambiente = {k: os.environ[k] for k in permitidas
                if k in os.environ}
    with tempfile.TemporaryFile(mode="w+b") as captura:
        codigo = None
        erro_inicio = None
        try:
            resultado = subprocess.run([str(python), "-I", "-S", "-E", str(fonte), *argumentos],
                                       shell=False, stdin=subprocess.DEVNULL,
                                       stdout=captura, stderr=subprocess.DEVNULL,
                                       env=ambiente, timeout=prazo, check=False,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            codigo = _numero_seguro(resultado.returncode)
            tentativa = "ok" if codigo == 0 else "falha"
        except subprocess.TimeoutExpired:
            # subprocess.run encerra e recolhe somente o filho desta chamada.
            tentativa = "tempo_esgotado"
        except OSError as erro:
            tentativa = "falha"
            erro_inicio = _numero_seguro(getattr(erro, "winerror", None))
        captura.seek(0)
        recibo = _analisar_recibo(captura.read(2049))
    if not recibo.pop("recibo_valido"):
        tentativa = "falha"
    recibo["tentativa"] = tentativa
    if codigo is not None:
        recibo["codigo_saida"] = codigo
    if erro_inicio is not None and erro_inicio >= 0:
        recibo["erro_nativo"] = erro_inicio
    return recibo


def _recibo_publico(execucao: object) -> dict:
    # Aceita tambem os recibos de texto antigos usados por chamadores internos.
    if isinstance(execucao, str):
        return {"tentativa": execucao if execucao in {"ok", "falha", "tempo_esgotado"} else "falha"}
    if not isinstance(execucao, dict):
        return {"tentativa": "falha"}
    recibo = {"tentativa": execucao.get("tentativa") if execucao.get("tentativa") in
              {"ok", "falha", "tempo_esgotado"} else "falha"}
    etapa = execucao.get("ultima_etapa")
    if etapa in (*ETAPAS_SONDA, SEM_ETAPA):
        recibo["ultima_etapa"] = etapa
    for nome in ("codigo_saida", "erro_nativo"):
        numero = _numero_seguro(execucao.get(nome))
        if numero is not None and (nome != "erro_nativo" or numero >= 0):
            recibo[nome] = numero
    return recibo


def diagnosticar() -> dict:
    if not _windows():
        return {"sonda": "falha", "ultima_etapa": SEM_ETAPA}
    try:
        recibo = _recibo_publico(_executar_worker(["--worker-diagnosticar"], LIMITE_SET))
        tentativa = recibo["tentativa"]
        if tentativa == "ok" and recibo.get("ultima_etapa") == "QUERY_FLAGS_OK":
            estado = "concluida"
        else:
            estado = "tempo_esgotado" if tentativa == "tempo_esgotado" else "falha"
        return {"sonda": estado, "ultima_etapa": recibo.get("ultima_etapa", SEM_ETAPA),
                **{k: v for k, v in recibo.items() if k in {"codigo_saida", "erro_nativo"}}}
    except Exception:
        return {"sonda": "falha", "ultima_etapa": SEM_ETAPA}


def ajustar(modo: str) -> dict:
    if not _windows():
        return {"estado": "execute_no_windows"}
    try:
        if modo not in {"desativar", "restaurar"}:
            raise FalhaProxy("argumento_invalido")
        identidade = _identidade()
        with _trava(identidade):
            atual = _ler_estado()
            arquivo = _arquivo_backup()
            if modo == "restaurar":
                if not arquivo.exists():
                    raise FalhaProxy("backup_ausente")
                backup = _ler_backup(arquivo, identidade)
                antes, depois = backup["flags_esperado"], backup["flags_original"]
                if atual == depois:
                    return {"estado": "ja_restaurado"}
                if atual != antes:
                    raise FalhaProxy("configuracao_alterada")
            else:
                if arquivo.exists():
                    backup = _ler_backup(arquivo, identidade)
                    if atual == backup["flags_esperado"]:
                        return {"estado": "ja_aplicado"}
                    if atual != backup["flags_original"]:
                        raise FalhaProxy("configuracao_alterada")
                else:
                    if not atual & 8:
                        raise FalhaProxy("autodeteccao_ja_desativada")
                    backup = _criar_backup(arquivo, identidade, atual)
                antes, depois = backup["flags_original"], backup["flags_esperado"]
            if _ler_estado() != antes:
                raise FalhaProxy("configuracao_alterada")
            recibo = _recibo_publico(_executar_worker(["--worker-set", str(antes), str(depois), identidade], LIMITE_SET))
            # Confere inclusive se a API expirou depois de aplicar a mudanca.
            try:
                conferido = _ler_estado()
            except Exception:
                return {"estado": "incerto", **recibo}
            if conferido == antes:
                return {"estado": "inalterado", **recibo}
            if conferido != depois:
                return {"estado": "incerto", **recibo}
            aviso = _recibo_publico(_executar_worker(["--worker-notify"], LIMITE_AVISO))
            return {"estado": "restaurado" if modo == "restaurar" else "aplicado",
                    **recibo,
                    "atualizacao": "solicitada" if aviso["tentativa"] == "ok" else "pendente"}
    except FalhaProxy as erro:
        return {"estado": erro.codigo}
    except Exception:
        return {"estado": "falha_local"}


MENSAGENS = {
    "aplicado": "Deteccao automatica desativada. Backup original preservado.",
    "restaurado": "Configuracao original de deteccao automatica restaurada.",
    "ja_aplicado": "A deteccao automatica ja esta desativada por este reparo.",
    "ja_restaurado": "A configuracao original ja esta restaurada.",
    "inalterado": "A alteracao nao foi confirmada; a configuracao anterior permanece.",
    "incerto": "Nao foi possivel confirmar o resultado. Nao repita o reparo automaticamente.",
    "execute_no_windows": "Execute este arquivo no Windows.",
    "proxy_da_maquina": "A politica usa proxy da maquina; este reparo nao se aplica.",
    "configuracao_alterada": "A configuracao difere do teste ou do backup; nenhuma nova alteracao foi enviada.",
    "backup_ausente": "Nao existe backup deste reparo para restaurar.",
    "backup_incompativel": "O backup nao corresponde a este usuario, computador ou formato.",
    "autodeteccao_ja_desativada": "A deteccao automatica ja esta desativada; nenhuma alteracao necessaria.",
}


def main(argumentos: list[str] | None = None) -> int:
    args = sys.argv[1:] if argumentos is None else argumentos
    if args == ["--worker-diagnosticar"] and _windows():
        try:
            return _sonda_worker()
        except Exception:
            return 23
    if args == ["--diagnosticar"]:
        resultado = diagnosticar()
        print("PROXY_SONDA=" + resultado["sonda"])
        print("ULTIMA_ETAPA=" + resultado["ultima_etapa"])
        if "codigo_saida" in resultado:
            print("CODIGO_SAIDA=" + str(resultado["codigo_saida"]))
        if "erro_nativo" in resultado:
            print("ERRO_NATIVO_PROXY=" + str(resultado["erro_nativo"]))
        return 0 if resultado["sonda"] == "concluida" else 1
    if args == ["--worker-notify"] and _windows():
        try:
            return _notificar()
        except Exception:
            return 23
    if len(args) == 4 and args[0] == "--worker-set" and _windows():
        try:
            if (not re.fullmatch(r"\d{1,10}", args[1]) or not re.fullmatch(r"\d{1,10}", args[2])
                    or not re.fullmatch(r"[a-f0-9]{64}", args[3])):
                return 23
            antes, depois = int(args[1]), int(args[2])
            original = antes if antes & 8 else depois
            if (not 0 <= antes <= 0xFFFFFFFF or not 0 <= depois <= 0xFFFFFFFF
                    or original & 6 or not original & 8
                    or {antes, depois} != {original, _destino(original)}):
                return 23
            return _definir_flags(antes, depois, args[3])
        except Exception:
            return 23
    resultado = ajustar(args[0][2:]) if len(args) == 1 and args[0] in {"--desativar", "--restaurar"} else {"estado": "argumento_invalido"}
    estado = resultado["estado"]
    print("RESULTADO_PROXY=" + estado)
    print(MENSAGENS.get(estado, "Nao foi possivel concluir este reparo local."))
    if "tentativa" in resultado:
        print("TENTATIVA_PROXY=" + resultado["tentativa"])
    if "codigo_saida" in resultado:
        print("CODIGO_SAIDA=" + str(resultado["codigo_saida"]))
    if "erro_nativo" in resultado:
        print("ERRO_NATIVO_PROXY=" + str(resultado["erro_nativo"]))
    if resultado.get("atualizacao") == "pendente":
        print("A notificacao aos aplicativos ficou pendente; encerre e reabra o Spotify para testar.")
    return 0 if estado in {"aplicado", "restaurado", "ja_aplicado", "ja_restaurado", "autodeteccao_ja_desativada"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
