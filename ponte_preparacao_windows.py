"""Abre somente as telas oficiais necessárias à preparação local.

Um fluxo autorizado pode preparar bibliotecas e reaproveitar credenciais locais,
mas uma página aberta não prova login, criação de chave ou autorização de conta.
Esta ponte não captura tela/clipboard, não lê credenciais e não aciona tarefas
RoboTask desconhecidas. URLs e o executável Windows são fixos, sem shell livre.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import threading

_ALVOS = {
    '9router_contas': ('Contas do 9Router', 'http://127.0.0.1:20128/dashboard/providers',
        'Conecte a conta desejada na interface oficial; login, 2FA e permissões pertencem ao provedor.'),
    '9router_chave': ('Chave local 9Router', 'http://127.0.0.1:20128/dashboard/endpoint',
        'Crie ou confira a chave na interface local. A abertura não lê a chave nem comprova o modelo.'),
    'gemini_chave': ('Gemini API / Google AI Studio', 'https://aistudio.google.com/app/apikey',
        'Conclua o login e a autorização do projeto Google. Chave, acesso e cota da API são separados da assinatura Colab.'),
    'telegram_token': ('Telegram BotFather', 'https://t.me/BotFather',
        'Use sua conta Telegram para criar/renovar o token do bot. Cole o token somente no campo oculto do configurador local.'),
    'openai_chave': ('OpenAI API', 'https://platform.openai.com/api-keys',
        'Conclua o login e as permissões do projeto. A assinatura ChatGPT não comprova cota da API.'),
    'claude_chave': ('Anthropic API', 'https://console.anthropic.com/settings/keys',
        'Conclua o login e as permissões da conta Anthropic; a abertura não cria créditos ou uma chave.'),
    'agenda_google': ('Credenciais Google Calendar', 'https://console.cloud.google.com/apis/credentials',
        'Conclua a configuração e o consentimento OAuth da sua conta Google antes de autorizar a agenda.'),
    '9remote_pareamento': ('Pareamento 9Remote', 'http://127.0.0.1:2208/ui/index.html',
        'Conclua o pareamento e as permissões na interface 9Remote. A abertura não inicia uma sessão remota.'),
    'ollama_instalacao': ('Ollama para Windows', 'https://ollama.com/download/windows',
        'Conclua o instalador oficial se a instalação automática não estiver disponível.'),
    'node_instalacao': ('Node.js LTS', 'https://nodejs.org/en/download',
        'Conclua o instalador oficial com npm se a instalação automática não estiver disponível.'),
    'robotask_instalacao': ('RoboTask', 'https://robotask.com/download/',
        'A instalação e as permissões do RoboTask pertencem ao seu instalador oficial.'),
}
_AMBIENTE_PUBLICO = frozenset({
    'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'SYSTEMDRIVE', 'COMSPEC',
    'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA', 'USERPROFILE',
    'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'HOMEDRIVE', 'HOMEPATH',
})
_ABERTAS = set()
_TRAVA = threading.Lock()


def _regular_sem_redirecionamento(arquivo):
    try:
        for parte in (arquivo, *arquivo.parents):
            meta = parte.lstat()
            if (stat.S_ISLNK(meta.st_mode) or
                    bool(getattr(meta, 'st_file_attributes', 0) &
                         getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))):
                return False
        return arquivo.is_file() and arquivo.suffix.casefold() == '.exe'
    except OSError:
        return False


def detectar_robotask():
    """Somente presença de executável; não lê .tsk nem configurações do usuário."""
    candidatos = []
    caminho = shutil.which('RoboTask.exe')
    if caminho:
        candidatos.append(Path(caminho))
    for nome in ('PROGRAMFILES', 'PROGRAMFILES(X86)'):
        base = os.getenv(nome, '')
        if base and Path(base).is_absolute():
            candidatos.append(Path(base) / 'RoboTask' / 'RoboTask.exe')
    encontrado = any(p.is_absolute() and _regular_sem_redirecionamento(p) for p in candidatos)
    return {'executavel_localizado': encontrado, 'macros_auditadas': False,
            'metodo_preparacao': 'script_direto',
            'mensagem': ('RoboTask localizado por metadados; tarefas específicas ainda dependem de auditoria.'
                         if encontrado else 'RoboTask não localizado nos caminhos conferidos; a abertura de telas oficiais usa script direto.')}


def plano_ajudas(servicos):
    """Plano puro, fechado e sem valores secretos para as pendências escolhidas."""
    if (not isinstance(servicos, (list, tuple)) or len(servicos) > len(_ALVOS) or
            any(not isinstance(s, str) or s not in _ALVOS for s in servicos)):
        raise ValueError('Escolha somente as telas de preparação conhecidas.')
    return [{'id': s, 'nome': _ALVOS[s][0], 'url': _ALVOS[s][1],
             'orientacao': _ALVOS[s][2], 'acao_na_conta_pendente': True,
             'conexao_testada': False} for s in dict.fromkeys(servicos)]


def _abridor_windows():
    raiz = os.getenv('SYSTEMROOT') or os.getenv('WINDIR') or ''
    if not raiz or not Path(raiz).is_absolute():
        raise RuntimeError('Diretório do Windows não localizado para abrir as telas oficiais.')
    programa = Path(raiz) / 'System32' / 'rundll32.exe'
    if not _regular_sem_redirecionamento(programa):
        raise RuntimeError('O abridor oficial do Windows não foi localizado em um caminho válido.')
    return programa


def abrir_ajudas(servicos, *, confirmado=False, reabrir=False):
    """Abre cada destino necessário uma vez, com ambiente sem chaves do bot.

    confirmado=True vem do fluxo de preparação solicitado pelo proprietário;
    não adiciona confirmações por provedor. reabrir só é usado num novo pedido
    explícito do usuário. O retorno contém pendências, nunca credenciais.
    """
    if confirmado is not True:
        raise PermissionError('A abertura pertence ao fluxo de preparação autorizado pelo proprietário.')
    if type(reabrir) is not bool:
        raise ValueError('A opção de reabertura deve ser booleana.')
    itens = plano_ajudas(servicos)
    if sys.platform != 'win32':
        raise RuntimeError('A abertura das telas oficiais precisa da sessão Windows local.')
    if not itens:
        return {'itens': [], 'aberturas_solicitadas': 0, 'pendencias_conta': 0}
    programa = _abridor_windows()
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE_PUBLICO}
    resultados = []
    with _TRAVA:
        for item in itens:
            ident = item['id']
            if ident in _ABERTAS and not reabrir:
                resultados.append({**item, 'abertura_solicitada': False,
                    'estado': 'ja_solicitada', 'mensagem': 'Esta tela já foi solicitada nesta preparação; confira o navegador.'})
                continue
            try:
                subprocess.Popen([str(programa), 'url.dll,FileProtocolHandler', item['url']],
                    shell=False, env=ambiente, stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    close_fds=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
            except OSError:
                resultados.append({**item, 'abertura_solicitada': False,
                    'estado': 'abertura_pendente', 'mensagem': 'O Windows não confirmou a abertura; use o endereço oficial indicado.'})
                continue
            _ABERTAS.add(ident)
            resultados.append({**item, 'abertura_solicitada': True,
                'estado': 'aguardando_conta', 'mensagem': 'Abertura solicitada. Conclua somente o login, a autorização ou a entrada de credencial que a página exigir.'})
    return {'itens': resultados,
            'aberturas_solicitadas': sum(r['abertura_solicitada'] for r in resultados),
            'pendencias_conta': len(resultados)}
