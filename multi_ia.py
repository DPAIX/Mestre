"""Roteamento de perguntas. Exa só para pesquisa explícita, nunca para decidir ações.
Limites e créditos são distinguidos. Provedores sem créditos ficam suspensos na sessão.
"""
from __future__ import annotations
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from nucleo import registrar,redigir,gravar_json,ler_json

LIMITE_RESPOSTA=2_000_000

def detalhe_seguro(texto,chave=''):
    """Erros de provedores podem repetir a chave, inclusive sem prefixo conhecido."""
    texto=str(texto)
    if chave:texto=texto.replace(chave,'[CREDENCIAL-REDACTADA]')
    return str(redigir(texto))

@dataclass
class FalhaAPI(Exception):
    provedor: str
    codigo: int
    detalhe: str
    categoria: str='temporario'
    def __str__(self):return f'{self.provedor} ({self.codigo}/{self.categoria}): {self.detalhe}'

def analisar_erro(provedor,codigo,corpo):
    try:
        payload=json.loads(corpo)
        e=payload.get('error',payload)
        tipo=' '.join(str(e.get(campo) or '') for campo in ('type','code','status'))
        msg=str(e.get('message') or e.get('status') or corpo)
    except (ValueError,AttributeError,TypeError):tipo='';msg=str(corpo)
    low=(tipo+' '+msg).lower()
    if codigo==404: cat='modelo_indisponivel'
    elif codigo==401 or codigo==403: cat='autenticacao'
    elif codigo==402 or any(x in low for x in ('no credits','credit balance','insufficient_quota','billing','purchase credits','saldo insuficiente','credits remaining','usage_limit','credit_balance_exhausted')):
        cat='sem_creditos'
    elif codigo==429: cat='limite_temporario'
    elif codigo in (500,502,503,504,529):cat='servidor_ocupado'
    elif codigo==400:cat='requisicao_invalida'
    else:cat='temporario'
    return FalhaAPI(provedor,codigo,str(redigir(msg))[:250],cat)

def postar(url,chave,payload,provedor,headers=None,timeout=18):
    cab={'Content-Type':'application/json'}
    cab.update(headers or {})
    req=urllib.request.Request(url,json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=cab,method='POST')
    try:
        with urllib.request.urlopen(req,timeout=timeout) as resposta:
            corpo=resposta.read(LIMITE_RESPOSTA+1)
        if len(corpo)>LIMITE_RESPOSTA:
            raise FalhaAPI(provedor,0,'Resposta excedeu o tamanho permitido.','resposta_invalida')
        try:
            dados=json.loads(corpo.decode('utf-8'))
        except (ValueError,UnicodeError):
            raise FalhaAPI(provedor,0,'O provedor retornou uma resposta JSON inválida.','resposta_invalida') from None
        if not isinstance(dados,dict):
            raise FalhaAPI(provedor,0,'O provedor retornou uma estrutura inesperada.','resposta_invalida')
        if dados.get('error'):
            raise analisar_erro(provedor,0,detalhe_seguro(json.dumps(dados),chave))
        return dados
    except urllib.error.HTTPError as e:
        try:corpo=e.read(1200).decode('utf-8','replace')
        finally:e.close()
        raise analisar_erro(provedor,e.code,detalhe_seguro(corpo,chave)) from None
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise FalhaAPI(provedor,0,detalhe_seguro(e,chave)[:150],'rede') from None

