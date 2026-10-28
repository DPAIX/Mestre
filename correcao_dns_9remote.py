"""Corrige DNS e limpeza por PID somente nos bundles gerenciados 9Remote 3.0.43.

Não executa programas, não usa rede e não lê configuração ou chaves do 9Remote.
O chamador deve encerrar o 9Remote e serializar a manutenção antes de chamar a
API. Arquivos desconhecidos nunca são sobrescritos, inclusive durante reversão.
"""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading

VERSAO = '3.0.43'
MAX_ARQUIVO = 10 * 1024 * 1024
MAX_MANIFESTO = 65536
BACKUP = '.meucontrolepc-dns-3.0.43'
_TRAVA = threading.RLock()

_BLOCO_CLI = b'gr.default.lookup=(e,n,r)=>{if(typeof n=="function"&&(r=n,n={}),e==="localhost"||Ac.test(e))return eo(e,n,r);(async()=>{if(n.family===6)return{addrs:await Mn.resolve6(e),family:6};if(n.family===4)return{addrs:await Mn.resolve4(e),family:4};let[t,i]=await Promise.allSettled([Mn.resolve4(e),Mn.resolve6(e)]);return t.status==="fulfilled"&&t.value?.length?{addrs:t.value,family:4}:i.status==="fulfilled"&&i.value?.length?{addrs:i.value,family:6}:null})().then(t=>{if(!t?.addrs?.length)return eo(e,n,r);n.all?r(null,t.addrs.map(i=>({address:i,family:t.family}))):r(null,t.addrs[0],t.family)}).catch(()=>eo(e,n,r))};'
_BLOCO_SERVIDOR = b'xS.default.lookup=(t,e,n)=>{if(typeof e=="function"&&(n=e,e={}),t==="localhost"||IOe.test(t))return z1(t,e,n);(async()=>{if(e.family===6)return{addrs:await V_.resolve6(t),family:6};if(e.family===4)return{addrs:await V_.resolve4(t),family:4};let[i,s]=await Promise.allSettled([V_.resolve4(t),V_.resolve6(t)]);return i.status==="fulfilled"&&i.value?.length?{addrs:i.value,family:4}:s.status==="fulfilled"&&s.value?.length?{addrs:s.value,family:6}:null})().then(i=>{if(!i?.addrs?.length)return z1(t,e,n);e.all?n(null,i.addrs.map(s=>({address:s,family:i.family}))):n(null,i.addrs[0],i.family)}).catch(()=>z1(t,e,n))};'

_TROCAS_PROCESSOS = (
    (b'function Wr(e){try{process.platform==="win32"?(0,fr.execSync)(`for /f "tokens=5" %a in (\'netstat -aon ^| findstr :${e}\') do taskkill /F /PID %a`,{stdio:"ignore",windowsHide:!0}):(0,fr.execSync)(`lsof -ti:${e} | xargs kill -9 2>/dev/null || true`,{stdio:"ignore"})}catch{}}', b'function Wr(e){}'),
    (b'function Fr(e){if(En)try{(0,ze.execSync)(`taskkill /PID ${e} /T /F`,{windowsHide:!0,stdio:"ignore"})}catch{}else try{process.kill(e,"SIGKILL")}catch{}}', b'var __meuControleCloudflared3043=new Map;function Fr(e){let n=__meuControleCloudflared3043.get(e);if(!n)return;try{n.kill("SIGTERM")}catch{}}'),
    (b'gn=c.pid,or=!1', b'gn=c.pid,__meuControleCloudflared3043.set(c.pid,c),c.once("exit",()=>{__meuControleCloudflared3043.get(c.pid)===c&&__meuControleCloudflared3043.delete(c.pid)}),or=!1'),
    (b'function Pl(){try{Rs()}catch{}try{if((0,z.existsSync)(Io)){let e=parseInt((0,z.readFileSync)(Io,"utf8"));if(Number.isFinite(e))try{process.kill(e)}catch{}try{(0,z.unlinkSync)(Io)}catch{}}}catch{}try{process.platform==="win32"?(0,un.execSync)(`for /f "tokens=5" %a in (\'netstat -aon ^| findstr :${Lt}\') do taskkill /F /PID %a`,{stdio:"ignore",windowsHide:!0}):(0,un.execSync)(`lsof -ti:${Lt} | xargs kill -9 2>/dev/null || true`,{stdio:"ignore"})}catch{}if(process.platform==="win32"){let e=Date.now()+1500;for(;Date.now()<e;);}}', b'function Pl(){}'),
)

