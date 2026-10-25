"""Encerra somente a instância identificada do próprio assistente no Windows.

Não aceita comandos, nomes de processos ou PIDs fornecidos pela interface.
A autorização vem do instalador local. A trava existente, executável, argumentos,
proprietário e criação do processo precisam concordar antes de qualquer parada.
Nada é apagado; a trava não é removida. Sem prova, devolve uma pendência.
"""
from __future__ import annotations

import ctypes
import errno
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

import instancia_assistente as instancia

_WINDOWS = sys.platform == 'win32'
_MAX_SAIDA = 16384
_SCRIPT_METADADOS = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false)
$pedido=([Console]::In.ReadToEnd() | ConvertFrom-Json)
$alvo=[uint32]$pedido.pid
$p=Get-CimInstance Win32_Process -Filter ('ProcessId='+[string]$alvo)
if ($null -eq $p) { '{}' ; exit 0 }
$o=Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid
if ($o.ReturnValue -ne 0) { throw 'owner unavailable' }
@{pid=[uint32]$p.ProcessId; exe=[string]$p.ExecutablePath;
  comando=[string]$p.CommandLine; criado=[string]$p.CreationDate.ToUniversalTime().ToFileTimeUtc();
  owner_sid=[string]$o.Sid;
  atual_sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value} |
  ConvertTo-Json -Compress
