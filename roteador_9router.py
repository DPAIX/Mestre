"""Cliente do 9Router local, compatível com a API OpenAI, sem ferramentas.

O serviço 9Router e suas contas são administrados em seu próprio dashboard.
Este cliente não instala pacotes, não lê bancos do 9Router nem suas credenciais,
não configura proxies/túneis e não repete requisições. Endpoint em loopback não
significa inferência local: o 9Router pode encaminhar mensagens para provedores.

Contrato verificado em decolua/9router, branch master, versão CLI 0.5.109:
https://github.com/decolua/9router/blob/master/src/app/api/v1/models/route.js
https://github.com/decolua/9router/blob/master/src/app/api/v1/chat/completions/route.js
https://github.com/decolua/9router/blob/master/cli/package.json
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import ipaddress
import json
import math
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urlsplit

URL_PADRAO = 'http://127.0.0.1:20128/v1'
PROVEDOR = '9Router'
LIMITE_JSON = 1_000_000
LIMITE_MODELOS = 2000
LIMITE_TEXTO = 12000
PRAZO_CATALOGO = 5


def _falha(detalhe, categoria='configuracao', codigo=0):
    # Importação tardia evita ciclo ao integrar este cliente ao Roteador.
    from multi_ia import FalhaAPI
    return FalhaAPI(PROVEDOR, codigo, detalhe, categoria)


def validar_url(valor):
    """Aceita somente /v1 em IP literal loopback, sem segredo na URL."""
    try:
        if not isinstance(valor, str) or not valor or len(valor)>250:
            raise ValueError()
        if valor != valor.strip() or any(c.isspace() or ord(c)<32 for c in valor):
            raise ValueError()
        if any(c in valor for c in ('?', '#', '%', '\\')):
            raise ValueError()
        url=urlsplit(valor)
        if url.scheme not in ('http', 'https') or url.username is not None or url.password is not None:
            raise ValueError()
        if url.path not in ('', '/', '/v1', '/v1/'):
            raise ValueError()
        ip=ipaddress.ip_address(url.hostname or '')
        if not ip.is_loopback:raise ValueError()
        porta=url.port if url.port is not None else (443 if url.scheme=='https' else 80)
        if not 1<=porta<=65535:raise ValueError()
        host='['+ip.compressed+']' if ip.version==6 else ip.compressed
        return f'{url.scheme}://{host}:{porta}/v1'
    except (ValueError, TypeError):
        raise _falha('NINE_ROUTER_URL deve usar um IP loopback literal e a base /v1, como http://127.0.0.1:20128/v1; sem credenciais, consulta ou fragmento.') from None


def validar_modelo(valor):
    """IDs de modelo/combo são texto JSON, nunca comandos de terminal."""
    if (not isinstance(valor,str) or not valor.strip() or valor!=valor.strip()
            or len(valor)>200 or any(not c.isprintable() for c in valor)):
        raise _falha('Selecione um identificador de modelo ou combo 9Router, com até 200 caracteres e sem controles.')
    return valor


@dataclass(frozen=True)
class _Configuracao:
    habilitado: bool
    url: str
    modelo: str
    timeout: float
    chave: str = field(repr=False)


def _configuracao(*, exigir_modelo=False):
    flag=os.getenv('NINE_ROUTER_HABILITADO','0')
    if flag not in ('0','1'):
        raise _falha('NINE_ROUTER_HABILITADO deve ser 0 ou 1.')
    url=validar_url(os.getenv('NINE_ROUTER_URL',URL_PADRAO))
    modelo=os.getenv('NINE_ROUTER_MODEL','')
    if modelo or exigir_modelo:modelo=validar_modelo(modelo)
    try:timeout=float(os.getenv('NINE_ROUTER_TIMEOUT','30'))
    except (TypeError,ValueError,OverflowError):timeout=float('nan')
    if not math.isfinite(timeout) or not 1<=timeout<=120:
        raise _falha('NINE_ROUTER_TIMEOUT deve ser um número finito entre 1 e 120 segundos.')
    chave=os.getenv('NINE_ROUTER_API_KEY','')
    if not isinstance(chave,str) or len(chave)>4096 or (chave and re.fullmatch(r'[!-~]+',chave) is None):
        raise _falha('NINE_ROUTER_API_KEY possui formato inválido. Confira somente no arquivo local, sem compartilhar seu conteúdo.')
    return _Configuracao(flag=='1',url,modelo,timeout,chave)


def _seguro(texto,chave=''):
    from nucleo import redigir
    texto=str(texto)
    if chave:texto=texto.replace(chave,'[CREDENCIAL-REDACTADA]')
    return str(redigir(texto))


def configuracao():
    """Metadados públicos da configuração, sem chave e sem chamada de rede."""
    cfg=_configuracao()
    return {'habilitado':cfg.habilitado,'url':cfg.url,
            'modelo':_seguro(cfg.modelo,cfg.chave),'timeout':cfg.timeout,
            'chave_definida':bool(cfg.chave)}


def assinatura_configuracao():
    """Fingerprint da configuração em memória; nunca devolve seus valores."""
    nomes=('NINE_ROUTER_HABILITADO','NINE_ROUTER_URL','NINE_ROUTER_MODEL',
           'NINE_ROUTER_API_KEY','NINE_ROUTER_TIMEOUT')
    bruto=json.dumps([os.getenv(nome,'') for nome in nomes],ensure_ascii=True).encode('utf-8')
    return hashlib.sha256(bruto).hexdigest()


def configurado():
    """Configuração suficiente não comprova instalação, conta ou conectividade."""
    try:return _configuracao(exigir_modelo=True).habilitado
    except Exception as erro:
        from multi_ia import FalhaAPI
        if isinstance(erro,FalhaAPI):return False
        raise


def diagnostico_local():
    """Inspeção de opções em memória; nunca lê .env ou faz consulta ao serviço."""
    try:
        meta=configuracao()
        pronto=meta['habilitado'] and bool(meta['modelo'])
        return {**meta,'configurado':pronto,'verificado':False,
                'estado':'configurado; não testado' if pronto else 'não habilitado ou sem modelo selecionado',
                'orientacao':'Configure contas, modelos e combos no dashboard local do 9Router. Consultas podem usar provedores externos e cota.'}
    except Exception as erro:
        from multi_ia import FalhaAPI
        if not isinstance(erro,FalhaAPI):raise
        return {'configurado':False,'verificado':False,'estado':'configuração inválida',
                'orientacao':str(erro)}


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise _falha('Redirecionamento do endpoint 9Router bloqueado; nenhuma credencial foi encaminhada.')


def _objeto_unico(pares):
    obj={}
    for chave,valor in pares:
        if chave in obj:raise ValueError('Campo repetido.')
        obj[chave]=valor
    return obj


def _float_finito(valor):
    numero=float(valor)
    if not math.isfinite(numero):raise ValueError('Número não finito.')
    return numero


def _constante_invalida(valor):
    raise ValueError('Constante inválida.')


def _carregar_json(bruto):
    if len(bruto)>LIMITE_JSON:
        raise _falha('A resposta do 9Router excedeu o limite de tamanho.','resposta_invalida')
    try:
        obj=json.loads(bruto.decode('utf-8'),parse_constant=_constante_invalida,
                       parse_float=_float_finito,object_pairs_hook=_objeto_unico)
        if not isinstance(obj,dict):raise ValueError()
        return obj
    except (ValueError,UnicodeError,RecursionError,OverflowError):
        raise _falha('O 9Router retornou uma resposta JSON inválida.','resposta_invalida') from None


def _requisicao(cfg,recurso,*,payload=None,timeout=None):
    """Uma tentativa limitada; não usa os proxies do ambiente nem redireciona."""
    from multi_ia import FalhaAPI,analisar_erro
    if recurso not in ('/models','/chat/completions'):raise _falha('Recurso 9Router não permitido.')
    # A listagem explícita prepara a seleção antes de habilitar a geração.
    if not cfg.habilitado and recurso!='/models':
        raise _falha('A integração 9Router está desabilitada. Ative-a após configurar o serviço e revisar o envio de mensagens.')
    headers={'Accept':'application/json','Content-Type':'application/json'}
    if cfg.chave:headers['Authorization']='Bearer '+cfg.chave
    corpo=None if payload is None else json.dumps(payload,ensure_ascii=False,allow_nan=False).encode('utf-8')
    pedido=urllib.request.Request(cfg.url+recurso,corpo,headers=headers,
                                  method='GET' if payload is None else 'POST')
    cliente=urllib.request.build_opener(urllib.request.ProxyHandler({}),_SemRedirecionamento())
    try:
        with cliente.open(pedido,timeout=cfg.timeout if timeout is None else timeout) as resposta:
            dados=_carregar_json(resposta.read(LIMITE_JSON+1))
        if dados.get('error'):
            raise analisar_erro(PROVEDOR,0,_seguro(json.dumps(dados,ensure_ascii=False),cfg.chave))
        return dados
    except urllib.error.HTTPError as erro:
        codigo=erro.code
        retry=erro.headers.get('Retry-After') if erro.headers else None
        try:mensagem=erro.read(12000).decode('utf-8','replace')
        finally:erro.close()
        raise analisar_erro(PROVEDOR,codigo,_seguro(mensagem,cfg.chave),retry_after=retry) from None
    except FalhaAPI:raise
    except (urllib.error.URLError,TimeoutError,OSError) as erro:
        causa=erro.reason if isinstance(erro,urllib.error.URLError) else erro
        if isinstance(causa,TimeoutError):
            raise _falha('O prazo de resposta do 9Router terminou. Isso não comprova cancelamento da consulta nos provedores; nenhuma nova tentativa foi enviada.','tempo_esgotado') from None
        raise _falha('Não foi possível acessar o endpoint local do 9Router. Confira o processo, endereço e porta; nenhuma nova tentativa foi enviada.','rede') from None


def listar_modelos():
    """Catálogo por solicitação explícita. O servidor pode consultar provedores."""
    cfg=_configuracao()
    dados=_requisicao(cfg,'/models',timeout=min(PRAZO_CATALOGO,cfg.timeout))
    itens=dados.get('data')
    if not isinstance(itens,list) or len(itens)>LIMITE_MODELOS:
        raise _falha('O 9Router retornou um catálogo fora do formato ou limite esperado.','resposta_invalida')
    modelos=[];vistos=set()
    for item in itens:
        if not isinstance(item,dict):raise _falha('O catálogo contém um item inválido.','resposta_invalida')
        nome=item.get('id')
        try:nome=validar_modelo(nome)
        except Exception as erro:
            from multi_ia import FalhaAPI
            if isinstance(erro,FalhaAPI):raise _falha('O catálogo contém um identificador de modelo inválido.','resposta_invalida') from None
            raise
        if nome in vistos:continue
        vistos.add(nome)
        modelos.append({'id':_seguro(nome,cfg.chave),'nome':_seguro(nome,cfg.chave),
                        'combo':item.get('owned_by')=='combo'})
    return {'modelos':modelos,'modelo':_seguro(cfg.modelo,cfg.chave),
            'habilitado':cfg.habilitado,'geracao_testada':False}


def responder(pergunta,historico=None):
    """Retorna somente texto. Respostas e tool_calls nunca são executados."""
    from multi_ia import preparar_mensagens,SISTEMA
    if not isinstance(pergunta,str) or not pergunta.strip() or len(pergunta)>LIMITE_TEXTO:
        raise ValueError('Envie uma pergunta de até 12000 caracteres para o 9Router.')
    cfg=_configuracao(exigir_modelo=True)
    # A redação da chave opcional ocorre também no pedido/histórico, antes de sair.
    pergunta=_seguro(pergunta,cfg.chave)
    if len(pergunta)>LIMITE_TEXTO:
        raise ValueError('A pergunta excedeu o limite após ocultar credenciais. Envie uma mensagem menor.')
    mensagens=preparar_mensagens(pergunta,historico)
    # O helper legado limita o pedido atual a 11000 caracteres. Preserve-o
    # integralmente aqui e retire espaço do contexto antigo, nunca do pedido.
    saldo=24000-len(pergunta)
    anteriores=[]
    for mensagem in reversed(mensagens[:-1]):
        if saldo<=0:break
        conteudo=_seguro(mensagem['content'],cfg.chave)[-saldo:]
        anteriores.append({'role':mensagem['role'],'content':conteudo})
        saldo-=len(conteudo)
    mensagens=list(reversed(anteriores))+[{'role':'user','content':pergunta}]
    dados=_requisicao(cfg,'/chat/completions',payload={
        'model':cfg.modelo,'messages':[{'role':'system','content':SISTEMA}]+mensagens,
        'stream':False,'max_tokens':800})
    escolhas=dados.get('choices')
    if not isinstance(escolhas,list) or not escolhas or not isinstance(escolhas[0],dict):
        raise _falha('O 9Router não devolveu uma resposta de conversa válida.','resposta_invalida')
    mensagem=escolhas[0].get('message')
    if not isinstance(mensagem,dict):
        raise _falha('O 9Router não devolveu uma mensagem textual.','resposta_invalida')
    texto=mensagem.get('content')
    if not isinstance(texto,str) or not texto.strip():
        raise _falha('O 9Router não devolveu texto. Nenhuma ferramenta ou chamada de função foi executada.','resposta_invalida')
    return _seguro(texto,cfg.chave)[:LIMITE_TEXTO]
