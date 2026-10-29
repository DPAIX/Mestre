"""Desativa somente o bloqueio de wl.spotify.com, com backup local reversivel."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile

ALVO = 'wl.spotify.com'
MAX_ARQUIVO = 16 * 1024 * 1024
BACKUP = 'hosts.antes-spotify.bak'
RECIBO = 'hosts.reparo-spotify.json'
BLOQUEADORES = {'0.0.0.0', '127.0.0.1', '::', '::1'}


class FalhaHosts(Exception):
    def __init__(self, codigo):
        self.codigo = codigo
        super().__init__(codigo)


def _windows():
    return os.name == 'nt'


def _dll(nome):
    return ctypes.WinDLL(nome, use_last_error=True, winmode=0x800)


def _administrador():
    funcao = _dll('shell32.dll').IsUserAnAdmin
    funcao.argtypes = []
    funcao.restype = ctypes.c_int
    return bool(funcao())


def _hosts_do_windows():
    funcao = _dll('kernel32.dll').GetWindowsDirectoryW
    funcao.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32]
    funcao.restype = ctypes.c_uint32
    texto = ctypes.create_unicode_buffer(32768)
    tamanho = funcao(texto, len(texto))
    if not 0 < tamanho < len(texto):
        raise FalhaHosts('diretorio_windows_indisponivel')
    pasta = Path(texto.value)
    if not pasta.is_absolute():
        raise FalhaHosts('diretorio_windows_indisponivel')
    return pasta / 'System32' / 'drivers' / 'etc' / 'hosts'


def _sem_links(caminho):
    for item in (caminho, *caminho.parents):
        if not item.exists() and not item.is_symlink():
            continue
        info = item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise FalhaHosts('caminho_inseguro')
        if item == caminho and stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise FalhaHosts('caminho_inseguro')


def _ler(caminho, limite=MAX_ARQUIVO):
    _sem_links(caminho)
    info = caminho.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limite:
        raise FalhaHosts('arquivo_incompativel')
    with caminho.open('rb') as origem:
        dados = origem.read(limite + 1)
    if len(dados) > limite:
        raise FalhaHosts('arquivo_incompativel')
    return dados


def _hash(dados):
    return hashlib.sha256(dados).hexdigest()


def transformar(dados):
    """Retorna bytes preservados e quantidade de aliases bloqueados desativados."""
    if not isinstance(dados, bytes) or len(dados) > MAX_ARQUIVO:
        raise FalhaHosts('arquivo_incompativel')
    prefixo, codec = b'', 'latin-1'
    for bom, nome in [(b'\xff\xfe\0\0', 'utf-32-le'), (b'\0\0\xfe\xff', 'utf-32-be'),
                      (b'\xff\xfe', 'utf-16-le'), (b'\xfe\xff', 'utf-16-be'),
                      (b'\xef\xbb\xbf', 'utf-8')]:
        if dados.startswith(bom):
            prefixo, codec = bom, nome
            break
    texto = dados[len(prefixo):].decode(codec, errors='strict')
    saida, total = [], 0
    for linha in texto.splitlines(keepends=True):
        conteudo = linha.rstrip('\r\n')
        fim = linha[len(conteudo):]
        ativo, separador, comentario = conteudo.partition('#')
        tokens = list(re.finditer(r'[^ \t]+', ativo))
        try:
            bloqueador = bool(tokens) and str(ipaddress.ip_address(tokens[0].group())) in BLOQUEADORES
        except ValueError:
            bloqueador = False
        alvos = [t for t in tokens[1:] if t.group().lower().rstrip('.') == ALVO] if bloqueador else []
        if not alvos:
            saida.append(linha)
            continue
        total += len(alvos)
        if len(alvos) == len(tokens) - 1:
            # Preserva integralmente o mapeamento e seu comentario como comentario.
            saida.append('# MeuControlePC: bloqueio desativado; ' + linha)
        else:
            for token in reversed(alvos):
                ativo = ativo[:token.start()] + ativo[token.end():]
            saida.append(ativo + separador + comentario + fim)
    return prefixo + ''.join(saida).encode(codec), total


def _criar_exclusivo(caminho, dados):
    _sem_links(caminho)
    fd = os.open(caminho, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as destino:
        destino.write(dados)
        destino.flush()
        os.fsync(destino.fileno())


def _validar_recibo(info):
    if not isinstance(info, dict) or set(info) != {'formato', 'backup', 'original', 'aplicado', 'alteracoes'}:
        raise FalhaHosts('backup_incompativel')
    if (type(info['formato']) is not int or info['formato'] != 1 or info['backup'] != BACKUP
            or type(info['alteracoes']) is not int or info['alteracoes'] < 1
            or any(not isinstance(info[n], str) or not re.fullmatch(r'[a-f0-9]{64}', info[n]) for n in ('original', 'aplicado'))
            or info['original'] == info['aplicado']):
        raise FalhaHosts('backup_incompativel')
    return info


def _preparar_backup(alvo, original, aplicado, quantidade):
    copia, recibo = alvo.with_name(BACKUP), alvo.with_name(RECIBO)
    info = _validar_recibo({'formato': 1, 'backup': BACKUP, 'original': _hash(original),
                            'aplicado': _hash(aplicado), 'alteracoes': quantidade})
    if copia.exists():
        if _hash(_ler(copia)) != info['original']:
            raise FalhaHosts('backup_incompativel')
    else:
        _criar_exclusivo(copia, original)
    if recibo.exists():
        salvo = _validar_recibo(json.loads(_ler(recibo, 4096)))
        if salvo != info:
            raise FalhaHosts('backup_incompativel')
    else:
        _criar_exclusivo(recibo, (json.dumps(info, sort_keys=True) + '\n').encode('ascii'))
    return info


def _substituir_nativo(alvo, temporario):
    funcao = _dll('kernel32.dll').ReplaceFileW
    funcao.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                       ctypes.c_uint32, ctypes.c_void_p, ctypes.c_void_p]
    funcao.restype = ctypes.c_int
    if not funcao(str(alvo), str(temporario), None, 0, None, None):
        raise ctypes.WinError(ctypes.get_last_error())


def _substituir(alvo, dados, esperado):
    _sem_links(alvo)
    if getattr(alvo.stat(), 'st_file_attributes', 0) & 1:
        raise FalhaHosts('somente_leitura')
    fd, nome = tempfile.mkstemp(prefix='.hosts-spotify-', suffix='.tmp', dir=alvo.parent)
    temporario = Path(nome)
    try:
        with os.fdopen(fd, 'wb') as destino:
            destino.write(dados)
            destino.flush()
            os.fsync(destino.fileno())
        if _ler(temporario) != dados or _hash(_ler(alvo)) != esperado:
            raise FalhaHosts('arquivo_alterado')
        _sem_links(alvo)
        _substituir_nativo(alvo, temporario)
        if _ler(alvo) != dados:
            raise FalhaHosts('resultado_incerto')
    finally:
        temporario.unlink(missing_ok=True)


@contextmanager
def _trava():
    kernel = _dll('kernel32.dll')
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel.ReleaseMutex.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateMutexW(None, True, 'Global\\MeuControlePCHostsSpotifyV1')
    if not handle:
        raise FalhaHosts('trava_indisponivel')
    ocupado = ctypes.get_last_error() == 183
    try:
        if ocupado:
            raise FalhaHosts('ja_em_execucao')
        yield
    finally:
        if not ocupado:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def executar(modo):
    if not _windows():
        return {'estado': 'execute_no_windows'}
    try:
        if modo not in {'corrigir', 'restaurar'}:
            raise FalhaHosts('argumento_invalido')
        if not _administrador():
            raise FalhaHosts('requer_administrador')
        with _trava():
            alvo = _hosts_do_windows()
            atual = _ler(alvo)
            if modo == 'corrigir':
                novo, quantidade = transformar(atual)
                if not quantidade:
                    return {'estado': 'sem_bloqueio', 'alteracoes': 0}
                info = _preparar_backup(alvo, atual, novo, quantidade)
                _substituir(alvo, novo, info['original'])
                return {'estado': 'corrigido', 'alteracoes': quantidade}
            info = _validar_recibo(json.loads(_ler(alvo.with_name(RECIBO), 4096)))
            original = _ler(alvo.with_name(BACKUP))
            if _hash(original) != info['original']:
                raise FalhaHosts('backup_incompativel')
            if _hash(atual) == info['original']:
                return {'estado': 'ja_restaurado', 'alteracoes': 0}
            if _hash(atual) != info['aplicado']:
                raise FalhaHosts('arquivo_alterado')
            _substituir(alvo, original, info['aplicado'])
            return {'estado': 'restaurado', 'alteracoes': info['alteracoes']}
    except FalhaHosts as erro:
        return {'estado': erro.codigo}
    except OSError as erro:
        resultado = {'estado': 'falha_de_acesso'}
        codigo = getattr(erro, 'winerror', None)
        if type(codigo) is int and 0 <= codigo <= 0xFFFFFFFF:
            resultado['winerror'] = codigo
        return resultado
    except Exception:
        return {'estado': 'arquivo_ou_backup_incompativel'}


def main(argumentos=None):
    args = sys.argv[1:] if argumentos is None else argumentos
    resultado = executar(args[0][2:]) if args in (['--corrigir'], ['--restaurar']) else {'estado': 'argumento_invalido'}
    print('HOSTS_RESULTADO=' + resultado['estado'])
    if 'alteracoes' in resultado:
        print('HOSTS_ALTERACOES=' + str(resultado['alteracoes']))
    if 'winerror' in resultado:
        print('HOSTS_WINERROR=' + str(resultado['winerror']))
    return 0 if resultado['estado'] in {'corrigido', 'restaurado', 'ja_restaurado', 'sem_bloqueio'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
