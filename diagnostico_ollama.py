"""Diagnóstico independente do Ollama: metadados locais, sem .env ou dados do bot.

Por padrão não gera texto. --testar-cpu solicita uma única geração curta de
llama3.2:latest local, com prazo total, sem GPU e sem persistir opções.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime as dt
import http.client
import ipaddress
import json
import math
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit

URL_PADRAO='http://127.0.0.1:11434'
MODELO_TESTE='llama3.2:latest'
LIMITE_RESPOSTA=256_000
TIMEOUT_LEITURA=3
TIMEOUT_GERACAO=30
_TAG=re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?')


def validar_url(url):
    try:
        p=urlsplit(url)
        ip=ipaddress.ip_address(p.hostname or '')
        porta=p.port if p.port is not None else (443 if p.scheme=='https' else 80)
        if (not isinstance(url,str) or any(c.isspace() for c in url) or
                p.scheme not in ('http','https') or not ip.is_loopback or '%' in (p.hostname or '') or
                p.username is not None or p.password is not None or p.path not in ('','/') or
                '?' in url or '#' in url or not 1<=porta<=65535):raise ValueError
    except (ValueError,TypeError,AttributeError):
        raise ValueError('Informe somente uma URL de IP loopback, sem caminho ou credenciais.') from None
    host='['+ip.compressed+']' if ip.version==6 else ip.compressed
    return f'{p.scheme}://{host}:{porta}'


def _constante_invalida(_):raise ValueError('Número não finito.')

def _float_finito(valor):
    numero=float(valor)
    if not math.isfinite(numero):raise ValueError('Número não finito.')
    return numero


def consultar(url,rota,*,payload=None,timeout=TIMEOUT_LEITURA):
    """Socket direto, sem proxy/redirect, com prazo total inclusive cabeçalhos."""
    url=validar_url(url)
    if rota not in ('/api/version','/api/tags','/api/ps','/api/chat'):raise ValueError('Rota não permitida.')
    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or not math.isfinite(timeout) or not 0<timeout<=30:
        raise ValueError('Prazo inválido.')
    partes=urlsplit(url)
    classe=http.client.HTTPSConnection if partes.scheme=='https' else http.client.HTTPConnection
    cliente=classe(partes.hostname,partes.port,timeout=timeout)
    inicio=time.monotonic();expirou=threading.Event();prazo=None
    try:
        cliente.connect()
        conectado=cliente.sock
        def encerrar_leitura():
            expirou.set()
            try:conectado.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        restante=max(0,timeout-(time.monotonic()-inicio))
        prazo=threading.Timer(restante,encerrar_leitura);prazo.daemon=True;prazo.start()
        corpo=None if payload is None else json.dumps(payload,allow_nan=False).encode('utf-8')
        cliente.request('GET' if corpo is None else 'POST',rota,body=corpo,
                        headers={'Accept':'application/json',**({'Content-Type':'application/json'} if corpo else {})})
        with cliente.getresponse() as resposta:
            codigo=resposta.status
            if codigo!=200:return {'ok':False,'categoria':'http','codigo':codigo}
            conteudo=resposta.read(LIMITE_RESPOSTA+1)
        if expirou.is_set():return {'ok':False,'categoria':'timeout'}
        if len(conteudo)>LIMITE_RESPOSTA:return {'ok':False,'categoria':'resposta_grande'}
        dados=json.loads(conteudo.decode('utf-8'),parse_constant=_constante_invalida,parse_float=_float_finito)
        if not isinstance(dados,dict):raise ValueError
        return {'ok':True,'dados':dados}
    except (TimeoutError,socket.timeout):return {'ok':False,'categoria':'timeout'}
    except (OSError,http.client.HTTPException):
        return {'ok':False,'categoria':'timeout' if expirou.is_set() else 'conexao'}
    except (ValueError,UnicodeError,RecursionError):
        return {'ok':False,'categoria':'resposta_invalida'}
    finally:
        if prazo:prazo.cancel()
        cliente.close()


def _numero(valor,limite=10**17):
    return valor if isinstance(valor,(int,float)) and not isinstance(valor,bool) and 0<=valor<=limite and math.isfinite(valor) else None


def _gib(valor):
    numero=_numero(valor)
    return round(numero/1024**3,2) if numero is not None else None


def memoria_local():
    try:
        if sys.platform=='win32':
            class Memoria(ctypes.Structure):
                _fields_=[('tamanho',ctypes.c_uint32),('uso',ctypes.c_uint32),
                          *[(nome,ctypes.c_ulonglong) for nome in
                            ('fisica_total','fisica_livre','pagina_total','pagina_livre','virtual_total','virtual_livre','estendida_livre')]]
            m=Memoria();m.tamanho=ctypes.sizeof(m)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):raise OSError
            total,livre=m.fisica_total,m.fisica_livre
        else:
            pagina=os.sysconf('SC_PAGE_SIZE')
            total=pagina*os.sysconf('SC_PHYS_PAGES');livre=pagina*os.sysconf('SC_AVPHYS_PAGES')
        resultado={'ok':True,'total_gib':_gib(total),'livre_gib':_gib(livre)}
        if sys.platform=='win32':
            resultado.update({'commit_limite_gib':_gib(m.pagina_total),'commit_disponivel_gib':_gib(m.pagina_livre)})
        return resultado
    except (AttributeError,OSError,ValueError):return {'ok':False}


def _executar(comando,*,url=None):
    # Não herdar credenciais, PYTHONPATH ou parâmetros externos dos provedores.
    permitidas={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','LANG','LC_ALL'}
    ambiente={k:v for k,v in os.environ.items() if k.upper() in permitidas}
    if url is not None:ambiente['OLLAMA_HOST']=validar_url(url)
    try:
        return subprocess.run(comando,env=ambiente,shell=False,stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                              errors='replace',timeout=5,check=False)
    except (OSError,subprocess.TimeoutExpired):return None


def versao_cli(url=URL_PADRAO):
    caminho=shutil.which('ollama')
    if not caminho:return {'ok':False,'categoria':'ferramenta_ausente'}
    r=_executar([caminho,'--version'],url=url)
    if r is None or r.returncode:return {'ok':False,'categoria':'consulta_indisponivel'}
    # Algumas versões imprimem primeiro a versão do servidor e depois a do cliente.
    texto=(r.stdout+'\n'+r.stderr)[:4000]
    achado=re.search(r'client version is\s+([0-9]+(?:\.[0-9]+){1,3})',texto,re.I)
    achado=achado or re.search(r'ollama version is\s+([0-9]+(?:\.[0-9]+){1,3})',texto,re.I)
    return {'ok':True,'versao_informada':achado.group(1)} if achado else {'ok':False,'categoria':'versao_nao_identificada'}


def gpu_local():
    caminho=shutil.which('nvidia-smi')
    if not caminho:return {'ok':False,'categoria':'ferramenta_ausente'}
    r=_executar([caminho,'--query-gpu=memory.total,memory.free,utilization.gpu,driver_version',
                 '--format=csv,noheader,nounits'])
    if r is None or r.returncode:return {'ok':False,'categoria':'consulta_indisponivel'}
    placas=[]
    for linha in r.stdout.splitlines()[:16]:
        colunas=[c.strip() for c in linha.split(',')]
        if len(colunas)!=4 or any(not c.isdecimal() for c in colunas[:3]) or not re.fullmatch(r'[0-9.]{1,30}',colunas[3]):continue
        placas.append({'vram_total_mib':int(colunas[0]),'vram_livre_mib':int(colunas[1]),
                       'uso_percentual':int(colunas[2]),'driver':colunas[3]})
    return {'ok':bool(placas),'placas':placas}


def _modelos(resposta,*,carregados=False):
    if not resposta.get('ok'):return resposta
    itens=resposta['dados'].get('models')
    if not isinstance(itens,list):return {'ok':False,'categoria':'resposta_invalida'}
    modelos=[]
    for item in itens[:100]:
        if not isinstance(item,dict):continue
        nome=item.get('name') or item.get('model')
        if not isinstance(nome,str) or len(nome)>200 or not _TAG.fullmatch(nome):continue
        detalhes=item.get('details',{})
        detalhes=detalhes if isinstance(detalhes,dict) else {}
        nuvem=nome.lower().endswith(('-cloud',':cloud')) or any(
            isinstance(d.get(k),str) and bool(d[k].strip())
            for d in (item,detalhes) for k in ('remote_model','remote_host'))
        modelo={'nome':nome,'nuvem':bool(nuvem),'tamanho_gib':_gib(item.get('size'))}
        if carregados:
            modelo.update({'vram_gib':_gib(item.get('size_vram')),
                           'contexto':_numero(item.get('context_length'),10**7)})
        modelos.append(modelo)
    return {'ok':True,'modelos':modelos}


def coletar(url=URL_PADRAO,*,testar_cpu=False):
    url=validar_url(url)
    if not isinstance(testar_cpu,bool):raise ValueError('Opção de teste inválida.')
    inicio_coleta=time.monotonic()
    relatorio={'versao_diagnostico':1,'coletado_em_utc':dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds'),
               'url_local':url,'memoria':memoria_local(),'gpu':gpu_local(),'cli':versao_cli(url)}
    versao=consultar(url,'/api/version')
    if versao.get('ok'):
        numero=versao['dados'].get('version')
        versao={'ok':True,'versao':numero} if isinstance(numero,str) and re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}(?:-[A-Za-z0-9.-]+)?',numero) else {'ok':False,'categoria':'resposta_invalida'}
    relatorio['servico']=versao
    relatorio['catalogo']=_modelos(consultar(url,'/api/tags'))
    relatorio['carregados']=_modelos(consultar(url,'/api/ps'),carregados=True)
    relatorio['teste_cpu']={'executado':False}
    avisos=['Metadados e modelos registrados não comprovam geração de respostas.',
            'Se o console do servidor mostrar Selecionar, pressione Esc para liberar a saída.',
            'Mantenha a equipe desativada enquanto testa uma única tag local.']
    if relatorio['memoria'].get('ok') and (relatorio['memoria'].get('livre_gib') or 0)<2:
        avisos.append('Há menos de 2 GiB de RAM livre; carregamento e paginação podem demorar.')
    if testar_cpu:
        locais=[m for m in relatorio['catalogo'].get('modelos',[]) if m['nome']==MODELO_TESTE]
        if not locais or any(m['nuvem'] for m in locais):
            relatorio['teste_cpu']={'executado':False,'categoria':'modelo_local_nao_confirmado'}
        else:
            inicio=time.monotonic()
            teste=consultar(url,'/api/chat',payload={'model':MODELO_TESTE,'stream':False,'keep_alive':0,
                'messages':[{'role':'user','content':'Responda apenas OK.'}],
                'options':{'num_gpu':0,'num_ctx':1024,'num_predict':8}},timeout=TIMEOUT_GERACAO)
            if teste.get('ok'):
                mensagem=teste['dados'].get('message')
                conteudo=mensagem.get('content') if isinstance(mensagem,dict) else None
                teste={'ok':True} if isinstance(conteudo,str) and conteudo.strip() else {'ok':False,'categoria':'sem_texto'}
            relatorio['teste_cpu']={'executado':True,'modelo':MODELO_TESTE,'gpu_solicitada':False,
                'duracao_segundos':round(time.monotonic()-inicio,1),**teste}
            avisos.append('O teste CPU solicita num_gpu=0 só nesta chamada; não altera arquivos ou limites do servidor.')
            avisos.append('Expirar o prazo de 30 s, inclusive no teste CPU, não prova travamento infinito nem sua causa.')
    relatorio['orientacoes']=avisos
    relatorio['duracao_segundos']=round(time.monotonic()-inicio_coleta,1)
    return relatorio


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',default=URL_PADRAO,help='IP loopback do serviço; não lê a URL do .env.')
    p.add_argument('--testar-cpu',action='store_true',help='Uma geração curta do Llama local em CPU; não baixa modelos.')
    args=p.parse_args(argv)
    try:
        print('Diagnóstico Ollama: leitura local; sem .env, histórico ou gravação de arquivos.',flush=True)
        if args.testar_cpu:print('Teste CPU solicitado: até 30 s de geração, além das leituras de metadados.',flush=True)
        print(json.dumps(coletar(args.url,testar_cpu=args.testar_cpu),ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except ValueError as erro:
        print('Diagnóstico não iniciado: '+str(erro));return 2
    except KeyboardInterrupt:
        print('Diagnóstico interrompido.');return 130


if __name__=='__main__':sys.exit(main())
