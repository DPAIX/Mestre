"""Seleção explícita da quantização leve; nenhum download ou inferência aqui.

O original permanece no catálogo. Somente OLLAMA_27B_LEVE=1, gravado após o
teste solicitado no PC, permite usar o artefato público conferido na equipe.
"""
from __future__ import annotations

import os

MODELO_ORIGINAL = 'qwen3.8:27b'
MODELO_LEVE = 'batiai/qwen3.8-27b:iq3'
DIGEST_MANIFESTO = 'abca93dece6899e6b1f4a98dfb8089c328fadc65a3df825d33ca5e39e0961d64'
TAMANHO_BYTES = 11_186_385_185  # Camadas e config; o manifesto não entra em /api/tags.


def ativada():
    valor = os.getenv('OLLAMA_27B_LEVE', '0')
    if valor not in ('0', '1'):
        raise ValueError('OLLAMA_27B_LEVE deve ser 0 ou 1. Confira a preparação do modelo leve.')
    return valor == '1'


def conferir_alternativa(catalogo):
    """Exige registro local e o manifesto conferido, sem confiar só no nome."""
    if not isinstance(catalogo, list):
        raise ValueError('Catálogo inválido para conferir o modelo leve.')
    itens = [m for m in catalogo if isinstance(m, dict) and m.get('nome') == MODELO_LEVE]
    if (not itens or any(m.get('nuvem') is not False or
            not isinstance(m.get('digest'), str) or
            m['digest'].removeprefix('sha256:') != DIGEST_MANIFESTO for m in itens)):
        raise ValueError('A versão leve local não corresponde ao manifesto conferido. '
                         'Abra PREPARAR_27B_LEVE.bat; nenhuma substituição ou geração foi enviada.')
    return dict(itens[0])


def selecionar(modelos, catalogo):
    """Devolve nomes e aviso, preservando todos os demais participantes."""
    nomes = list(modelos)
    if not ativada():
        return nomes, ''
    if not any(n in (MODELO_ORIGINAL, MODELO_LEVE) for n in nomes):
        return nomes, ''
    conferir_alternativa(catalogo)
    escolhidos = list(dict.fromkeys(MODELO_LEVE if n == MODELO_ORIGINAL else n for n in nomes))
    return escolhidos, (f'Versão leve selecionada para a equipe: {MODELO_LEVE}. '
                        f'O original {MODELO_ORIGINAL} permanece instalado; não foi consultado nesta rodada.')