ESPECIFICACOES = {
    'cli.cjs': {
        'original': '9cca7e1be7c89062a48bcb57a3b3777323330a3e9da6755412c3a01b5ccd1594',
        'corrigido': 'c1bb40e98a07351d10c5d5668445e0f1018ea448865cb44ee2c5a9df45973ea6',
        'antes': _BLOCO_CLI, 'depois': b'gr.default.lookup=eo;',
        'trocas': ((_BLOCO_CLI, b'gr.default.lookup=eo;'), *_TROCAS_PROCESSOS),
    },
    'server.cjs': {
        'original': '83a681b49d5a89c5e9e17589534450288b45dfa0c6c63036953d8053af418edc',
        'corrigido': '83a339f5c13121d7d8d55c6b7630912904c2fcef95b0a10b3cb5e1a83b9a079e',
        'antes': _BLOCO_SERVIDOR, 'depois': b'xS.default.lookup=z1;',
    },
}


class FalhaCorrecao(RuntimeError):
    """Erro sanitizado; informa se a tentativa desfez suas próprias escritas."""
    def __init__(self, mensagem, *, reversao_completa=True):
        super().__init__(mensagem)
        self.reversao_completa = bool(reversao_completa)


@contextmanager
def manutencao():
    """Serializa instalação e reparo; o mutex Windows aceita a mesma thread."""
    with _TRAVA:
        if sys.platform != 'win32':
            yield
            return
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        kernel.CreateMutexW.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
        kernel.ReleaseMutex.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateMutexW(None, False, 'Local\\MeuControlePC9RemoteManutencao3043')
        if not handle:
            raise FalhaCorrecao('Não foi possível reservar a manutenção do 9Remote.')
        adquirido = False
        try:
            adquirido = kernel.WaitForSingleObject(handle, 0) in (0, 0x80)
            if not adquirido:
                raise FalhaCorrecao('Outra manutenção do 9Remote está em execução; aguarde sua conclusão.')
            yield
        finally:
            if adquirido:
                kernel.ReleaseMutex(handle)
            kernel.CloseHandle(handle)


def _sha(conteudo):
    return hashlib.sha256(conteudo).hexdigest()