class Roteador:
    def __init__(self):
        self.bloqueados={}
        self.motivos={}
        self.ultimo_provedor='local'
        self.mutex=threading.RLock()
        self._recuperar_bloqueios()
    def _recuperar_bloqueios(self):
        """Restaura somente bloqueios com prazo válido, sem carregar credenciais."""
        try:
            dados=ler_json('estado_ia.json',{})
            if not isinstance(dados,dict):return
            for nome,item in dados.items():
                if nome not in ('Gemini','OpenAI','Claude','Exa') or not isinstance(item,dict):continue
                try:limite=float(item.get('ate',0))
                except (ValueError,TypeError):continue
                categoria=str(item.get('categoria','temporario'))
                if time.time()<limite<time.time()+86460:
                    self.bloqueados[nome]=limite
                    self.motivos[nome]=categoria
        except (ValueError,TypeError,OSError):pass

    def _salvar_bloqueios(self):
        try:
            gravar_json('estado_ia.json',{nome:{'ate':ate,'categoria':self.motivos.get(nome,'temporario')}
                         for nome,ate in self.bloqueados.items() if ate>time.time()})
        except (OSError,ValueError):pass

    def _registrar_sucesso(self,provedor):
        with self.mutex:
            self.bloqueados.pop(provedor,None)
            self.motivos.pop(provedor,None)
            self._salvar_bloqueios()

    def reativar(self):
        """Remove pausas locais após troca de credencial ou recarga de crédito.
        NÃO faz consulta e NÃO contorna limites impostos pelo provedor.
        """
        with self.mutex:
            antigos=len(self.bloqueados)
            self.bloqueados.clear()
            self.motivos.clear()
            self._salvar_bloqueios()
        registrar('api_reativacao','executado','Pausas locais removidas a pedido do proprietário; nenhuma API consultada.')
        return f'{antigos} pausa(s) locais removidas. A próxima /ia ou /pesquisar tentará uma chamada normal, sujeita a saldo e limites.'

    def disponivel(self,provedor):
        with self.mutex:return time.time()>=self.bloqueados.get(provedor,0)
    def registrar_falha(self,erro):
        duracao={'sem_creditos':24*3600,'autenticacao':24*3600,'modelo_indisponivel':24*3600,
                 'requisicao_invalida':3600,'limite_temporario':120,'servidor_ocupado':60,'rede':60}.get(erro.categoria,90)
        with self.mutex:
            self.bloqueados[erro.provedor]=time.time()+duracao
            self.motivos[erro.provedor]=erro.categoria
            self._salvar_bloqueios()
        registrar('api_'+erro.provedor,'indisponivel',str(erro),erro.provedor)
    def status(self):
        config={'Gemini':bool(os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')),
                'OpenAI':bool(os.getenv('OPENAI_API_KEY')),
                'Claude':bool(os.getenv('ANTHROPIC_API_KEY')),
                'Exa':bool(os.getenv('EXA_API_KEY'))}
        with self.mutex:
            result={}
            for nome,habilitado in config.items():
                if not habilitado:
                    result[nome]='sem chave';continue
                limite=self.bloqueados.get(nome,0)
                if limite>time.time():
                    cat=self.motivos.get(nome,'temporario')
                    descricao={'sem_creditos':'sem créditos','autenticacao':'credencial rejeitada',
                               'modelo_indisponivel':'modelo não acessível','limite_temporario':'limite temporário',
                               'servidor_ocupado':'servidor ocupado','requisicao_invalida':'requisição inválida',
                               'rede':'problema de rede','resposta_invalida':'resposta inválida'}.get(cat,'temporariamente indisponível')
                    espera=max(1,int((limite-time.time()+59)//60))
                    result[nome]=f'{descricao} — pausa local (~{espera} min)'
                else:result[nome]='configurado; não testado'
            return result
    def gemini(self,pergunta):
        chave=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        if not chave:raise FalhaAPI('Gemini',0,'Chave não configurada.','configuracao')
        try:from google import genai
        except ImportError:raise FalhaAPI('Gemini',0,'Instale google-genai.','configuracao') from None
        modelo=os.environ.get('GEMINI_MODEL','gemini-3.8-flash')
        try:
            cliente=genai.Client(api_key=chave,http_options={'timeout':18000})
            try:
                resposta=cliente.models.generate_content(model=modelo,contents=pergunta)
            finally:cliente.close()
            texto=(resposta.text or '').strip()
            if not texto:raise FalhaAPI('Gemini',0,'Resposta vazia.','temporario')
            return texto
        except FalhaAPI:raise
        except Exception as e:
            cod=getattr(e,'code',getattr(e,'status_code',0))
            try:cod=int(cod)
            except (TypeError,ValueError):cod=0
            raise analisar_erro('Gemini',cod,detalhe_seguro(e,chave)) from None
    def openai(self,pergunta):
        chave=os.environ.get('OPENAI_API_KEY')
        if not chave:raise FalhaAPI('OpenAI',0,'Chave não configurada.','configuracao')
        d=postar('https://api.openai.com/v1/chat/completions',chave,{
            'model':os.environ.get('OPENAI_MODEL','gpt-4o-mini'),
            'messages':[{'role':'system','content':'Responda em português do Brasil com precisão. Não simule execução de comandos no computador.'},
                        {'role':'user','content':pergunta[:11000]}]},'OpenAI',{'Authorization':'Bearer '+chave})
        try:texto=d['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError):texto=None
        if not isinstance(texto,str) or not texto.strip():
            raise FalhaAPI('OpenAI',0,'Resposta sem conteúdo textual.','resposta_invalida')
        return texto.strip()
    def claude(self,pergunta):
        chave=os.environ.get('ANTHROPIC_API_KEY')
        if not chave:raise FalhaAPI('Claude',0,'Chave não configurada.','configuracao')
        d=postar('https://api.anthropic.com/v1/messages',chave,{
            'model':os.environ.get('ANTHROPIC_MODEL','claude-sonnet-4-5'),
            'max_tokens':1024,'messages':[{'role':'user','content':pergunta[:11000]}]},
            'Claude',{'x-api-key':chave,'anthropic-version':'2023-06-01'})
        conteudo=d.get('content')
        if not isinstance(conteudo,list) or any(not isinstance(x,dict) for x in conteudo):
            raise FalhaAPI('Claude',0,'Resposta sem conteúdo textual.','resposta_invalida')
        textos=[x.get('text') for x in conteudo if x.get('type')=='text']
        if not textos or any(not isinstance(x,str) for x in textos) or not ''.join(textos).strip():
            raise FalhaAPI('Claude',0,'Resposta sem conteúdo textual.','resposta_invalida')
        return ''.join(textos).strip()
    def pesquisa_exa(self,consulta):
        chave=os.environ.get('EXA_API_KEY')
        if not chave:raise FalhaAPI('Exa',0,'Chave não configurada.','configuracao')
        d=postar('https://api.exa.ai/search',chave,{
            'query':consulta[:450],'numResults':4,'contents':{'text':{'maxCharacters':550}}},
            'Exa',{'x-api-key':chave})
        itens=d.get('results')
        if not isinstance(itens,list) or any(not isinstance(x,dict) for x in itens):
            raise FalhaAPI('Exa',0,'Resposta de pesquisa inválida.','resposta_invalida')
        if not itens:return 'A pesquisa não encontrou resultados.'
        saida=[]
        for i,item in enumerate(itens[:4],1):
            titulo=str(item.get('title','Sem título'))[:160]
            url=str(item.get('url',''))
            if not url.startswith('https://'):url=''
            trecho=re.sub(r'\s+',' ',str(item.get('text') or ''))[:250]
            saida.append(f'{i}. {titulo}\n{url}\n{trecho}')
        return '\n\n'.join(saida)
    def responder(self,pergunta,pesquisa=False):
        if pesquisa:
            prov='Exa'
            if not self.disponivel(prov):raise FalhaAPI(prov,0,'Pesquisa temporariamente suspensa.','suspenso')
            try:
                texto=self.pesquisa_exa(pergunta)
                self.ultimo_provedor=prov
                self._registrar_sucesso(prov)
                registrar('pesquisa','sucesso',pergunta[:120],prov)
                return texto,prov
            except FalhaAPI as e:
                if e.categoria!='configuracao':self.registrar_falha(e)
                raise
        falhas=[]
        for prov,fn,chave in [('Gemini',self.gemini,'GEMINI_API_KEY'),('OpenAI',self.openai,'OPENAI_API_KEY'),('Claude',self.claude,'ANTHROPIC_API_KEY')]:
            if prov=='Gemini' and not (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')):continue
            if prov!='Gemini' and not os.environ.get(chave):continue
            if not self.disponivel(prov):continue
            try:
                texto=fn(pergunta)
                if not texto:raise FalhaAPI(prov,0,'Resposta vazia')
                self.ultimo_provedor=prov
                self._registrar_sucesso(prov)
                registrar('pergunta','sucesso',pergunta[:120],prov)
                return texto,prov
            except FalhaAPI as e:
                self.registrar_falha(e)
                falhas.append(f'{prov}: {e.categoria}')
            except Exception as e:
                self.registrar_falha(FalhaAPI(prov,0,str(redigir(e))[:180]))
                falhas.append(f'{prov}: falha inesperada')
        explicacao=', '.join(falhas) if falhas else 'sem provedores habilitados ou todos em pausa local'
        raise FalhaAPI('Multi-IA',0,'Nenhuma API de resposta disponível: '+explicacao+'. Confira /verificar e créditos; comandos locais continuam funcionando.','indisponivel')
