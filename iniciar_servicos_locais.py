"""Inicia somente o Ollama instalado quando o endpoint de loopback está ausente.

Uma tentativa de criação e leituras finitas de metadados. Não baixa modelos,
encerra processos, altera arquivos do serviço ou consulta credenciais.
"""
from __future__ import annotations

import os
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit

from caminhos_instalacao import arquivo_env
from diagnostico_ollama import consultar, validar_url, URL_PADRAO

BASE = Path(__file__).resolve().parent
_WINDOWS = sys.platform == 'win32'
PRAZO_INICIO = 15
MAX_CONSULTAS = 5
PRAZO_DIAGNOSTICO_PORTA = 4
LIMITE_DIAGNOSTICO_PORTA = 8192
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
    if any(k.upper() == 'OLLAMA_NO_CLOUD' and v.lower() in ('1', 'true')
           for k, v in os.environ.items()):
        ambiente['OLLAMA_NO_CLOUD'] = '1'
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


def _vinculo_exclusivo_disponivel(partes):
    """Confirma a disponibilidade local após um connect Windows inconclusivo.

    O socket é temporário e não escuta nem aceita conexões. Exclusividade é
    obrigatória: sem ela ou se bind falhar, a porta continua indeterminada.
    A prova é uma amostra; o processo Ollama ainda precisa conseguir iniciar
    e responder. Nenhum processo existente é encerrado ou reaproveitado aqui.
    """
    exclusivo=getattr(socket,'SO_EXCLUSIVEADDRUSE',None)
    if not _WINDOWS or exclusivo is None:return False
    familia=socket.AF_INET6 if ':' in partes.hostname else socket.AF_INET
    try:
        with socket.socket(familia,socket.SOCK_STREAM,socket.IPPROTO_TCP) as prova:
            prova.setsockopt(socket.SOL_SOCKET,exclusivo,1)
            if familia==socket.AF_INET6:
                prova.setsockopt(socket.IPPROTO_IPV6,socket.IPV6_V6ONLY,1)
            prova.bind((partes.hostname,partes.port))
            return True
    except OSError:return False


def _porta_ocupada(url):
    partes=urlsplit(validar_url(url))
    try:
        with socket.create_connection((partes.hostname,partes.port),timeout=0.3):return True
    except ConnectionRefusedError:return False
    except OSError:
        # Um connect de 0,3 s pode expirar antes da recusa TCP no Windows,
        # mesmo sem escuta. Só um bind exclusivo bem-sucedido permite tratar
        # essa amostra como disponível; não inferir isso de um timeout ou de
        # uma lista de processos vazia.
        return not _vinculo_exclusivo_disponivel(partes)


def _diagnostico_porta(estado, porta, mensagem, acao, processos=None, api_responde=None):
    return {'estado': estado, 'porta': porta, 'api_responde': api_responde,
            'processos': processos or [], 'mensagem': mensagem,
            'acao_recomendada': acao, 'reparo_automatico': False}


