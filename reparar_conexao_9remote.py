"""Aplica o reparo local do 9Remote somente à instalação gerenciada.

Não lê credenciais nem a configuração do assistente. Antes de trocar os bundles,
identifica todos os hosts permitidos e mantém HANDLEs nativos até confirmar sua
parada. Outros programas Node, outras instalações e outros usuários são mantidos.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

import correcao_dns_9remote as correcao
from controlar_instancia_preparacao import _ProcessoWindows, _igual_caminho, _sem_links

_WINDOWS = sys.platform == 'win32'
PORTA = 2208
PAINEL = 'http://127.0.0.1:2208/ui/index.html'
_AMBIENTE = {'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC',
    'SYSTEMDRIVE', 'USERPROFILE', 'HOMEDRIVE', 'HOMEPATH', 'APPDATA',
    'LOCALAPPDATA', 'PROGRAMFILES', 'PROGRAMFILES(X86)', 'PROGRAMDATA',
    'TEMP', 'TMP', 'USERNAME', 'USERDOMAIN', 'OS', 'PROCESSOR_ARCHITECTURE',
    'NUMBER_OF_PROCESSORS', 'LANG', 'LC_ALL', 'TERM', 'COLORTERM'}


class FalhaReparo(RuntimeError):
    """Mensagem pública, sem argumentos dos processos nem detalhes privados."""


def _ambiente():
    return {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE}


def _pacote():
    local = os.environ.get('LOCALAPPDATA', '')
    if not local or not Path(local).is_absolute():
        raise FalhaReparo('A pasta LOCALAPPDATA do Windows não foi localizada.')
    pacote = Path(local) / 'MeuControlePC' / 'integracoes' / '9remote' / 'node_modules' / '9remote'
    _sem_links(pacote)
    return pacote


def _node(ambiente):
    path = next((v for k, v in ambiente.items() if k.upper() == 'PATH'), '')
    localizado = shutil.which('node.exe', path=path)
    if not localizado:
        raise FalhaReparo('Node.js não foi localizado no PATH; reabra o terminal após instalá-lo.')
    node = Path(localizado)
    if not node.is_absolute() or node.name.casefold() != 'node.exe':
        raise FalhaReparo('O reparo requer o executável node.exe instalado no Windows.')
    _sem_links(node)
    if not node.is_file():
        raise FalhaReparo('O executável do Node.js não pôde ser confirmado.')
    node = node.resolve()
    try:
        resultado = subprocess.run([str(node), '--version'], cwd=str(node.parent),
            env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, check=False, timeout=5,
            text=True, encoding='utf-8', errors='strict',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise FalhaReparo('Não foi possível conferir a versão do Node.js em cinco segundos.') from None
    versao = re.fullmatch(r'v([0-9]{1,3})\.[0-9]{1,5}\.[0-9]{1,5}', resultado.stdout.strip())
    if resultado.returncode or not versao or int(versao[1]) < 22:
        raise FalhaReparo('O reparo requer Node.js 22 ou mais recente.')
    return node


def _psutil():
    try:
        import psutil
    except ImportError:
        raise FalhaReparo('Execute o reparo pelo Python .venv do assistente, que contém psutil.') from None
    return psutil


def _tipo_argumentos(argv, node, pacote):
    if (not isinstance(argv, (list, tuple)) or len(argv) < 2
            or not all(isinstance(x, str) for x in argv)):
        return None
    if not Path(argv[0]).is_absolute() or not _igual_caminho(argv[0], node):
        return None
    if not Path(argv[1]).is_absolute():
        return None
    cli, servidor = pacote / 'dist' / 'cli.cjs', pacote / 'dist' / 'server.cjs'
    if _igual_caminho(argv[1], servidor):
        if len(argv) != 2:
            raise FalhaReparo('O servidor 9Remote usa argumentos inesperados; nenhum processo foi encerrado.')
        return 'servidor'
    if _igual_caminho(argv[1], cli):
        if tuple(argv[2:]) not in (('ui',), ('ui', '--start'), ('start',)):
            raise FalhaReparo('O iniciador 9Remote usa argumentos inesperados; nenhum processo foi encerrado.')
        return 'cli'
    return None


def _metadados(processo):
    return {'pid': processo.pid, 'exe': processo.exe(),
            'argv': tuple(processo.cmdline()), 'criado': processo.create_time()}


def _listar_metadados(psutil, node, pacote):
    encontrados = []
    for processo in psutil.process_iter():
        try:
            if processo.name().casefold() != 'node.exe':
                continue
            exe = processo.exe()
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            raise FalhaReparo('O Windows não permitiu identificar um processo Node; nenhuma parada foi enviada.') from None
        if not isinstance(exe, str) or not Path(exe).is_absolute():
            raise FalhaReparo('Um executável Node não pôde ser identificado com segurança.')
        if not _igual_caminho(exe, node):
            continue
        try:
            info = {'pid': processo.pid, 'exe': exe,
                    'argv': tuple(processo.cmdline()), 'criado': processo.create_time()}
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            raise FalhaReparo('Os argumentos de um processo Node não puderam ser confirmados; nenhuma parada foi enviada.') from None
        tipo = _tipo_argumentos(info['argv'], node, pacote)
        if tipo is None:
            continue
        if (type(info['pid']) is not int or not 0 < info['pid'] <= 0xFFFFFFFF
                or info['pid'] == os.getpid() or isinstance(info['criado'], bool)
                or not isinstance(info['criado'], (int, float))
                or not math.isfinite(info['criado']) or info['criado'] <= 0):
            raise FalhaReparo('A identidade de um host 9Remote não pôde ser confirmada.')
        encontrados.append({**info, 'tipo': tipo})
    if len({x['pid'] for x in encontrados}) != len(encontrados):
        raise FalhaReparo('A lista de processos mudou durante a identificação.')
    return encontrados


def _identidade_valida(info, pid, node):
    return (isinstance(info, dict)
        and set(info) == {'pid', 'exe', 'criado', 'owner_sid', 'atual_sid'}
        and type(info['pid']) is int and info['pid'] == pid
        and isinstance(info['exe'], str) and Path(info['exe']).is_absolute()
        and _igual_caminho(info['exe'], node)
        and isinstance(info['criado'], str) and bool(re.fullmatch(r'[1-9][0-9]{5,19}', info['criado']))
        and isinstance(info['owner_sid'], str)
        and bool(re.fullmatch(r'S-1-[0-9-]{3,180}', info['owner_sid']))
        and info['owner_sid'] == info['atual_sid'])


def _fechar(alvos):
    for alvo in alvos:
        try:
            alvo['handle'].close()
        except (OSError, ValueError):
            pass


def _capturar(psutil, node, pacote):
    alvos = []
    try:
        for info in _listar_metadados(psutil, node, pacote):
            handle = _ProcessoWindows(info['pid'])
            alvo = {'info': info, 'handle': handle}
            alvos.append(alvo)
            identidade = handle.identidade()
            if not _identidade_valida(identidade, info['pid'], node):
                raise FalhaReparo('O proprietário ou executável de um host 9Remote não foi confirmado.')
            # O HANDLE fica aberto antes da nova leitura. Seu PID não pode ser
            # reciclado para outro processo enquanto essa referência existir.
            atual = _metadados(psutil.Process(info['pid']))
            if atual != {k: v for k, v in info.items() if k != 'tipo'}:
                raise FalhaReparo('Um processo mudou durante a identificação; nenhuma parada foi enviada.')
            if handle.aguardar(0):
                raise FalhaReparo('Um host 9Remote terminou durante a identificação; tente o reparo novamente.')
            alvo['identidade'] = identidade
        return alvos
    except BaseException:
        _fechar(alvos)
        raise


def _donos_porta(psutil):
    donos = set()
    for conexao in psutil.net_connections(kind='tcp'):
        endereco = conexao.laddr
        if not endereco or conexao.status != psutil.CONN_LISTEN:
            continue
        porta = endereco.port if hasattr(endereco, 'port') else endereco[1]
        if porta != PORTA:
            continue
        if type(conexao.pid) is not int or conexao.pid <= 0:
            raise FalhaReparo('O dono da porta 2208 não pôde ser identificado; nenhum processo será selecionado.')
        donos.add(conexao.pid)
    return donos


def _revalidar(psutil, node, pacote, alvos):
    anteriores = {a['info']['pid']: a['info'] for a in alvos}
    atuais = {a['pid']: a for a in _listar_metadados(psutil, node, pacote)}
    if atuais != anteriores:
        raise FalhaReparo('A lista de hosts 9Remote mudou; nenhuma nova parada foi enviada.')
    for alvo in alvos:
        if alvo['handle'].identidade() != alvo['identidade'] or alvo['handle'].aguardar(0):
            raise FalhaReparo('Um host 9Remote mudou durante a verificação; nenhuma nova parada foi enviada.')
    if not _donos_porta(psutil).issubset(anteriores):
        raise FalhaReparo('Outro processo ocupa a porta 2208; ele foi preservado e o reparo não prosseguiu.')


def _conferir_porta_livre(psutil):
    if _donos_porta(psutil):
        raise FalhaReparo('A porta 2208 continua ocupada; os arquivos não serão substituídos.')
    sockets = []
    try:
        for familia, endereco in ((socket.AF_INET, '127.0.0.1'), (socket.AF_INET6, '::1')):
            s = socket.socket(familia, socket.SOCK_STREAM)
            sockets.append(s)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            if familia == socket.AF_INET6:
                s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
            s.bind((endereco, PORTA))
    except (AttributeError, OSError):
        raise FalhaReparo('A liberação da porta local 2208 não pôde ser confirmada; o reparo foi interrompido.') from None
    finally:
        for s in sockets:
            s.close()


def parar_host(node, pacote, *, timeout=12):
    """Encerra apenas os HANDLEs identificados, nunca por nome ou arquivo PID."""
    if not _WINDOWS:
        raise FalhaReparo('O reparo do host é exclusivo do Windows.')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 1 <= timeout <= 30):
        raise ValueError('O prazo deve ficar entre um e trinta segundos.')
    psutil = _psutil()
    limite = time.monotonic() + timeout
    alvos = []
    encerrados = 0
    try:
        alvos = _capturar(psutil, node, pacote)
        _revalidar(psutil, node, pacote, alvos)
        # Matar o controlador primeiro impede sua política de reinício de
        # recriar o filho depois que o servidor já tiver sido encerrado.
        for alvo in sorted(alvos, key=lambda a: a['info']['tipo'] != 'cli'):
            restante = limite - time.monotonic()
            if restante <= 0:
                raise FalhaReparo('O prazo de parada terminou; o reparo não substituiu os arquivos.')
            if alvo['handle'].identidade() != alvo['identidade']:
                raise FalhaReparo('A identidade do host mudou; nenhuma nova parada foi enviada.')
            alvo['handle'].parar()
            if not alvo['handle'].aguardar(restante):
                raise FalhaReparo('A parada do host não foi confirmada; nenhuma segunda parada será enviada.')
            encerrados += 1
        if _listar_metadados(psutil, node, pacote):
            raise FalhaReparo('Outro host 9Remote apareceu durante a parada; ele foi preservado.')
        _conferir_porta_livre(psutil)
        return encerrados
    except FalhaReparo:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, psutil.Error):
        raise FalhaReparo('Não foi possível confirmar a parada do 9Remote; nenhum outro processo foi selecionado.') from None
    finally:
        _fechar(alvos)


def _saude_local():
    class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), SemRedirecionamento())
    try:
        with opener.open('http://127.0.0.1:2208/api/health', timeout=1) as resposta:
            return resposta.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _host_lancado_identificado(processo, node, pacote):
    psutil = _psutil()
    alvos = []
    try:
        alvos = _capturar(psutil, node, pacote)
        _revalidar(psutil, node, pacote, alvos)
        if not any(a['info']['pid'] == processo.pid and a['info']['tipo'] == 'cli' for a in alvos):
            return False
        servidores = {a['info']['pid'] for a in alvos if a['info']['tipo'] == 'servidor'}
        donos = _donos_porta(psutil)
        return bool(donos) and donos.issubset(servidores)
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, psutil.Error):
        return False
    finally:
        _fechar(alvos)


def _iniciar_host(node, pacote, ambiente, *, timeout=20):
    try:
        processo = subprocess.Popen([str(node), str(pacote / 'dist' / 'cli.cjs'), 'ui', '--start'],
            cwd=str(pacote.parents[1]), env=ambiente, shell=False, close_fds=True,
            creationflags=getattr(subprocess, 'CREATE_NEW_CONSOLE', 0x10))
    except OSError:
        raise FalhaReparo('A correção foi aplicada, mas o Windows não abriu a janela do 9Remote.') from None
    limite = time.monotonic() + timeout
    while time.monotonic() < limite:
        if processo.poll() is not None:
            raise FalhaReparo('A correção foi aplicada, mas o iniciador do 9Remote terminou antes de abrir o painel.')
        if _saude_local():
            if not _host_lancado_identificado(processo, node, pacote):
                raise FalhaReparo('O painel respondeu, mas a identidade do novo host não foi confirmada.')
            webbrowser.open(PAINEL, new=2)
            return
        time.sleep(.2)
    raise FalhaReparo('A correção foi aplicada; o painel do 9Remote não respondeu no prazo de vinte segundos.')


def reparar_conexao(*, aplicar=False, iniciar=False, reverter=False):
    """Planeja sem alterações; as flags explícitas autorizam reparo e início."""
    if not _WINDOWS:
        raise FalhaReparo('Execute este reparo no Windows onde o 9Remote foi instalado.')
    if any(type(v) is not bool for v in (aplicar, iniciar, reverter)):
        raise ValueError('As opções do reparo devem ser booleanas.')
    if reverter and (aplicar or iniciar) or iniciar and not aplicar:
        raise ValueError('Use --aplicar --iniciar ou --reverter separadamente.')
    with correcao.manutencao():
        return _reparar_serializado(aplicar=aplicar, iniciar=iniciar, reverter=reverter)


def _reparar_serializado(*, aplicar, iniciar, reverter):
    pacote = _pacote()
    plano = correcao.planejar_correcao(pacote)
    if not aplicar and not reverter:
        return {**plano, 'iniciado': False, 'processos_encerrados': 0}
    ambiente = _ambiente()
    node = _node(ambiente)
    encerrados = parar_host(node, pacote)
    resultado = (correcao.reverter_correcao(pacote) if reverter
                 else correcao.aplicar_correcao(pacote))
    if iniciar:
        _iniciar_host(node, pacote, ambiente)
    return {**resultado, 'iniciado': iniciar, 'processos_encerrados': encerrados,
            'painel': PAINEL if iniciar else None}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Reparo local e reversível da conexão do 9Remote gerenciado.')
    parser.add_argument('--aplicar', action='store_true')
    parser.add_argument('--iniciar', action='store_true')
    parser.add_argument('--reverter', action='store_true')
    opcoes = parser.parse_args(argv)
    try:
        resultado = reparar_conexao(**vars(opcoes))
    except (FalhaReparo, correcao.FalhaCorrecao, ValueError) as erro:
        print(str(erro))
        return 1
    except (OSError, RuntimeError, TypeError, KeyError):
        print('O reparo não pôde ser concluído. Nenhuma chave ou configuração de rede foi alterada.')
        return 1
    print(json.dumps(resultado, ensure_ascii=False))
    if resultado['iniciado']:
        print('Painel local aberto. A conexão remota e o pareamento devem ser conferidos no próprio 9Remote.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