'''


def _resultado(estado, mensagem, *, parado=False, livre=False, pid=None):
    saida = {'estado': estado, 'parado': parado, 'livre': livre,
             'pendente': not livre, 'mensagem': mensagem}
    if pid is not None: saida['pid'] = pid
    return saida


def _sem_links(caminho):
    for parte in (caminho, *caminho.parents):
        try: meta = parte.lstat()
        except FileNotFoundError: continue
        if (stat.S_ISLNK(meta.st_mode) or bool(getattr(meta, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))):
            raise ValueError('O caminho da instalação não pode conter redirecionamentos.')


def _caminho(valor):
    p = Path(valor)
    if not p.is_absolute(): raise ValueError('Selecione caminhos absolutos da instalação.')
    _sem_links(p)
    return p.resolve()


def _inspecionar_trava(dados):
    caminho = dados / instancia.NOME_TRAVA
    _sem_links(caminho)
    try: meta = caminho.lstat()
    except FileNotFoundError: return {'ativa': False}
    if not stat.S_ISREG(meta.st_mode) or meta.st_size > 64:
        raise ValueError('Trava de instância inválida; nenhum processo será encerrado.')
    with caminho.open('r+b') as arquivo:
        try:
            instancia._bloquear(arquivo)
        except OSError as erro:
            if erro.errno not in (errno.EACCES, errno.EAGAIN) or getattr(erro, 'winerror', None) not in (None, 33):
                raise ValueError('Não foi possível confirmar o bloqueio da instância.') from None
        else:
            instancia._desbloquear(arquivo)
            return {'ativa': False}
        arquivo.seek(0)
        bruto = arquivo.read(65)
        if not re.fullmatch(rb'\x00[1-9][0-9]{0,9}', bruto):
            raise ValueError('A trava ocupada não identifica uma instância válida.')
        pid = int(bruto[1:])
        if pid > 0xFFFFFFFF or pid == os.getpid():
            raise ValueError('A trava não identifica outro processo permitido.')
        atual = os.fstat(arquivo.fileno())
        assinatura = (atual.st_dev, atual.st_ino, atual.st_mtime_ns, atual.st_size)
        return {'ativa': True, 'pid': pid, 'assinatura': assinatura}


def _metadados_windows(pid, timeout):
    raiz = Path(os.environ.get('SYSTEMROOT', r'C:\Windows'))
    ps = raiz / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    if not raiz.is_absolute() or not ps.is_file(): raise RuntimeError('Metadados Windows indisponíveis.')
    permitidas = {'SYSTEMROOT','WINDIR','PATH','PATHEXT','TEMP','TMP','USERPROFILE',
                  'SYSTEMDRIVE','PROGRAMDATA','APPDATA','LOCALAPPDATA'}
    ambiente = {k:v for k,v in os.environ.items() if k.upper() in permitidas}
    retorno = subprocess.run([str(ps), '-NoProfile', '-NonInteractive', '-Command', _SCRIPT_METADADOS],
        input=json.dumps({'pid':pid}), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='strict', shell=False, check=False,
        timeout=timeout, env=ambiente, creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0x08000000))
    if retorno.returncode or len(retorno.stdout.encode('utf-8')) > _MAX_SAIDA:
        raise RuntimeError('Não foi possível identificar a instância pelo Windows.')
    info = json.loads(retorno.stdout.strip() or '{}')
    if not isinstance(info, dict): raise ValueError('Metadados de processo inválidos.')
    return info


def _argumentos_windows(comando):
    from ctypes import wintypes
    shell = ctypes.WinDLL('shell32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    shell.CommandLineToArgvW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype = ctypes.POINTER(wintypes.LPWSTR)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    n = ctypes.c_int()
    ptr = shell.CommandLineToArgvW(comando, ctypes.byref(n))
    if not ptr: raise ValueError('Argumentos da instância inválidos.')
    try:
        if not 1 <= n.value <= 4: raise ValueError('Argumentos da instância inválidos.')
        return [ptr[i] for i in range(n.value)]
    finally: kernel.LocalFree(ctypes.cast(ptr, wintypes.HLOCAL))


def _igual_caminho(a, b):
    return str(Path(a).resolve()).replace('/', '\\').casefold() == str(Path(b).resolve()).replace('/', '\\').casefold()


def _identidade_permitida(info, pid, codigo, dados, python):
    if (set(info) != {'pid','exe','comando','criado','owner_sid','atual_sid'}
            or type(info['pid']) is not int or info['pid'] != pid):
        return False
    if any(not isinstance(info[n], str) for n in ('exe','comando','criado','owner_sid','atual_sid')):
        return False
    if not re.fullmatch(r'[1-9][0-9]{5,19}', info['criado']): return False
    if not re.fullmatch(r'S-1-[0-9-]{3,180}', info['owner_sid']) or info['owner_sid'] != info['atual_sid']:
        return False
    if not 1 <= len(info['comando']) <= 4096: return False
    candidatos = ([python] if python is not None else [codigo/'.venv'/'Scripts'/'python.exe',
        dados.parent/'.venv'/'Scripts'/'python.exe', Path(sys.executable)])
    exe = Path(info['exe'])
    if not exe.is_absolute() or exe.name.casefold() not in ('python.exe','pythonw.exe'):
        return False
    _sem_links(exe)
    if not any(_igual_caminho(exe,p) for p in candidatos): return False
    argumentos = _argumentos_windows(info['comando'])
    if len(argumentos) not in (2,3) or len(argumentos)==3 and argumentos[2] != '--somente-painel':
        return False
    if not Path(argumentos[0]).is_absolute() or not Path(argumentos[1]).is_absolute():
        return False
    return _igual_caminho(argumentos[0],exe) and _igual_caminho(argumentos[1],codigo/'assistente_pc.py')


class _ProcessoWindows:
    """Um HANDLE mantém a identidade do alvo mesmo se seu PID for reutilizado."""
    def __init__(self, pid):
        from ctypes import wintypes
        self.w = wintypes
        self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        self.advapi = ctypes.WinDLL('advapi32', use_last_error=True)
        self.kernel.OpenProcess.argtypes = [wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
        self.kernel.OpenProcess.restype = wintypes.HANDLE
        self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessId.argtypes = [wintypes.HANDLE]
        self.kernel.GetProcessId.restype = wintypes.DWORD
        self.kernel.GetProcessTimes.argtypes = [wintypes.HANDLE,*([ctypes.POINTER(wintypes.FILETIME)]*4)]
        self.kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        self.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        self.kernel.TerminateProcess.argtypes = [wintypes.HANDLE,wintypes.UINT]
        self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE,wintypes.DWORD]
        self.kernel.WaitForSingleObject.restype = wintypes.DWORD
        self.advapi.OpenProcessToken.argtypes = [wintypes.HANDLE,wintypes.DWORD,ctypes.POINTER(wintypes.HANDLE)]
        self.advapi.GetTokenInformation.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(wintypes.DWORD)]
        self.advapi.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p,ctypes.POINTER(wintypes.LPWSTR)]
        self.kernel.LocalFree.argtypes = [wintypes.HLOCAL]
        self.kernel.LocalFree.restype = wintypes.HLOCAL
        self.handle = self.kernel.OpenProcess(0x1000 | 0x0001 | 0x00100000, False, pid)
        if not self.handle: raise OSError('Não foi possível abrir a instância identificada.')

    def _sid(self, handle):
        token = self.w.HANDLE()
        if not self.advapi.OpenProcessToken(handle, 0x0008, ctypes.byref(token)):
            raise OSError('Identidade do proprietário indisponível.')
        try:
            tamanho = self.w.DWORD()
            self.advapi.GetTokenInformation(token,1,None,0,ctypes.byref(tamanho))
            if not 1 <= tamanho.value <= 65536: raise OSError('Token de processo inválido.')
            buffer = ctypes.create_string_buffer(tamanho.value)
            if not self.advapi.GetTokenInformation(token,1,buffer,tamanho,ctypes.byref(tamanho)):
                raise OSError('Token de processo indisponível.')
            sid = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_void_p))[0]
            texto = self.w.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid,ctypes.byref(texto)):
                raise OSError('SID indisponível.')
            try: return texto.value
            finally: self.kernel.LocalFree(ctypes.cast(texto,self.w.HLOCAL))
        finally: self.kernel.CloseHandle(token)

    def identidade(self):
        criado, saida, kernel, usuario = (self.w.FILETIME() for _ in range(4))
        if not self.kernel.GetProcessTimes(self.handle,*(ctypes.byref(x) for x in (criado,saida,kernel,usuario))):
            raise OSError('Criação da instância indisponível.')
        buffer = ctypes.create_unicode_buffer(32768); tamanho = self.w.DWORD(32768)
        if not self.kernel.QueryFullProcessImageNameW(self.handle,0,buffer,ctypes.byref(tamanho)):
            raise OSError('Executável da instância indisponível.')
        return {'pid':int(self.kernel.GetProcessId(self.handle)), 'exe':buffer.value,
            'criado':str((criado.dwHighDateTime << 32) | criado.dwLowDateTime),
            'owner_sid':self._sid(self.handle), 'atual_sid':self._sid(self.kernel.GetCurrentProcess())}

    def parar(self):
        if not self.kernel.TerminateProcess(self.handle,0): raise OSError('A instância não foi encerrada.')

    def aguardar(self, segundos):
        return self.kernel.WaitForSingleObject(self.handle,max(0,int(segundos*1000))) == 0

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle); self.handle = None


def _mesma_identidade(handle_info, info, *, fonte_cim=False):
    # CreationDate/CIM tem microssegundos; FILETIME nativo tem 100 ns.
    # Só a comparação entre fontes admite os nove ticks perdidos no CIM.
    # A segunda leitura do mesmo HANDLE continua exigindo FILETIME exato.
    criado_igual = (abs(int(handle_info['criado'])-int(info['criado'])) < 10
                   if fonte_cim else handle_info['criado']==info['criado'])
    return (set(handle_info)=={'pid','exe','criado','owner_sid','atual_sid'}
        and handle_info['pid']==info['pid'] and _igual_caminho(handle_info['exe'],info['exe'])
        and criado_igual and all(handle_info[n]==info[n] for n in ('owner_sid','atual_sid')))


def parar_assistente(codigo, dados, *, autorizado=False, timeout=8, python=None):
    """Uma parada autorizada e estreita; falhas nunca repetem TerminateProcess.

    O fallback Windows é encerramento de processo, não uma saída cooperativa.
    ``livre=True`` só é retornado depois de verificar a liberação da trava.
    Não modifica .env, dados, arquivos da instância ou outros aplicativos.
    """
    if autorizado is not True: raise PermissionError('Autorize a preparação antes de encerrar sua instância.')
    if isinstance(timeout,bool) or not isinstance(timeout,(int,float)) or not math.isfinite(timeout) or not 1<=timeout<=30:
        raise ValueError('O prazo da parada deve ficar entre um e trinta segundos.')
    codigo, dados = _caminho(codigo), _caminho(dados)
    if python is not None: python = _caminho(python)
    _sem_links(codigo/'assistente_pc.py')
    if not (codigo/'assistente_pc.py').is_file(): raise ValueError('Selecione a raiz completa do assistente.')
    if not _WINDOWS:
        return _resultado('indisponivel','A parada automática é exclusiva do Windows; encerre o assistente no PC.')
    inicio = time.monotonic(); processo = None
    try:
        trava = _inspecionar_trava(dados)
        if not trava['ativa']:
            return _resultado('livre','Nenhuma instância mantém a trava; preparação pode continuar.',livre=True)
        pid = trava['pid']
        info = _metadados_windows(pid,min(4,timeout))
        if not _identidade_permitida(info,pid,codigo,dados,python):
            return _resultado('nao_identificada','Não foi possível provar a identidade da instância. Encerre a janela do bot antes de continuar.')
        processo = _ProcessoWindows(pid)
        capturada = processo.identidade()
        if not _mesma_identidade(capturada,info,fonte_cim=True):
            return _resultado('identidade_alterada','O processo mudou durante a verificação; nenhuma parada foi executada.')
        atual = _inspecionar_trava(dados)
        if atual != trava or not _mesma_identidade(processo.identidade(),capturada):
            return _resultado('identidade_alterada','A instância ou a trava mudou; nenhuma parada foi executada.')
        restante = timeout-(time.monotonic()-inicio)
        if restante<=0:
            return _resultado('prazo_esgotado','O prazo de identificação terminou; nenhuma parada foi executada.')
        processo.parar()
        if not processo.aguardar(restante):
            return _resultado('parada_nao_confirmada','O encerramento da instância não foi confirmado. Nenhuma nova parada foi enviada.',pid=pid)
        if _inspecionar_trava(dados)['ativa']:
            return _resultado('outra_instancia','A trava continua ocupada; não foi autorizado encerrar outra instância.',parado=True,pid=pid)
        return _resultado('encerrado','Somente a instância identificada do assistente foi encerrada para a preparação.',parado=True,livre=True,pid=pid)
    except (OSError,RuntimeError,ValueError,TypeError,KeyError,subprocess.SubprocessError):
        return _resultado('nao_confirmada','A identidade/parada do assistente não pôde ser confirmada. Encerre a janela do bot antes de continuar; nenhum outro processo foi selecionado.')
    finally:
        if processo is not None:
            try: processo.close()
            except (OSError,ValueError): pass