def _processos_da_porta(url):
    """Lê só PID/nome dos listeners locais; nunca argumentos ou caminhos.

    O PowerShell e o script são fixos. Somente porta/IP já validados entram
    como literais, e a saída não é devolvida sem validar seu esquema.
    """
    raiz = os.environ.get('SystemRoot', os.environ.get('SYSTEMROOT', r'C:\Windows'))
    executavel = Path(raiz) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    if not executavel.is_absolute() or not executavel.is_file():
        raise OSError('Diagnóstico do Windows indisponível.')
    partes = urlsplit(url)
    porta = partes.port
    host = partes.hostname
    script = (
        "$ErrorActionPreference='Stop';"
        "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
        "$OutputEncoding=[Console]::OutputEncoding;"
        "$conexoes=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | "
        "Where-Object {$_.LocalPort -eq " + str(porta) +
        " -and $_.LocalAddress -in @('0.0.0.0','::','" + host + "')} | Select-Object -First 9);"
        "$linhas=@(foreach($conexao in $conexoes){"
        "$dono=[int]$conexao.OwningProcess;$nome=$null;"
        "try{$nome=(Get-Process -Id $dono -ErrorAction Stop).ProcessName}catch{};"
        "[pscustomobject]@{pid=$dono;nome=$nome}});"
        "@{listeners=$linhas}|ConvertTo-Json -Compress -Depth 3"
    )
    resultado = subprocess.run(
        [str(executavel), '-NoProfile', '-NonInteractive', '-Command', script],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding='utf-8', errors='replace', shell=False, check=False,
        timeout=PRAZO_DIAGNOSTICO_PORTA,
        env=_ambiente_servidor(url),
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
    if resultado.returncode != 0 or not isinstance(resultado.stdout, str):
        raise ValueError('Não foi possível identificar a escuta local.')
    if len(resultado.stdout.encode('utf-8')) > LIMITE_DIAGNOSTICO_PORTA:
        raise ValueError('Diagnóstico excedeu o limite local.')
    dados = json.loads(resultado.stdout)
    if (not isinstance(dados, dict) or set(dados) != {'listeners'}
            or not isinstance(dados['listeners'], list) or len(dados['listeners']) > 8):
        raise ValueError('Diagnóstico não reconhecido.')
    reconhecidos = {'ollama', 'ollama app', 'ollama_llama_server', 'llama-server',
                    'node', 'python', 'pythonw', 'svchost', 'system', 'wslhost',
                    'wslrelay', 'com.docker.backend', 'docker-proxy', 'powershell', 'pwsh'}
    nomes_ollama = {'ollama', 'ollama app', 'ollama_llama_server', 'llama-server'}
    processos = {}
    for item in dados['listeners']:
        if (not isinstance(item, dict) or set(item) != {'pid', 'nome'}
                or type(item['pid']) is not int or not 1 <= item['pid'] <= 4294967295
                or item['nome'] is not None and not isinstance(item['nome'], str)):
            raise ValueError('Processo não reconhecido.')
        nome = (item['nome'] or '').casefold().removesuffix('.exe')
        # Um nome de processo arbitrário também pode conter informação privada.
        # Mostrar o PID e um rótulo genérico é suficiente quando não conhecido.
        rotulo = (nome + '.exe') if nome in reconhecidos else 'outro processo'
        tipo = ('ollama' if nome in nomes_ollama else 'outro' if nome else 'nao_identificado')
        processos[item['pid']] = {'pid': item['pid'], 'nome': rotulo, 'tipo': tipo}
    return sorted(processos.values(), key=lambda item: item['pid'])


def diagnosticar_porta_ollama(url=None, *, sondar_api=True):
    """Diagnóstico finito, sem iniciar/encerrar processos ou mudar configuração.

    A API é consultada no máximo uma vez e o dono da porta é lido no Windows
    em até quatro segundos. O resultado contém somente rótulos públicos e PID;
    nunca stdout bruto, commandline, executável completo ou valores de ambiente.
    Uma identificação do Ollama não autoriza encerrá-lo: pode haver geração.
    """
    if type(sondar_api) is not bool:
        raise ValueError('A sondagem da API deve ser booleana.')
    try:
        url = validar_url(os.getenv('OLLAMA_URL', URL_PADRAO) if url is None else url)
    except ValueError:
        return _diagnostico_porta('endereco_invalido', None,
            'Endereço Ollama inválido; selecione somente IP de loopback.', 'corrigir_endpoint')
    porta = urlsplit(url).port
    if not _WINDOWS:
        return _diagnostico_porta('plataforma_nao_suportada', porta,
            'A identificação do processo da porta está disponível na sessão Windows do PC.',
            'conferir_no_windows')
    api_responde = None
    if sondar_api:
        try: api_responde = _responde(url, 3)
        except (OSError, ValueError): api_responde = False
        if api_responde:
            return _diagnostico_porta('api_pronta', porta,
                'A API Ollama responde aos metadados locais; geração ainda não verificada.',
                'nenhuma', api_responde=True)
    try:
        processos = _processos_da_porta(url)
    except (OSError, ValueError, subprocess.SubprocessError):
        return _diagnostico_porta('indeterminada', porta,
            'Não foi possível identificar o dono da porta local no prazo da verificação. '
            'A porta não foi considerada livre e nenhum processo foi alterado.',
            'conferir_porta_no_windows', api_responde=api_responde)
    if not processos:
        return _diagnostico_porta('sem_escuta_identificada', porta,
            'Nenhuma escuta local foi identificada na porta '+str(porta)+' nesta amostra. '
            'A verificação não iniciou nem encerrou programas.',
            'iniciar_se_autorizado', api_responde=api_responde)
    tipos = {p['tipo'] for p in processos}
    resumo = ', '.join(p['nome']+' (PID '+str(p['pid'])+')' for p in processos)
    if tipos == {'ollama'}:
        return _diagnostico_porta('ocupada_ollama', porta,
            'Processo Ollama identificado na porta '+str(porta)+': '+resumo+'. '
            'Confira a janela do serviço ou aguarde a operação em andamento antes de decidir reiniciá-lo.',
            'conferir_ollama_existente', processos, api_responde)
    if tipos == {'nao_identificado'}:
        estado, acao = 'ocupada_nao_identificada', 'conferir_porta_no_windows'
    else:
        estado, acao = 'ocupada_outro', 'conferir_conflito_de_porta'
    return _diagnostico_porta(estado, porta,
        'Escuta identificada na porta '+str(porta)+': '+resumo+'. '
        'Confira o dono da porta e o endpoint selecionado; nenhum processo foi encerrado.',
        acao, processos, api_responde)


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
        if os.getenv('OLLAMA_INICIAR_SERVICO','1')!='1':
            return _resultado(False,False,'O início do servidor Ollama está desativado. Abra-o manualmente quando precisar; os recursos locais do assistente continuam disponíveis.')
        if _porta_ocupada(url):
            detalhe=diagnosticar_porta_ollama(url,sondar_api=False)
            return _resultado(False,False,'A API Ollama não respondeu e a porta não pôde ser confirmada livre. '+detalhe['mensagem']+
                ' Nenhum segundo servidor foi iniciado.')
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
