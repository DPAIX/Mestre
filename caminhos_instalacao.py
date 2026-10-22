"""Caminhos de configuração e dados, independentes da pasta de código.

Os seletores são variáveis do processo, definidas antes de importar o núcleo.
Este módulo não lê credenciais, cria diretórios ou importa a aplicação.
"""
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(__file__).resolve().parent
SELETORES = frozenset({'MEUCONTROLEPC_ENV', 'MEUCONTROLEPC_DADOS'})


def _absoluto(valor, nome):
    texto = os.fspath(valor).strip()
    if len(texto) >= 2 and texto[0] == texto[-1] and texto[0] in ('"', "'"):
        texto = texto[1:-1]
    if not texto or any(c in texto for c in ('\x00', '\r', '\n')):
        raise ValueError(nome + ' exige um caminho absoluto válido.')
    caminho = Path(texto).expanduser()
    if not caminho.is_absolute():
        raise ValueError(nome + ' exige um caminho absoluto, independente da pasta atual.')
    return caminho.resolve()


def arquivo_env(base=None):
    """Seleciona um único .env; um seletor explícito nunca usa fallback local."""
    if 'MEUCONTROLEPC_ENV' in os.environ:
        return _absoluto(os.environ['MEUCONTROLEPC_ENV'], 'MEUCONTROLEPC_ENV')
    return Path(base if base is not None else BASE) / '.env'


def diretorio_dados(base=None):
    """Sem seletores preserva o legado; .env externo usa dados junto dele."""
    if 'MEUCONTROLEPC_DADOS' in os.environ:
        return _absoluto(os.environ['MEUCONTROLEPC_DADOS'], 'MEUCONTROLEPC_DADOS')
    if 'MEUCONTROLEPC_ENV' in os.environ:
        return arquivo_env(base).parent / 'dados'
    return Path(base if base is not None else BASE) / 'dados'


def ancestral_existente(caminho):
    """Permite consultar espaço antes da primeira criação da pasta de dados."""
    caminho = Path(caminho)
    while not caminho.exists() and caminho != caminho.parent:
        caminho = caminho.parent
    return caminho
