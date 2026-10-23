"""Trava de arquivo mantida pelo processo; impede dois bots nos mesmos dados."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sys

_WINDOWS = sys.platform == 'win32'
NOME_TRAVA = '.meucontrolepc_instancia.lock'


class InstanciaAtiva(RuntimeError):
    """Outro processo mantém o assistente ativo no mesmo diretório de dados."""


def _bloquear(arquivo):
    arquivo.seek(0)
    if _WINDOWS:
        import msvcrt
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _desbloquear(arquivo):
    arquivo.seek(0)
    if _WINDOWS:
        import msvcrt
        msvcrt.locking(arquivo.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(arquivo.fileno(), fcntl.LOCK_UN)


@contextmanager
def instancia_unica(diretorio_dados):
    """Mantém a trava até o término do contexto, inclusive durante polling.

    O arquivo não é apagado: remover o caminho permitiria a um terceiro
    processo criar outro inode enquanto um segundo ainda usa o antigo.
    """
    pasta = Path(diretorio_dados)
    if not pasta.is_absolute():
        raise ValueError('O diretório de dados da instância deve ser absoluto.')
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / NOME_TRAVA
    if caminho.is_symlink():
        raise RuntimeError('Arquivo de trava inválido; confira o diretório de dados.')
    descritor = os.open(caminho, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descritor, 'r+b') as arquivo:
        try:
            _bloquear(arquivo)
        except OSError:
            raise InstanciaAtiva('O assistente já está em execução com esses dados. A segunda inicialização foi ignorada.') from None
        try:
            arquivo.seek(0)
            arquivo.write(b'\0')
            arquivo.seek(1)
            arquivo.truncate()
            arquivo.write(str(os.getpid()).encode('ascii'))
            arquivo.flush()
            yield
        finally:
            _desbloquear(arquivo)