def _conferir(caminho, *, diretorio=False, ausente=False):
    for parte in reversed((caminho, *caminho.parents)):
        try:
            meta = parte.lstat()
        except FileNotFoundError:
            if parte == caminho and ausente:
                return None
            raise FalhaCorrecao('Um componente do pacote gerenciado não foi localizado.') from None
        if (stat.S_ISLNK(meta.st_mode) or getattr(meta, 'st_file_attributes', 0)
                & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise FalhaCorrecao('A manutenção não aceita links, junctions ou redirecionamentos.')
        if parte != caminho or diretorio:
            if not stat.S_ISDIR(meta.st_mode):
                raise FalhaCorrecao('Um componente do pacote gerenciado não é um diretório.')
        elif not stat.S_ISREG(meta.st_mode):
            raise FalhaCorrecao('A manutenção aceita somente arquivos regulares.')
    return meta


def _absoluto(valor):
    if not isinstance(valor, (str, os.PathLike)):
        raise FalhaCorrecao('Informe o caminho absoluto do pacote gerenciado.')
    texto = os.fspath(valor)
    if not isinstance(texto, str):
        raise FalhaCorrecao('Informe o caminho absoluto do pacote gerenciado.')
    caminho = Path(texto)
    if (not caminho.is_absolute() or '..' in caminho.parts
            or any(ord(c) < 32 for c in texto)):
        raise FalhaCorrecao('Informe o caminho absoluto sem navegação relativa.')
    return caminho


def _ler(caminho, *, limite=MAX_ARQUIVO):
    meta = _conferir(caminho)
    if meta.st_size > limite:
        raise FalhaCorrecao('Um arquivo excede o limite permitido para a manutenção.')
    fd = os.open(caminho, os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as arquivo:
        atual = os.fstat(arquivo.fileno())
        if (not stat.S_ISREG(atual.st_mode) or (atual.st_dev, atual.st_ino)
                != (meta.st_dev, meta.st_ino)):
            raise FalhaCorrecao('O arquivo mudou durante a conferência.')
        conteudo = arquivo.read(limite + 1)
    if len(conteudo) > limite:
        raise FalhaCorrecao('Um arquivo excede o limite permitido para a manutenção.')
    return conteudo


def _pares_unicos(pares):
    resultado = {}
    for nome, valor in pares:
        if nome in resultado:
            raise FalhaCorrecao('O manifesto do pacote contém campos duplicados.')
        resultado[nome] = valor
    return resultado


def _pacote(valor):
    pacote = _absoluto(valor)
    import instalacao_em_f as instalacao
    local = _absoluto(instalacao.raiz()/'runtime'/'Local' if instalacao.ativo()
                      else os.environ.get('LOCALAPPDATA', ''))
    esperado = local / 'MeuControlePC' / 'integracoes' / '9remote' / 'node_modules' / '9remote'
    if pacote != esperado:
        raise FalhaCorrecao('A correção aceita somente o pacote 9Remote gerenciado pelo assistente.')
    _conferir(pacote, diretorio=True)
    _conferir(pacote / 'dist', diretorio=True)
    try:
        manifesto = json.loads(_ler(pacote / 'package.json', limite=MAX_MANIFESTO),
                               object_pairs_hook=_pares_unicos)
    except (ValueError, UnicodeError):
        raise FalhaCorrecao('O manifesto do pacote não é válido.') from None
    if not isinstance(manifesto, dict) or manifesto.get('name') != '9remote' or manifesto.get('version') != VERSAO:
        raise FalhaCorrecao('A correção exige o pacote oficial 9Remote 3.0.43.')
    return pacote


def _versoes(conteudo, especificacao):
    trocas = especificacao.get('trocas')
    if trocas is None:
        trocas = ((especificacao['antes'], especificacao['depois']),)
    assinatura = _sha(conteudo)
    if assinatura == especificacao['original']:
        original = conteudo
        corrigido = original
        for antes, depois in trocas:
            if corrigido.count(antes) != 1:
                raise FalhaCorrecao('O bloco original esperado não é único.')
            corrigido = corrigido.replace(antes, depois)
    elif assinatura == especificacao['corrigido']:
        corrigido = conteudo
        original = corrigido
        for antes, depois in reversed(trocas):
            if original.count(depois) != 1:
                raise FalhaCorrecao('O bloco corrigido esperado não é único.')
            original = original.replace(depois, antes)
    else:
        raise FalhaCorrecao('Os bundles não correspondem às fontes verificadas do 9Remote 3.0.43.')
    if _sha(original) != especificacao['original'] or _sha(corrigido) != especificacao['corrigido']:
        raise FalhaCorrecao('A transformação não corresponde aos hashes verificados.')
    return original, corrigido


def _gravar_atomico(caminho, conteudo):
    _conferir(caminho.parent, diretorio=True)
    _conferir(caminho, ausente=True)
    fd, temporario = tempfile.mkstemp(prefix='.dns-9remote-', dir=caminho.parent)
    temporario = Path(temporario)
    try:
        with os.fdopen(fd, 'wb') as arquivo:
            arquivo.write(conteudo)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        _conferir(caminho.parent, diretorio=True)
        _conferir(caminho, ausente=True)
        _conferir(temporario)
        os.replace(temporario, caminho)
        if _ler(caminho) != conteudo:
            raise FalhaCorrecao('A gravação não passou pela verificação final.')
    finally:
        try:
            temporario.unlink()
        except FileNotFoundError:
            pass


def _preparar_plano(valor):
    pacote = _pacote(valor)
    backup = pacote / BACKUP
    backup_existe = _conferir(backup, diretorio=True, ausente=True) is not None
    plano = []
    for nome, especificacao in ESPECIFICACOES.items():
        arquivo = pacote / 'dist' / nome
        atual = _ler(arquivo)
        original, corrigido = _versoes(atual, especificacao)
        copia = backup / (nome + '.original')
        tem_copia = False
        if backup_existe:
            tem_copia = _conferir(copia, ausente=True) is not None
            if tem_copia and _ler(copia) != original:
                raise FalhaCorrecao('Um backup não corresponde ao original verificado.')
        if atual == corrigido and not tem_copia:
            raise FalhaCorrecao('O bundle corrigido não tem seu backup original verificado.')
        plano.append((arquivo, copia, atual, original, corrigido, tem_copia))
    return pacote, backup, backup_existe, plano


def planejar_correcao(pacote):
    """Confere o pacote inteiro e backups sem criar, escrever ou executar nada."""
    with manutencao():
        try:
            _, _, _, plano = _preparar_plano(pacote)
            estados = {item[0].name: ('original' if item[2] == item[3] else 'aplicada') for item in plano}
            conjunto = set(estados.values())
            return {'versao': VERSAO, 'estado': next(iter(conjunto)) if len(conjunto) == 1 else 'parcial',
                    'arquivos': estados, 'arquivos_pendentes': sum(item[2] != item[4] for item in plano),
                    'backup_disponivel': all(item[5] for item in plano)}
        except OSError:
            raise FalhaCorrecao('Não foi possível conferir os arquivos gerenciados.') from None


def _executar(valor, *, aplicar):
    with manutencao():
        try:
            pacote, backup, backup_existe, plano = _preparar_plano(valor)
            # Todos os arquivos e backups são conferidos antes da primeira escrita.
            alteracoes = [item for item in plano if item[2] != item[4 if aplicar else 3]]
            if alteracoes and aplicar:
                if not backup_existe:
                    _conferir(pacote, diretorio=True)
                    backup.mkdir()
                    _conferir(backup, diretorio=True)
                for _, copia, _, original, _, tem_copia in plano:
                    if not tem_copia:
                        _gravar_atomico(copia, original)
                backup_existe = True
            for arquivo, copia, atual, original, _, _ in plano:
                if _ler(arquivo) != atual:
                    raise FalhaCorrecao('Um bundle mudou durante a manutenção; tente novamente com o aplicativo encerrado.')
                if backup_existe and _ler(copia) != original:
                    raise FalhaCorrecao('Um backup mudou durante a manutenção.')
            escritos = []
            try:
                for item in alteracoes:
                    arquivo, _, atual, _, _, _ = item
                    if _ler(arquivo) != atual:
                        raise FalhaCorrecao('Um bundle mudou durante a manutenção.')
                    escritos.append(item)
                    _gravar_atomico(arquivo, item[4 if aplicar else 3])
            except (OSError, FalhaCorrecao):
                completa = True
                for arquivo, _, anterior, original, corrigido, _ in reversed(escritos):
                    try:
                        atual = _ler(arquivo)
                        if atual not in (original, corrigido):
                            completa = False
                        elif atual != anterior:
                            _gravar_atomico(arquivo, anterior)
                    except (OSError, FalhaCorrecao):
                        completa = False
                raise FalhaCorrecao('A manutenção falhou; os backups verificados foram preservados.',
                                    reversao_completa=completa) from None
            return {'versao': VERSAO, 'estado': 'aplicada' if aplicar else 'original',
                    'arquivos_alterados': len(alteracoes), 'backup_disponivel': backup_existe}
        except OSError:
            raise FalhaCorrecao('Não foi possível concluir a manutenção dos arquivos gerenciados.') from None


def aplicar_correcao(pacote):
    """Aplica as transformações públicas de DNS e processos, com backup."""
    return _executar(pacote, aplicar=True)


def reverter_correcao(pacote):
    """Restaura os originais verificados, preservando os backups para reaplicação."""
    return _executar(pacote, aplicar=False)
