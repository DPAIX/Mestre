"""Confere o armazenamento do daemon e prepara um Ollama dedicado em F:.

OLLAMA_MODELS no cliente não muda um servidor existente. A prova usa o
listener e o ambiente do processo, projetando apenas caminho de modelos e
perfil. Não baixa pesos, copia contas ou encerra processos.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from diagnostico_ollama import consultar, validar_url

URL_DEDICADA = 'http://127.0.0.1:11435'
_DIGEST = re.compile(r'sha256:([a-f0-9]{64})')
_PUBLICAS = frozenset({'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC',
    'PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','NUMBER_OF_PROCESSORS',
    'PROCESSOR_ARCHITECTURE','LANG','LC_ALL'})


class FalhaArmazenamento(RuntimeError):
    """Mensagem controlada: nenhum ambiente bruto ou dado de conta."""


def _seguro(caminho):
    caminho = Path(caminho)
    if not caminho.is_absolute() or str(caminho).startswith(('\\\\','//')):
        raise FalhaArmazenamento('O armazenamento exige um caminho local absoluto, sem compartilhamentos de rede.')
    for parte in (caminho, *caminho.parents):
        try:
            m = parte.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(m.st_mode) or getattr(m,'st_file_attributes',0) & 0x400:
            raise FalhaArmazenamento('O armazenamento não pode seguir links ou junctions.')
    return caminho


def _em_f(caminho):
    from instalacao_em_f import validar_caminho
    return validar_caminho(caminho)


def _inspecionar(url):
    """Só retorna PID, executável e pasta comprovada do listener local."""
    try:
        import psutil
        partes = urlsplit(validar_url(url))
        pids = set()
        for item in psutil.net_connections(kind='tcp'):
            if item.status != psutil.CONN_LISTEN or not item.laddr:
                continue
            ip = getattr(item.laddr, 'ip', item.laddr[0])
            porta = getattr(item.laddr, 'port', item.laddr[1])
            if porta == partes.port and ip in (partes.hostname,'0.0.0.0','::'):
                if type(item.pid) is not int or item.pid <= 0:
                    raise ValueError
                pids.add(item.pid)
        if not pids:
            return None
        if len(pids) != 1:
            raise ValueError
        pid = pids.pop()
        processo = psutil.Process(pid)
        criado = processo.create_time()
        executavel = _seguro(processo.exe())
        argumentos = processo.cmdline()
        if (executavel.name.casefold() != 'ollama.exe' or not executavel.is_file()
                or len(argumentos) != 2 or argumentos[1] != 'serve'
                or Path(argumentos[0]).name.casefold() != 'ollama.exe'):
            raise ValueError
        # Não persistir nem devolver o dicionário completo de ambiente.
        ambiente = processo.environ()
        modelos = next((v for k,v in ambiente.items() if k.upper()=='OLLAMA_MODELS'),None)
        perfil = next((v for k,v in ambiente.items() if k.upper()=='USERPROFILE'),None)
        del ambiente
        if not modelos:
            if not isinstance(perfil,str) or not perfil:
                raise ValueError
            modelos = str(_seguro(perfil) / '.ollama' / 'models')
        if not isinstance(modelos,str) or not modelos or any(c in modelos for c in '\r\n\0'):
            raise ValueError
        modelos = _seguro(modelos)
        try:
            _em_f(perfil)
            perfil_f=True
        except (ValueError,TypeError,RuntimeError):
            perfil_f=False
        if not processo.is_running() or processo.create_time() != criado:
            raise ValueError
        return {'pid':pid,'executavel':executavel,'modelos':modelos,'perfil_f':perfil_f}
    except FalhaArmazenamento:
        raise
    except Exception:
        raise FalhaArmazenamento('Não foi possível comprovar o processo e o armazenamento do Ollama. Nenhum download foi enviado.') from None


def _catalogo(url):
    resposta = consultar(url,'/api/tags',timeout=3)
    try:
        modelos = resposta['dados']['models']
        if not resposta.get('ok') or not isinstance(modelos,list) or len(modelos)>512:
            raise ValueError
        resultado = {}
        for item in modelos:
            nome = item.get('name') or item.get('model')
            digest = item.get('digest')
            if (not isinstance(nome,str) or not 1 <= len(nome) <= 200 or
                    any(c in nome for c in '\r\n\0') or not isinstance(digest,str)
                    or not re.fullmatch(r'[a-f0-9]{64}',digest.removeprefix('sha256:'))):
                raise ValueError
            valor = digest.removeprefix('sha256:')
            if nome in resultado and resultado[nome] != valor:
                raise ValueError
            resultado[nome] = valor
        return resultado
    except (KeyError,TypeError,AttributeError,ValueError):
        raise FalhaArmazenamento('O catálogo local não permitiu conferir os modelos por nome e digest. Nenhum download foi enviado.') from None


def _hash(arquivo):
    digest = hashlib.sha256()
    with arquivo.open('rb') as f:
        for bloco in iter(lambda:f.read(4*1024*1024), b''):
            digest.update(bloco)
    return digest.hexdigest()


def _planejar_copia(origem, destino, catalogo):
    origem = _seguro(origem); destino = _seguro(destino)
    if not catalogo:
        return [], []
    pasta = _seguro(origem/'manifests')
    if not pasta.is_dir():
        raise FalhaArmazenamento('A pasta dos modelos anteriores não foi confirmada. Nada foi apagado ou baixado.')
    manifestos = []
    blobs = {}
    encontrados = set()
    for atual, pastas, arquivos in os.walk(pasta,followlinks=False):
        atual = _seguro(atual)
        for nome in pastas:
            _seguro(atual/nome)
        for nome in arquivos:
            fonte = _seguro(atual/nome)
            if not fonte.is_file() or fonte.stat().st_size>1_000_000:
                raise FalhaArmazenamento('Há metadados de modelo que não puderam ser conferidos.')
            bruto = fonte.read_bytes()
            digest = hashlib.sha256(bruto).hexdigest()
            if digest not in catalogo.values():
                continue
            try:
                doc = json.loads(bruto)
                itens = [doc['config'],*doc['layers']]
                if not isinstance(doc['layers'],list) or not 1<=len(itens)<=200:
                    raise ValueError
                for item in itens:
                    marca = _DIGEST.fullmatch(item['digest'])
                    tamanho = item['size']
                    if not marca or type(tamanho) is not int or tamanho<0:
                        raise ValueError
                    esperado = marca[1]
                    blob = _seguro(origem/'blobs'/('sha256-'+esperado))
                    if not blob.is_file() or blob.stat().st_size != tamanho:
                        raise ValueError
                    if esperado in blobs and blobs[esperado][1] != tamanho:
                        raise ValueError
                    blobs[esperado] = (blob,tamanho)
            except (ValueError,KeyError,TypeError,AttributeError):
                raise FalhaArmazenamento('Os pesos anteriores não correspondem aos manifestos. A origem foi preservada.') from None
            relativo = fonte.relative_to(origem)
            alvo = _seguro(destino/relativo)
            if alvo.exists() and (not alvo.is_file() or _hash(alvo)!=digest):
                raise FalhaArmazenamento('O destino já tem um manifesto diferente. Essas alterações foram preservadas.')
            manifestos.append((fonte,alvo,digest))
            encontrados.add(digest)
            if len(manifestos)>4096:
                raise FalhaArmazenamento('O catálogo excedeu o limite de conferência local.')
    if set(catalogo.values())-encontrados:
        raise FalhaArmazenamento('Nem todos os modelos anteriores foram localizados com os digests esperados.')
    pesos = [(fonte,_seguro(destino/'blobs'/fonte.name),digest,tamanho)
             for digest,(fonte,tamanho) in blobs.items()]
    return pesos,manifestos


def _copiar_verificado(fonte, alvo, esperado):
    if alvo.exists() and alvo.is_file() and _hash(alvo)==esperado:
        return False
    alvo.parent.mkdir(parents=True,exist_ok=True)
    fd, nome = tempfile.mkstemp(prefix='.ollama_copia.',suffix='.tmp',dir=str(alvo.parent))
    temporario = Path(nome)
    digest = hashlib.sha256()
    try:
        with os.fdopen(fd,'wb') as saida, fonte.open('rb') as entrada:
            for bloco in iter(lambda:entrada.read(4*1024*1024),b''):
                digest.update(bloco);saida.write(bloco)
            saida.flush();os.fsync(saida.fileno())
        if digest.hexdigest()!=esperado:
            raise FalhaArmazenamento('Um arquivo mudou durante a cópia. A origem e os manifestos anteriores foram preservados.')
        os.replace(temporario,alvo)
        return True
    finally:
        temporario.unlink(missing_ok=True)


def copiar_modelos(origem, destino, catalogo):
    """Copia somente manifests referenciados e blobs com SHA256, sem exclusões."""
    pesos,manifestos = _planejar_copia(origem,destino,catalogo)
    destino = _seguro(destino)
    existente = destino
    while not existente.exists():
        existente = existente.parent
    necessarios = sum(tamanho for _,alvo,digest,tamanho in pesos
        if not (alvo.is_file() and _hash(alvo)==digest))
    if shutil.disk_usage(existente).free < necessarios+1024**3:
        raise FalhaArmazenamento('F: não tem espaço livre suficiente para copiar os modelos e manter uma reserva de 1 GiB.')
    copiados = 0
    for indice,(fonte,alvo,digest,_) in enumerate(pesos,1):
        print(f'Conferindo/copiando peso {indice}/{len(pesos)} para F:; a origem permanece.',file=sys.stderr,flush=True)
        copiados += _copiar_verificado(fonte,alvo,digest)
    # Publicar o catálogo somente depois dos blobs completos e conferidos.
    for fonte,alvo,digest in manifestos:
        if alvo.exists() and _hash(alvo)!=digest:
            raise FalhaArmazenamento('Um manifesto no destino mudou durante a cópia. A alteração posterior foi preservada.')
        _copiar_verificado(fonte,alvo,digest)
    return copiados


def _ambiente_servidor(raiz,modelos):
    perfil = _em_f(raiz/'perfil_ollama')
    temporarios = _em_f(raiz/'temporarios'/'ollama')
    for pasta in (perfil,temporarios,modelos,perfil/'AppData'/'Local',perfil/'AppData'/'Roaming'):
        _em_f(pasta).mkdir(parents=True,exist_ok=True)
    ambiente = {k:v for k,v in os.environ.items() if k.upper() in _PUBLICAS}
    ambiente.update({'USERPROFILE':str(perfil),'LOCALAPPDATA':str(perfil/'AppData'/'Local'),
        'APPDATA':str(perfil/'AppData'/'Roaming'),'TEMP':str(temporarios),'TMP':str(temporarios),
        'OLLAMA_MODELS':str(modelos),'OLLAMA_HOST':URL_DEDICADA})
    if os.getenv('OLLAMA_NO_CLOUD','').casefold() in ('1','true'):
        ambiente['OLLAMA_NO_CLOUD']='1'
    return ambiente


def _ocupado(url):
    p = urlsplit(url)
    try:
        with socket.create_connection((p.hostname,p.port),timeout=0.5):
            return True
    except ConnectionRefusedError:
        return False
    except OSError:
        from iniciar_servicos_locais import _vinculo_exclusivo_disponivel
        return not _vinculo_exclusivo_disponivel(p)


def _verificar_preservados(url,catalogo):
    atuais = _catalogo(url)
    if any(atuais.get(nome)!=digest for nome,digest in catalogo.items()):
        raise FalhaArmazenamento('O serviço em F: não confirmou todos os modelos anteriores. A configuração ainda não foi trocada.')


def garantir_armazenamento_f(url, raiz, *, executavel=None, permitir_importacao=True):
    """Retorna URL e store comprovados; o chamador persiste as opções depois."""
    if type(permitir_importacao) is not bool:
        raise ValueError('A opção de importação deve ser booleana.')
    raiz = _em_f(raiz)
    url = validar_url(url)
    if urlsplit(url).hostname != '127.0.0.1':
        raise FalhaArmazenamento('A preparação em F: exige endpoint IPv4 de loopback literal.')
    atual = _inspecionar(url)
    catalogo = _catalogo(url) if atual is not None else {}
    modelos_f=None
    if atual is not None:
        try:
            modelos_f = _em_f(atual['modelos'])
        except (ValueError,RuntimeError):
            modelos_f = None
        if modelos_f is not None and atual.get('perfil_f') is True:
            _planejar_copia(modelos_f,modelos_f,catalogo)
            _verificar_preservados(url,catalogo)
            return {'url':url,'modelos':str(modelos_f),'iniciado':False,'importado':False}
    destino = modelos_f if modelos_f is not None else _em_f(raiz/'modelos_ollama')
    if atual is None and os.getenv('OLLAMA_MODELS'):
        try:
            # Depois de um logon, o daemon pode ainda não existir. Reutilizar
            # a pasta F já selecionada preserva o catálogo fora da raiz padrão.
            destino=_em_f(os.environ['OLLAMA_MODELS'])
        except (ValueError,TypeError,RuntimeError):
            raise FalhaArmazenamento('O armazenamento anterior não está comprovado em F: e o servidor não está disponível para conferir a importação. Nenhum download foi enviado.') from None
    dedicado = _inspecionar(URL_DEDICADA)
    if dedicado is not None:
        if dedicado.get('perfil_f') is not True:
            raise FalhaArmazenamento('A porta dedicada não comprovou seu perfil de execução em F:. Nenhum processo foi encerrado.')
        if _em_f(dedicado['modelos']) != destino:
            raise FalhaArmazenamento('A porta dedicada já pertence a outro armazenamento. Nenhum processo foi encerrado.')
        if executavel is not None and dedicado['executavel'] != _seguro(executavel):
            raise FalhaArmazenamento('O executável da porta dedicada não corresponde ao selecionado. Nenhum processo foi encerrado.')
        _planejar_copia(destino,destino,_catalogo(URL_DEDICADA))
        _verificar_preservados(URL_DEDICADA,catalogo)
        return {'url':URL_DEDICADA,'modelos':str(destino),'iniciado':False,'importado':False}
    if _ocupado(URL_DEDICADA):
        raise FalhaArmazenamento('A porta dedicada não foi confirmada livre. Nenhum segundo servidor foi iniciado.')
    if atual is None and _ocupado(url):
        raise FalhaArmazenamento('Não foi possível comprovar o armazenamento do serviço anterior. Nenhum download foi enviado.')
    programa = _seguro(executavel or (atual['executavel'] if atual else ''))
    if programa.name.casefold()!='ollama.exe' or not programa.is_file():
        raise FalhaArmazenamento('O executável existente do Ollama não foi confirmado.')
    copiados = 0
    if atual is not None and catalogo:
        if not permitir_importacao:
            raise FalhaArmazenamento('Os modelos anteriores estão fora de F:. A importação não foi solicitada.')
        copiados = copiar_modelos(atual['modelos'],destino,catalogo)
    ambiente = _ambiente_servidor(raiz,destino)
    processo = subprocess.Popen([str(programa),'serve'],env=ambiente,shell=False,
        stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    prazo = time.monotonic()+15
    for _ in range(30):
        if processo.poll() is not None:
            break
        prova = _inspecionar(URL_DEDICADA)
        if (prova is not None and prova['pid']==processo.pid
                and prova.get('perfil_f') is True
                and prova['executavel']==programa and _em_f(prova['modelos'])==destino):
            try:
                _verificar_preservados(URL_DEDICADA,catalogo)
                return {'url':URL_DEDICADA,'modelos':str(destino),'iniciado':True,'importado':bool(copiados)}
            except FalhaArmazenamento:
                pass  # Somente novas leituras de metadados dentro do prazo.
        if time.monotonic()>=prazo:
            break
        time.sleep(0.5)
    raise FalhaArmazenamento('O Ollama iniciado não comprovou armazenamento e catálogo em F:. Nenhum download ou novo início foi enviado.')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--garantir',action='store_true',required=True)
    parser.add_argument('--url',required=True)
    parser.add_argument('--raiz',required=True)
    parser.add_argument('--executavel')
    args=parser.parse_args(argv)
    try:
        if sys.platform!='win32':
            raise FalhaArmazenamento('A conferência do armazenamento do daemon requer a sessão Windows do PC.')
        resultado=garantir_armazenamento_f(args.url,Path(args.raiz),executavel=args.executavel)
        print(json.dumps({'ok':True,**resultado},ensure_ascii=False),flush=True)
        return 0
    except (FalhaArmazenamento,ValueError,OSError,subprocess.SubprocessError):
        print(json.dumps({'ok':False,'erro':'armazenamento_nao_confirmado',
            'mensagem':'O armazenamento em F: não foi confirmado. Nenhum pull foi enviado; origem e processos existentes foram preservados.'},
            ensure_ascii=False),flush=True)
        return 2


if __name__=='__main__':raise SystemExit(main())
