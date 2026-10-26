"""Interrompe somente a sonda Telegram publicada para o terminal do proprietário.

Não lê arquivos de configuração, não usa rede e não seleciona processos por nome
ou PID isolado. O código completo do argumento Python -c precisa corresponder à
sonda conhecida; depois, executável, proprietário, criação e HANDLE concordam.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import sys
import time

from controlar_instancia_preparacao import _ProcessoWindows, _igual_caminho, _sem_links

_WINDOWS = sys.platform == 'win32'
_MAX_CODIGO = 8192
_RELATIVOS = {r'.\.venv\Scripts\python.exe'.casefold(), r'.venv\Scripts\python.exe'.casefold()}
_HASH_ORIGINAL = '6cef080b977b9f0fe960a499c604f0f006def9b6e8ffc01f6f09b2a6b0c89fe5'
_SONDA = r'''try:
 import re, requests
 from pathlib import Path
 from configurar_telegram import valores_env, validar_token, validar_ids
 c=valores_env(Path('F:/MeuControlePC_v2/.env'))
 t=c.get('TELEGRAM_TOKEN','')
 ids=c.get('TELEGRAM_ALLOWED_USER_IDS','')
 print('TOKEN_FORMATO='+str(validar_token(t)),flush=True)
 print('DONOS_FORMATO='+str(validar_ids(ids))+'; DONOS_QTD='+str(len(re.findall(r'\d+',ids))),flush=True)
 if validar_token(t):
  for metodo in ('getMe','getWebhookInfo'):
   try:
    r=requests.post('https://api.telegram.org/bot'+t+'/'+metodo,timeout=(3,5),allow_redirects=False)
    print(metodo+'_HTTP='+str(r.status_code),flush=True)
    j=r.json()
    print(metodo+'_OK='+str(j.get('ok') is True),flush=True)
    d=j.get('result',{})
    if metodo=='getMe' and j.get('ok') is True:
     u=d.get('username','')
     print('BOT_USUARIO='+('@'+u if isinstance(u,str) and re.fullmatch(r'[A-Za-z0-9_]{5,32}',u) else 'nao_informado'),flush=True)
    if metodo=='getWebhookInfo' and j.get('ok') is True:
     print('WEBHOOK_ATIVO='+str(bool(d.get('url'))),flush=True)
     p=d.get('pending_update_count')
     if type(p) is int: print('ATUALIZACOES_PENDENTES='+str(p),flush=True)
   except Exception as e:
    print(metodo+'_ERRO='+type(e).__name__,flush=True)
except Exception as e:
 print('DIAGNOSTICO_ERRO='+type(e).__name__,flush=True)
'''


class FalhaEncerrarTeste(RuntimeError):
    """Falha pública que nunca inclui argumentos, chaves ou PIDs."""


class _NormalizarCaminho(ast.NodeTransformer):
    def visit_Call(self, node):
        node = self.generic_visit(node)
        if (isinstance(node.func, ast.Name) and node.func.id == 'Path'
                and len(node.args) == 1 and not node.keywords
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
                and node.args[0].value.replace('\\', '/').casefold() == 'f:/meucontrolepc_v2/.env'):
            node.args[0].value = 'F:/MeuControlePC_v2/.env'
        return node


def _arvore(codigo):
    return ast.dump(_NormalizarCaminho().visit(ast.parse(codigo)), include_attributes=False)


_AST_SONDA = _arvore(_SONDA)


def _codigo_corresponde(codigo):
    """Analisa texto; nunca executa o código encontrado em outro processo."""
    if not isinstance(codigo, str) or not 1 <= len(codigo) <= _MAX_CODIGO:
        return False
    if hashlib.sha256(codigo.encode('utf-8')).hexdigest() == _HASH_ORIGINAL:
        return True
    try:
        arvore = ast.parse(codigo)
        if len(arvore.body) != 1 or not isinstance(arvore.body[0], ast.Expr):
            return False
        chamada = arvore.body[0].value
        if (not isinstance(chamada, ast.Call) or not isinstance(chamada.func, ast.Name)
                or chamada.func.id != 'exec' or len(chamada.args) != 1 or chamada.keywords
                or not isinstance(chamada.args[0], ast.Constant)
                or not isinstance(chamada.args[0].value, str)):
            return False
        return _arvore(chamada.args[0].value) == _AST_SONDA
    except (SyntaxError, ValueError, TypeError, RecursionError, MemoryError):
        return False


def _python_atual():
    caminho = Path(sys.executable)
    if not caminho.is_absolute() or caminho.name.casefold() != 'python.exe':
        raise FalhaEncerrarTeste('Use o Python do assistente no Windows para identificar a sonda.')
    _sem_links(caminho)
    if not caminho.is_file():
        raise FalhaEncerrarTeste('O executável Python selecionado não pôde ser confirmado.')
    return caminho.resolve()


def _psutil():
    try:
        import psutil
    except ImportError:
        raise FalhaEncerrarTeste('Use o Python .venv do assistente, que contém psutil.') from None
    return psutil


def _argumentos_exatos(argv, python, cwd=None):
    if (not isinstance(argv, (list, tuple)) or len(argv) != 3
            or not all(isinstance(x, str) for x in argv)
            or argv[1] != '-c' or not _codigo_corresponde(argv[2])):
        return False
    if Path(argv[0]).is_absolute():
        return _igual_caminho(argv[0], python)
    if argv[0].casefold() not in _RELATIVOS or not isinstance(cwd, str) or not Path(cwd).is_absolute():
        return False
    base = Path(cwd)
    caminho = base.joinpath(*PureWindowsPath(argv[0]).parts)
    _sem_links(base)
    _sem_links(caminho)
    return _igual_caminho(caminho, python)


def _metadados(processo):
    argv = tuple(processo.cmdline())
    cwd = processo.cwd() if argv and isinstance(argv[0], str) and argv[0].casefold() in _RELATIVOS else None
    return {'pid': processo.pid, 'exe': processo.exe(), 'argv': argv,
            'criado': processo.create_time(), 'cwd': cwd}


def _listar(psutil, python):
    candidatos = []
    for processo in psutil.process_iter():
        try:
            if processo.name().casefold() != 'python.exe':
                continue
            exe = processo.exe()
            if not isinstance(exe, str) or not Path(exe).is_absolute() or not _igual_caminho(exe, python):
                continue
            argv = processo.cmdline()
            cwd = processo.cwd() if argv and isinstance(argv[0], str) and argv[0].casefold() in _RELATIVOS else None
            if not _argumentos_exatos(argv, python, cwd):
                continue
            info = _metadados(processo)
            if (type(info['pid']) is not int or not 0 < info['pid'] <= 0xFFFFFFFF
                    or isinstance(info['criado'], bool) or not isinstance(info['criado'], (int, float))
                    or not math.isfinite(info['criado']) or info['criado'] <= 0
                    or not _igual_caminho(info['exe'], python)
                    or tuple(argv) != info['argv'] or cwd != info['cwd']):
                raise FalhaEncerrarTeste('A identidade da sonda mudou durante a consulta.')
            candidatos.append(info)
        except psutil.NoSuchProcess:
            continue
        except psutil.AccessDenied:
            raise FalhaEncerrarTeste('O Windows não permitiu conferir um processo; nenhuma nova parada foi enviada.') from None
    if len(candidatos) > 8 or len({x['pid'] for x in candidatos}) != len(candidatos):
        raise FalhaEncerrarTeste('A lista de sondas não pôde ser confirmada com segurança.')
    return sorted(candidatos, key=lambda info: info['pid'])


def _identidade_valida(info, snapshot, python):
    if (not isinstance(info, dict)
            or set(info) != {'pid', 'exe', 'criado', 'owner_sid', 'atual_sid'}
            or type(info['pid']) is not int or info['pid'] != snapshot['pid']
            or not isinstance(info['exe'], str) or not Path(info['exe']).is_absolute()
            or not _igual_caminho(info['exe'], python)
            or not isinstance(info['criado'], str) or not re.fullmatch(r'[1-9][0-9]{5,19}', info['criado'])
            or not isinstance(info['owner_sid'], str) or not re.fullmatch(r'S-1-[0-9-]{3,180}', info['owner_sid'])
            or info['owner_sid'] != info['atual_sid']):
        return False
    # psutil expõe segundos em float; o HANDLE preserva o FILETIME integral.
    segundos = (int(info['criado']) - 116444736000000000) / 10_000_000
    return math.isclose(segundos, snapshot['criado'], rel_tol=0, abs_tol=0.000005)


def _fechar(alvos):
    for alvo in alvos:
        try:
            alvo['handle'].close()
        except (OSError, ValueError):
            pass


def _revalidar_alvo(psutil, alvo):
    handle = alvo['handle']
    if (handle.identidade() != alvo['identidade'] or handle.aguardar(0)
            or _metadados(psutil.Process(alvo['info']['pid'])) != alvo['info']
            or handle.identidade() != alvo['identidade']):
        raise FalhaEncerrarTeste('A sonda mudou durante a verificação; nenhuma nova parada foi enviada.')


def encerrar_teste(*, confirmado=False, timeout=10):
    if confirmado is not True:
        raise PermissionError('A interrupção da sonda exige a opção --confirmar.')
    if not _WINDOWS:
        raise FalhaEncerrarTeste('A interrupção da sonda é exclusiva do Windows.')
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 1 <= timeout <= 10):
        raise ValueError('O prazo total deve ficar entre um e dez segundos.')
    python = _python_atual()
    psutil = _psutil()
    limite = time.monotonic() + timeout
    alvos = []
    encerrados = 0
    try:
        candidatos = _listar(psutil, python)
        for info in candidatos:
            if time.monotonic() >= limite:
                raise FalhaEncerrarTeste('O prazo de identificação terminou; nenhuma parada foi enviada.')
            handle = _ProcessoWindows(info['pid'])
            alvo = {'info': info, 'handle': handle}
            alvos.append(alvo)
            identidade = handle.identidade()
            if not _identidade_valida(identidade, info, python):
                raise FalhaEncerrarTeste('O proprietário ou a criação da sonda não pôde ser confirmado.')
            alvo['identidade'] = identidade
            _revalidar_alvo(psutil, alvo)
        if _listar(psutil, python) != candidatos:
            raise FalhaEncerrarTeste('A lista de sondas mudou; nenhuma parada foi enviada.')
        # Todos os HANDLEs já estão abertos antes da primeira interrupção.
        for alvo in alvos:
            _revalidar_alvo(psutil, alvo)
        for alvo in alvos:
            restante = limite - time.monotonic()
            if restante <= 0:
                raise FalhaEncerrarTeste('O prazo terminou; nenhuma nova parada foi enviada.')
            _revalidar_alvo(psutil, alvo)
            restante = limite - time.monotonic()
            if restante <= 0:
                raise FalhaEncerrarTeste('O prazo terminou; nenhuma nova parada foi enviada.')
            alvo['handle'].parar()
            restante = max(0, limite - time.monotonic())
            if not alvo['handle'].aguardar(min(5, restante)):
                raise FalhaEncerrarTeste('A parada da sonda não foi confirmada; nenhuma segunda tentativa foi enviada.')
            encerrados += 1
        return {'estado': 'encerrado' if encerrados else 'nenhuma_sonda_identificada',
                'sondas_encerradas': encerrados}
    except FalhaEncerrarTeste:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, psutil.Error):
        raise FalhaEncerrarTeste('Não foi possível confirmar a sonda; outros programas foram preservados.') from None
    finally:
        _fechar(alvos)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Interrompe apenas a consulta Telegram conhecida e identificada.')
    parser.add_argument('--confirmar', action='store_true')
    args = parser.parse_args(argv)
    try:
        resultado = encerrar_teste(confirmado=args.confirmar)
    except (FalhaEncerrarTeste, PermissionError, ValueError):
        print('ENCERRAR_TESTE=NAO_CONFIRMADO; outros programas foram preservados.')
        return 1
    except (OSError, RuntimeError, TypeError, KeyError):
        print('ENCERRAR_TESTE=NAO_CONFIRMADO; verificação local indisponível.')
        return 1
    print(json.dumps(resultado, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
