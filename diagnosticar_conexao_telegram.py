"""Consulta pública e finita da conexão Telegram, sem ler credenciais ou dados.

Executa apenas um Node.js instalado, com código fixo em pasta temporária própria.
Não carrega o assistente, não consulta mensagens e não altera rede ou processos
existentes. O prazo externo encerra somente o Node filho criado pela consulta.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import ipaddress
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile

_WINDOWS = sys.platform == 'win32'
NODE_FALLBACK = Path('F:/PROGRAMAS/nodejs/node.exe')
PRAZO_VERSAO = 5
PRAZO_SONDA = 16
MAX_LINHA = 4096
_AMBIENTE = frozenset({'PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR',
                      'SYSTEMDRIVE', 'TEMP', 'TMP'})
_CODIGOS = frozenset({'ENOTFOUND', 'EAI_AGAIN', 'ECONNREFUSED', 'ECONNRESET',
    'ENETUNREACH', 'EHOSTUNREACH', 'EADDRNOTAVAIL', 'ETIMEDOUT', 'ETIMEOUT',
    'ECANCELLED', 'ENODATA', 'ESERVFAIL', 'EREFUSED', 'ENOTIMP', 'ENETDOWN',
    'ESOCKETTIMEDOUT', 'EPROTO', 'EACCES', 'EPERM', 'EBADRESP', 'ENOMEM',
    'EDESTRUCTION', 'ENONAME', 'EOF', 'EBADFAMILY', 'EBADFLAGS', 'EBADHINTS',
    'EBADQUERY', 'EBADNAME', 'EBADSTR', 'EFILE', 'EFORMERR', 'ENOTINITIALIZED',
    'ELOADIPHLPAPI', 'EADDRGETNETWORKPARAMS', 'ERR_SOCKET_BAD_PORT', 'ERR_INVALID_ARG_TYPE',
    'ERR_INVALID_ARG_VALUE', 'ERR_TLS_CERT_ALTNAME_INVALID', 'CERT_HAS_EXPIRED',
    'CERT_NOT_YET_VALID', 'UNABLE_TO_VERIFY_LEAF_SIGNATURE',
    'UNABLE_TO_GET_ISSUER_CERT_LOCALLY', 'DEPTH_ZERO_SELF_SIGNED_CERT',
    'SELF_SIGNED_CERT_IN_CHAIN', 'ERR_TLS_CERT_SIGNATURE_ALGORITHM_UNSUPPORTED',
    'ERR_SSL_WRONG_VERSION_NUMBER', 'ERR_SSL_TLSV1_ALERT_INTERNAL_ERROR',
    'ERR_SSL_TLSV1_ALERT_PROTOCOL_VERSION', 'ABORT_ERR',
    'Error', 'TypeError', 'RangeError'})

SCRIPT_JS = r"""
const dns = require('node:dns'), https = require('node:https'), fs = require('node:fs'), net = require('node:net');
const inicio = Date.now(), etapas = {4:'DNS',6:'DNS'}, tempos = {4:{},6:{}}, resultado = {4:null,6:null}, os = {4:'PENDENTE',6:'PENDENTE'}, publico = {4:'PENDENTE',6:'PENDENTE'};
const resolver = new dns.promises.Resolver({timeout:2000,tries:1});
resolver.setServers(['1.1.1.1','8.8.8.8']);
let emitido = false;
function seguro(ip) {
  if (net.isIP(ip) === 4) {
    const a=ip.split('.').map(Number), x=a[0], y=a[1];
    if (x===0 || x===10 || x===127 || x>=224 || x===169&&y===254 || x===172&&y>=16&&y<=31 || x===192&&(y===168||y===0||y===2) || x===100&&y>=64&&y<=127 || x===198&&(y===18||y===19||y===51) || x===203&&y===0) return 'LOCAL_OU_PRIVADO';
    return ip;
  }
  if (net.isIP(ip) === 6 && /^[23][0-9a-f]{0,3}:/i.test(ip) && ip.toLowerCase().startsWith('2001:db8:')===false) return ip;
  return 'LOCAL_OU_PRIVADO';
}
function enderecos(valor) {
  const a=Array.isArray(valor)?valor:[valor];
  return a.slice(0,4).map(x=>seguro(typeof x==='string'?x:x.address)).join(',') || 'SEM_REGISTROS';
}
function emitir() {
  if (emitido) return;
  emitido=true;clearTimeout(limite);
  for (const n of [4,6]) fs.writeSync(1,'TELEGRAM_'+n+'='+(resultado[n]??'TIMEOUT_12s')+';ETAPA='+etapas[n]+';MS='+(Date.now()-inicio)+';DNS_OS='+os[n]+';DNS_PUBLICO='+publico[n]+';DNS='+ (tempos[n].dns??'-')+';TCP='+(tempos[n].tcp??'-')+';TLS='+(tempos[n].tls??'-')+'\n');
  resolver.cancel();process.exit(0);
}
function verificar() {
  if (resultado[4]===null || resultado[6]===null || publico[4]==='PENDENTE' || publico[6]==='PENDENTE') return;
  emitir();
}
function fim(n,valor) { if(resultado[n]===null){resultado[n]=valor;verificar();} }
const limite=setTimeout(()=>{for(const n of [4,6])if(publico[n]==='PENDENTE')publico[n]='TIMEOUT_12s';emitir();},12000);
for(const n of [4,6]) {
  resolver['resolve'+n]('api.telegram.org').then(a=>{publico[n]=enderecos(a);verificar();},e=>{publico[n]=e.code||e.name;verificar();});
  try {
    const pedido=https.get('https://api.telegram.org/',{family:n,autoSelectFamily:false,agent:false,lookup:(nome,opcoes,retorno)=>dns.lookup(nome,opcoes,(erro,endereco,familia)=>{
      if(erro==null){os[n]=enderecos(endereco);tempos[n].dns=Date.now()-inicio;etapas[n]='TCP';}else os[n]=erro.code||erro.name;
      retorno(erro,endereco,familia);
    })},resposta=>{fim(n,'HTTP_'+resposta.statusCode);resposta.destroy();pedido.destroy();});
    pedido.on('socket',socket=>{socket.once('connect',()=>{tempos[n].tcp=Date.now()-inicio;etapas[n]='TLS';});socket.once('secureConnect',()=>{tempos[n].tls=Date.now()-inicio;etapas[n]='HTTP';});});
    pedido.once('error',erro=>fim(n,erro.code||erro.name));
  }catch(erro){fim(n,erro.code||erro.name);}
}
"""


class FalhaDiagnostico(RuntimeError):
    """Falha pública, sem conteúdo recebido de subprocessos ou ambiente."""


def _ambiente():
    return {k: v for k, v in os.environ.items() if k.upper() in _AMBIENTE}


@contextmanager
def _reserva():
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateMutexW(None, False, 'Local\\MeuControlePCDiagnosticoTelegramV1')
    if not handle:
        raise FalhaDiagnostico('DIAGNOSTICO=RESERVA_INDISPONIVEL')
    adquirido = False
    try:
        adquirido = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
        if not adquirido:
            raise FalhaDiagnostico('DIAGNOSTICO=OUTRA_CONSULTA_EM_EXECUCAO')
        yield
    finally:
        if adquirido:
            kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def _node(ambiente):
    caminho_path = next((v for k, v in ambiente.items() if k.upper() == 'PATH'), '')
    caminho = Path(shutil.which('node.exe', path=caminho_path) or NODE_FALLBACK)
    if not caminho.is_absolute() or caminho.name.casefold() != 'node.exe' or not caminho.is_file():
        raise FalhaDiagnostico('DIAGNOSTICO=NODE_NAO_LOCALIZADO')
    caminho = caminho.resolve(strict=True)
    try:
        resultado = subprocess.run([str(caminho), '--version'], cwd=str(caminho.parent),
            env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, shell=False, check=False, timeout=PRAZO_VERSAO,
            text=True, encoding='utf-8', errors='strict',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
    except (OSError, subprocess.SubprocessError, UnicodeError):
        raise FalhaDiagnostico('DIAGNOSTICO=VERSAO_NODE_INDISPONIVEL') from None
    texto = resultado.stdout if isinstance(resultado.stdout, str) else ''
    versao = re.fullmatch(r'v([0-9]{1,3})\.[0-9]{1,5}\.[0-9]{1,5}', texto.strip())
    if resultado.returncode or not versao or int(versao[1]) < 22:
        raise FalhaDiagnostico('DIAGNOSTICO=NODE_22_OU_SUPERIOR_NECESSARIO')
    return caminho


def _numero(texto, *, ausente=False):
    return (ausente and texto == '-') or bool(re.fullmatch(r'[0-9]{1,9}', texto))


def _endereco_publico(valor, familia):
    if valor in {'PENDENTE', 'SEM_REGISTROS', 'LOCAL_OU_PRIVADO', 'TIMEOUT_12s'}:
        return True
    if valor in _CODIGOS:
        return True
    enderecos = valor.split(',')
    if not 1 <= len(enderecos) <= 4:
        return False
    for endereco in enderecos:
        if endereco == 'LOCAL_OU_PRIVADO':
            continue
        try:
            ip = ipaddress.ip_address(endereco)
        except ValueError:
            return False
        if ip.version != familia or not ip.is_global or ip.is_multicast:
            return False
    return True


def _linhas_publicas(texto):
    if not isinstance(texto, str) or len(texto) > MAX_LINHA * 2 + 4:
        raise FalhaDiagnostico('DIAGNOSTICO=RESPOSTA_INESPERADA')
    linhas = texto.splitlines()
    if len(linhas) != 2:
        raise FalhaDiagnostico('DIAGNOSTICO=RESPOSTA_INESPERADA')
    validadas = []
    for familia, linha in zip((4, 6), linhas):
        if len(linha) > MAX_LINHA or any(ord(c) < 32 for c in linha):
            raise FalhaDiagnostico('DIAGNOSTICO=RESPOSTA_INESPERADA')
        campos = linha.split(';')
        nomes = (f'TELEGRAM_{familia}', 'ETAPA', 'MS', 'DNS_OS', 'DNS_PUBLICO', 'DNS', 'TCP', 'TLS')
        if len(campos) != len(nomes) or any(not c.startswith(n + '=') for c, n in zip(campos, nomes)):
            raise FalhaDiagnostico('DIAGNOSTICO=RESPOSTA_INESPERADA')
        valores = [c.split('=', 1)[1] for c in campos]
        if (not (re.fullmatch(r'HTTP_[1-5][0-9]{2}', valores[0])
                  or valores[0] == 'TIMEOUT_12s' or valores[0] in _CODIGOS)
                or valores[1] not in {'DNS', 'TCP', 'TLS', 'HTTP'}
                or not _numero(valores[2])
                or not all(_endereco_publico(v, familia) for v in valores[3:5])
                or not all(_numero(v, ausente=True) for v in valores[5:])):
            raise FalhaDiagnostico('DIAGNOSTICO=RESPOSTA_INESPERADA')
        validadas.append(linha)
    return validadas


def diagnosticar():
    """Executa somente a sonda pública fixa, sem consultar autenticação do bot."""
    if not _WINDOWS:
        raise FalhaDiagnostico('DIAGNOSTICO=EXECUTE_NO_WINDOWS')
    with _reserva():
        ambiente = _ambiente()
        node = _node(ambiente)
        with tempfile.TemporaryDirectory(prefix='meucontrolepc-telegram-publico-') as pasta:
            arquivo = Path(pasta) / 'sonda.cjs'
            arquivo.write_text(SCRIPT_JS, encoding='utf-8')
            try:
                resultado = subprocess.run([str(node), str(arquivo)], cwd=pasta,
                    env=ambiente, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, shell=False, check=False, timeout=PRAZO_SONDA,
                    text=True, encoding='utf-8', errors='strict',
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
            except subprocess.TimeoutExpired:
                raise FalhaDiagnostico('DIAGNOSTICO=TEMPO_TOTAL_ESGOTADO_16S') from None
            except (OSError, subprocess.SubprocessError, UnicodeError):
                raise FalhaDiagnostico('DIAGNOSTICO=CONSULTA_INDISPONIVEL') from None
            if resultado.returncode:
                raise FalhaDiagnostico('DIAGNOSTICO=CONSULTA_INDISPONIVEL')
            linhas = _linhas_publicas(resultado.stdout)
        return {'estado': 'concluido', 'linhas': linhas}


def _sem_redirecionamento(caminho):
    for parte in reversed((caminho, *caminho.parents)):
        try:
            meta = parte.lstat()
        except FileNotFoundError:
            if parte == caminho:
                return
            raise FalhaDiagnostico('DIAGNOSTICO=PASTA_RESULTADO_INDISPONIVEL') from None
        if (stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise FalhaDiagnostico('DIAGNOSTICO=RESULTADO_NAO_ACEITA_REDIRECIONAMENTO')
        if parte != caminho and not stat.S_ISDIR(meta.st_mode):
            raise FalhaDiagnostico('DIAGNOSTICO=PASTA_RESULTADO_INDISPONIVEL')
        if parte == caminho and not stat.S_ISREG(meta.st_mode):
            raise FalhaDiagnostico('DIAGNOSTICO=DESTINO_RESULTADO_INVALIDO')


def _salvar_resultado(linhas):
    texto = '\n'.join(linhas) + '\n'
    _linhas_publicas(texto)
    destino = Path(__file__).absolute().parent / 'RESULTADO_TELEGRAM.txt'
    _sem_redirecionamento(destino)
    fd, temporario = tempfile.mkstemp(prefix='.resultado-telegram-', suffix='.tmp', dir=destino.parent)
    temporario = Path(temporario)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as arquivo:
            arquivo.write(texto)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        _sem_redirecionamento(destino)
        os.replace(temporario, destino)
    finally:
        temporario.unlink(missing_ok=True)


def main(argv=None):
    argumentos = list(sys.argv[1:] if argv is None else argv)
    if argumentos not in ([], ['--salvar']):
        print('DIAGNOSTICO=OPCAO_INVALIDA', flush=True)
        return 1
    try:
        resultado = diagnosticar()
        if argumentos:
            _salvar_resultado(resultado['linhas'])
    except FalhaDiagnostico as erro:
        print(str(erro), flush=True)
        return 1
    except (OSError, RuntimeError, ValueError, TypeError):
        print('DIAGNOSTICO=INDISPONIVEL', flush=True)
        return 1
    for linha in resultado['linhas']:
        print(linha, flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
