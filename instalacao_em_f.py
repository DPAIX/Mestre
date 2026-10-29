"""Política explícita para manter os arquivos volumosos do assistente em F.

Importar ou planejar não cria pastas. O perfil Windows principal permanece;
os serviços externos recebem perfis próprios somente nos seus subprocessos.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
import stat

RAIZ_PADRAO = 'F:/MeuControlePC_v2'


def ativo():
    valor = os.getenv('MEUCONTROLEPC_SOMENTE_F', '0')
    if valor not in ('0', '1'):
        raise ValueError('MEUCONTROLEPC_SOMENTE_F deve ser 0 ou 1.')
    return valor == '1'


def validar_caminho(valor):
    texto = os.fspath(valor)
    if not isinstance(texto, str) or any(c in texto for c in ('\0', '\r', '\n')):
        raise ValueError('Use um caminho absoluto no disco F:.')
    p = PureWindowsPath(texto)
    if (not p.is_absolute() or p.drive.casefold() != 'f:' or
            '..' in p.parts or any(':' in x for x in p.parts[1:])):
        raise ValueError('Esta instalação exige caminhos locais no disco F:, sem redirecionamento.')
    caminho = Path(p.as_posix())
    for parte in (caminho, *caminho.parents):
        try:
            meta = parte.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Os caminhos da instalação em F: não podem usar links ou junctions.')
    return caminho


def raiz():
    return validar_caminho(os.getenv('MEUCONTROLEPC_RAIZ_F', RAIZ_PADRAO))


def ambiente(base=None):
    """Somente opções públicas; não copia ambiente ou credenciais do chamador."""
    pasta = raiz() if base is None else validar_caminho(base)
    cache = pasta / 'cache'
    return {
        'MEUCONTROLEPC_SOMENTE_F': '1', 'MEUCONTROLEPC_RAIZ_F': str(pasta),
        'TEMP': str(pasta/'temporarios'), 'TMP': str(pasta/'temporarios'),
        'TMPDIR': str(pasta/'temporarios'),
        'PIP_CACHE_DIR': str(cache/'pip'), 'UV_CACHE_DIR': str(cache/'uv'),
        'HF_HOME': str(cache/'huggingface'),
        'HUGGINGFACE_HUB_CACHE': str(cache/'huggingface'/'hub'),
        'XDG_CACHE_HOME': str(cache), 'TORCH_HOME': str(cache/'torch'),
        'NUMBA_CACHE_DIR': str(cache/'numba'), 'NPM_CONFIG_CACHE': str(cache/'npm'),
        'CUDA_CACHE_PATH': str(cache/'cuda'), 'TRITON_CACHE_DIR': str(cache/'triton'),
        'MPLCONFIGDIR': str(cache/'matplotlib'),
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1',
    }


def preparar_pastas():
    pasta = raiz()
    if not Path(PureWindowsPath(str(pasta)).anchor).is_dir():
        raise ValueError('O disco F: não está disponível; nenhuma instalação foi enviada para C:.')
    caminhos = [pasta, pasta/'runtime'/'Local', pasta/'runtime'/'Roaming',
                pasta/'runtime'/'perfil']
    caminhos += [Path(v) for k, v in ambiente().items()
                 if k not in ('MEUCONTROLEPC_SOMENTE_F','MEUCONTROLEPC_RAIZ_F',
                              'PYTHONDONTWRITEBYTECODE','PYTHONUTF8')]
    for caminho in caminhos:
        validar_caminho(caminho).mkdir(parents=True, exist_ok=True)
