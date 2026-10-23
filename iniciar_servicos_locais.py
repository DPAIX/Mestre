"""Inicia somente o Ollama instalado quando o endpoint de loopback está ausente.

Uma tentativa de criação e leituras finitas de metadados. Não baixa modelos,
encerra processos, altera arquivos do serviço ou consulta credenciais.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from caminhos_instalacao import arquivo_env
from diagnostico_ollama import consultar, validar_url, URL_PADRAO

BASE = Path(__file__).resolve().parent
_WINDOWS = sys.platform == 'win32'
PRAZO_INICIO = 15
MAX_CONSULTAS = 5
_AMBIENTE_PUBLICO = frozenset({
    'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
    'LANG', 'LC_ALL', 'USERPROFILE', 'HOME', 'HOMEDRIVE', 'HOMEPATH',
    'LOCALAPPDATA', 'APPDATA', 'OLLAMA_MODELS',
})


def _resultado(ok, iniciado, mensagem):
    return {'ok': ok, 'iniciado': iniciado, 'mensagem': mensagem}


def _executavel_ollama():
    encontrado = shutil.which('ollama')
    if encontrado:
        caminho = Path(encontrado)
        if caminho.is_file():
            return caminho.resolve()
    if _WINDOWS:
        local = os.getenv('LOCALAPPDATA')
        if local:
            candidato = Path(local) / 'Programs' / 'Ollama' / 'ollama.exe'
            if candidato.is_file():
                return candidato.resolve()
    return None


def _ambiente_servidor(url):
    # Evita repassar chaves, proxy, Python ou hosts remotos ao processo local.
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE_PUBLICO}
    ambiente['OLLAMA_HOST'] = url
    if not any(k.upper() == 'OLLAMA_MODELS' for k in ambiente):
        # Na instalação redirecionada F:\MeuControlePC_v2\.env, reaproveita
        # F:\Models apenas se a estrutura do catálogo já existir.
        pasta_env = arquivo_env(BASE).parent
        candidato = pasta_env.parent / 'Models'
        if candidato.is_dir() and (candidato / 'manifests').is_dir():
            ambiente['OLLAMA_MODELS'] = str(candidato)
    return ambiente


def _responde(url, timeout):
    resposta = consultar(url, '/api/version', timeout=timeout)
    dados = resposta.get('dados')
    return bool(resposta.get('ok') and isinstance(dados, dict)
                and isinstance(dados.get('version'), str) and dados['version'].strip())


def garantir_ollama():
    """Garante uma tentativa finita de início; não confunde versão com inferência."""
    if os.getenv('OLLAMA_HABILITADO') != '1':
        return _resultado(False, False, 'Integração Ollama desabilitada; nenhum serviço foi iniciado.')
    try:
        url = validar_url(os.getenv('OLLAMA_URL', URL_PADRAO))
    except ValueError:
        return _resultado(False, False, 'Endereço Ollama inválido; configure somente IP de loopback.')
    inicio = time.monotonic()
    try:
        if _responde(url, 3):
            return _resultado(True, False, 'Ollama já responde aos metadados locais; geração ainda não verificada.')
        caminho = _executavel_ollama()
        if caminho is None:
            return _resultado(False, False, 'Ollama não foi encontrado no PC. Instale-o para usar os modelos locais.')
        ambiente = _ambiente_servidor(url)
        opcoes = {'env': ambiente, 'shell': False, 'stdin': subprocess.DEVNULL,
                  'stdout': subprocess.DEVNULL, 'stderr': subprocess.DEVNULL}
        if _WINDOWS:
            opcoes['creationflags'] = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
        processo = subprocess.Popen([str(caminho), 'serve'], **opcoes)
    except (OSError, ValueError):
        return _resultado(False, False, 'Não foi possível iniciar o Ollama instalado; confira o executável e a configuração local.')
    try:
        for _ in range(MAX_CONSULTAS):
            restante = PRAZO_INICIO - (time.monotonic() - inicio)
            if restante <= 0:
                break
            if _responde(url, min(3, restante)):
                return _resultado(True, True, 'Ollama iniciado e metadados locais acessíveis; geração ainda não verificada.')
            if processo.poll() is not None:
                return _resultado(False, True, 'O Ollama encerrou antes de responder. Nenhuma reinicialização ou download foi feito.')
            restante = PRAZO_INICIO - (time.monotonic() - inicio)
            if restante > 0:
                time.sleep(min(0.25, restante))
    except (OSError, ValueError):
        return _resultado(False, True, 'Não foi possível confirmar os metadados do Ollama iniciado. Os comandos locais continuam disponíveis.')
    return _resultado(False, True, 'O Ollama foi iniciado, mas não respondeu dentro da verificação. Nenhum novo processo foi agendado.')
