"""Roteamento de perguntas. Exa só para pesquisa explícita, nunca para decidir ações.
Limites e créditos são distinguidos. Provedores sem créditos ficam suspensos na sessão.
"""
from __future__ import annotations
import json
import ipaddress
import math
import os
import re
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
from nucleo import registrar,redigir,gravar_json,ler_json

LIMITE_RESPOSTA=2_000_000
DESCRICOES_FALHA={
    'sem_creditos':'sem créditos','autenticacao':'credencial rejeitada',
    'modelo_indisponivel':'modelo não acessível','limite_temporario':'limite temporário',
    'servidor_ocupado':'servidor ocupado','requisicao_invalida':'requisição inválida',
    'rede':'problema de rede','resposta_invalida':'resposta inválida',
    'configuracao':'configuração incompleta','temporario':'falha temporária',
    'cota_temporaria':'cota de uso temporariamente esgotada',
}
SISTEMA='Responda em português do Brasil com precisão. Não simule execução de comandos no computador.'
PROVEDORES_RESPOSTA=('Gemini','OpenAI','Claude','Ollama')

def limitar_retry(valor):
    try:
        if isinstance(valor,dict):valor=float(valor.get('seconds',0))+float(valor.get('nanos',0))/1_000_000_000
        elif isinstance(valor,str):
            valor=valor.strip()
            if valor.endswith('s'):valor=valor[:-1]
        segundos=float(valor)
        if not math.isfinite(segundos) or segundos<=0:return None
        return max(1,min(3600,segundos))
    except (TypeError,ValueError,OverflowError):return None

def preparar_mensagens(pergunta,historico=None):
    """Mantém só turnos anteriores user/assistant, limitados e sem credenciais."""
    atual=str(redigir(str(pergunta)))[:11000]
    if not atual.strip():raise ValueError('Digite uma pergunta.')
    if historico is not None and not isinstance(historico,list):raise ValueError('Histórico deve ser uma lista de mensagens.')
    anteriores=[]
    saldo=24000-len(atual)
    for item in reversed((historico or [])[-19:]):
        if not isinstance(item,dict) or item.get('role') not in ('user','assistant') or not isinstance(item.get('content'),str):continue
        texto=str(redigir(item['content']))[:11000]
        if not texto.strip() or saldo<=0:continue
        texto=texto[-saldo:]
        anteriores.append({'role':item['role'],'content':texto})
        saldo-=len(texto)
    return list(reversed(anteriores))+[{'role':'user','content':atual}]

def endpoint_ollama():
    """Aceita somente IP literal loopback; nenhum hostname será resolvido."""
    base=os.getenv('OLLAMA_URL','http://127.0.0.1:11434')
    try:
        url=urlsplit(base)
        if base!=base.strip() or any(c.isspace() for c in base):raise ValueError()
        if url.scheme not in ('http','https') or url.username or url.password or '?' in base or '#' in base:raise ValueError()
        if url.path not in ('','/') or '%' in (url.hostname or ''):raise ValueError()
        ip=ipaddress.ip_address(url.hostname or '')
        if not ip.is_loopback:raise ValueError()
        porta=url.port if url.port is not None else (443 if url.scheme=='https' else 80)
        if not 1<=porta<=65535:raise ValueError()
        host=f'[{ip.compressed}]' if ip.version==6 else ip.compressed
        return f'{url.scheme}://{host}:{porta}/api/chat'
    except ValueError:
        raise FalhaAPI('Ollama',0,'OLLAMA_URL deve apontar para um IP loopback literal, como http://127.0.0.1:11434, sem credenciais ou caminho.','configuracao') from None

class SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise FalhaAPI('Ollama',0,'Redirecionamento do servidor local bloqueado.','configuracao')

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
    retry_after: float | None=None
    def __str__(self):return f'{self.provedor} ({self.codigo}/{self.categoria}): {self.detalhe}'

def analisar_erro(provedor,codigo,corpo,retry_after=None):
    e={}
    try:
        payload=json.loads(corpo)
        e=payload.get('error',payload)
        tipo=' '.join(str(e.get(campo) or '') for campo in ('type','code','status'))
        msg=str(e.get('message') or e.get('status') or corpo)
    except (ValueError,AttributeError,TypeError):tipo='';msg=str(corpo)
    low=(tipo+' '+msg).lower()
    credito=any(x in low for x in ('no credits','credit balance','purchase credits','saldo insuficiente','credits remaining','credit_balance_exhausted'))
    if provedor!='Gemini' and 'insufficient_quota' in low:credito=True
    if codigo==404: cat='modelo_indisponivel'
    elif codigo==401 or codigo==403: cat='autenticacao'
    elif codigo in (500,502,503,504,529):cat='servidor_ocupado'
    elif codigo==402 or credito:
        cat='sem_creditos'
    elif provedor=='Gemini' and any(x in low for x in ('resource_exhausted','quota exceeded','free_tier','requests_per_day')):
        cat='cota_temporaria'
    elif codigo==429: cat='limite_temporario'
    elif codigo==400:cat='requisicao_invalida'
    else:cat='temporario'
    espera=limitar_retry(retry_after)
    if espera is None and isinstance(e,dict):
        espera=limitar_retry(e.get('retry_after') or e.get('retryAfter'))
        detalhes=e.get('details',[])
        if isinstance(detalhes,list):
            for item in detalhes[:20]:
                if isinstance(item,dict):
                    espera=espera or limitar_retry(item.get('retryDelay'))
    return FalhaAPI(provedor,codigo,str(redigir(msg))[:250],cat,espera)

def postar(url,chave,payload,provedor,headers=None,timeout=18,opener=None):
    cab={'Content-Type':'application/json'}
    cab.update(headers or {})
    req=urllib.request.Request(url,json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers=cab,method='POST')
    try:
        abrir=urllib.request.urlopen if opener is None else opener.open
        with abrir(req,timeout=timeout) as resposta:
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
        retry=e.headers.get('Retry-After') if e.headers else None
        if retry and limitar_retry(retry) is None:
            try:retry=parsedate_to_datetime(retry).timestamp()-time.time()
            except (TypeError,ValueError,OverflowError):retry=None
        try:corpo=e.read(12000).decode('utf-8','replace')
        finally:e.close()
        raise analisar_erro(provedor,e.code,detalhe_seguro(corpo,chave),retry_after=retry) from None
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        raise FalhaAPI(provedor,0,detalhe_seguro(e,chave)[:150],'rede') from None

class Roteador:
    def __init__(self):
        self.bloqueados={}
        self.motivos={}
        self.falhas={}
        self.sucessos={}
        self.ultimo_provedor='local'
        self.mutex=threading.RLock()
        self._recuperar_bloqueios()
    def _recuperar_bloqueios(self):
        """Restaura somente bloqueios com prazo válido, sem carregar credenciais."""
        try:
            dados=ler_json('estado_ia.json',{})
            if not isinstance(dados,dict):return
            for nome,item in dados.items():
                if nome not in (*PROVEDORES_RESPOSTA,'Exa') or not isinstance(item,dict):continue
                try:limite=float(item.get('ate',0))
                except (ValueError,TypeError):continue
                categoria=str(item.get('categoria','temporario'))
                if categoria not in DESCRICOES_FALHA:categoria='temporario'
                if time.time()<limite<time.time()+86460:
                    self.bloqueados[nome]=limite
                    self.motivos[nome]=categoria
                    codigo=item.get('codigo')
                    if not isinstance(codigo,int) or not 0<=codigo<=599:codigo=None
                    quando=item.get('falha_em')
                    if not isinstance(quando,(int,float)) or not 0<quando<=time.time()+60:quando=None
                    self.falhas[nome]={'categoria':categoria,'codigo':codigo,'falha_em':quando}
        except (ValueError,TypeError,OSError):pass

    def _salvar_bloqueios(self):
        try:
            gravar_json('estado_ia.json',{nome:{'ate':ate,'categoria':self.motivos.get(nome,'temporario'),
                                             'codigo':self.falhas.get(nome,{}).get('codigo'),
                                             'falha_em':self.falhas.get(nome,{}).get('falha_em')}
                         for nome,ate in self.bloqueados.items() if ate>time.time()})
        except (OSError,ValueError):pass

    def _registrar_sucesso(self,provedor):
        with self.mutex:
            self.bloqueados.pop(provedor,None)
            self.motivos.pop(provedor,None)
            self.sucessos[provedor]=time.time()
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
                 'requisicao_invalida':3600,'limite_temporario':120,'cota_temporaria':120,
                 'servidor_ocupado':60,'rede':60}.get(erro.categoria,90)
        if erro.categoria in ('limite_temporario','cota_temporaria','servidor_ocupado'):
            duracao=limitar_retry(erro.retry_after) or duracao
        with self.mutex:
            agora=time.time()
            self.bloqueados[erro.provedor]=agora+duracao
            self.motivos[erro.provedor]=erro.categoria
            self.falhas[erro.provedor]={'categoria':erro.categoria,'codigo':erro.codigo,'falha_em':agora}
            self._salvar_bloqueios()
        registrar('api_'+erro.provedor,'indisponivel',str(erro),erro.provedor)
    def _configurados(self):
        config={'Gemini':bool(os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')),
                'OpenAI':bool(os.getenv('OPENAI_API_KEY')),
                'Claude':bool(os.getenv('ANTHROPIC_API_KEY')),
                'Exa':bool(os.getenv('EXA_API_KEY'))}
        if os.getenv('OLLAMA_HABILITADO')=='1':config['Ollama']=True
        return config

    def estado_local(self):
        """Snapshot sem rede, chaves ou mensagens: épocas em segundos UTC.

        A pausa pode expirar sem nova consulta. Apenas sucesso_em registra uma
        resposta válida nesta sessão; compare-o com falha_em para a cronologia.
        """
        config=self._configurados()
        agora=time.time()
        with self.mutex:
            estados={}
            for nome,configurado in config.items():
                falha=self.falhas.get(nome,{})
                ate=self.bloqueados.get(nome,0)
                espera=max(0,math.ceil(ate-agora))
                estados[nome]={'configurado':configurado,'em_pausa':espera>0,
                    'categoria':falha.get('categoria'),'codigo':falha.get('codigo'),
                    'falha_em':falha.get('falha_em'),'pausa_ate':ate or None,
                    'espera_segundos':espera,'sucesso_em':self.sucessos.get(nome)}
            return estados

    def _explicar_indisponibilidade(self,nome,estado):
        if not estado['configurado']:
            if nome=='Ollama':return 'Ollama: integração local desabilitada; configure um modelo local antes de habilitar.'
            return nome+': sem chave configurada.'
        categoria=estado['categoria'] or 'temporario'
        causa=DESCRICOES_FALHA.get(categoria,'falha temporária')
        codigo=estado['codigo']
        if codigo:causa+=f' (HTTP {codigo})'
        espera=estado['espera_segundos']
        if espera:
            minutos=math.ceil(espera/60)
            tempo=f'{espera} s' if espera<60 else f'{minutos} min'
            if minutos>=60:tempo=f'{minutos//60} h {minutos%60} min'
            causa+=f'; pausa local por mais {tempo}'
        if categoria=='sem_creditos':
            orientacao='Confira saldo/faturamento desse provedor; após corrigir, use /reativar_ias.'
        elif categoria=='autenticacao':
            orientacao='Confira a credencial desse provedor; após corrigir, use /reativar_ias.'
        elif categoria=='modelo_indisponivel':
            orientacao='Confira o nome e o acesso ao modelo; após corrigir, use /reativar_ias.'
        elif categoria=='configuracao':
            orientacao='Use /verificar para conferir a configuração local.'
        elif espera:
            orientacao='Aguarde essa pausa e envie uma nova solicitação.'
        else:
            orientacao='A última falha ainda não foi verificada por uma nova resposta.'
        return f'{nome}: {causa}. {orientacao}'

    def status(self):
        config=self._configurados()
        with self.mutex:
            result={}
            for nome,habilitado in config.items():
                if not habilitado:
                    result[nome]='sem chave';continue
                limite=self.bloqueados.get(nome,0)
                if limite>time.time():
                    cat=self.motivos.get(nome,'temporario')
                    descricao=(DESCRICOES_FALHA.get(cat,'temporariamente indisponível')
                               if cat not in ('temporario','configuracao') else 'temporariamente indisponível')
                    espera=max(1,int((limite-time.time()+59)//60))
                    result[nome]=f'{descricao} — pausa local (~{espera} min)'
                else:result[nome]='configurado; não testado'
            return result
    def gemini(self,pergunta,historico=None):
        chave=os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        if not chave:raise FalhaAPI('Gemini',0,'Chave não configurada.','configuracao')
        try:from google import genai
        except ImportError:raise FalhaAPI('Gemini',0,'Instale google-genai.','configuracao') from None
        modelo=os.environ.get('GEMINI_MODEL','gemini-3.8-flash')
        try:
            cliente=genai.Client(api_key=chave,http_options={'timeout':18000})
            try:
                mensagens=preparar_mensagens(pergunta,historico)
                conteudo=[{'role':'model' if x['role']=='assistant' else 'user','parts':[{'text':x['content']}]} for x in mensagens]
                resposta=cliente.models.generate_content(model=modelo,contents=conteudo,config={'system_instruction':SISTEMA})
            finally:cliente.close()
            texto=(resposta.text or '').strip()
            if not texto:raise FalhaAPI('Gemini',0,'Resposta vazia.','temporario')
            return texto
        except FalhaAPI:raise
        except Exception as e:
            cod=getattr(e,'code',getattr(e,'status_code',0))
            try:cod=int(cod)
            except (TypeError,ValueError):cod=0
            payload=getattr(e,'response_json',None)
            corpo=json.dumps(payload) if isinstance(payload,dict) else str(e)
            raise analisar_erro('Gemini',cod,detalhe_seguro(corpo,chave)) from None
    def openai(self,pergunta,historico=None):
        chave=os.environ.get('OPENAI_API_KEY')
        if not chave:raise FalhaAPI('OpenAI',0,'Chave não configurada.','configuracao')
        d=postar('https://api.openai.com/v1/chat/completions',chave,{
            'model':os.environ.get('OPENAI_MODEL','gpt-4o-mini'),
            'messages':[{'role':'system','content':SISTEMA}]+preparar_mensagens(pergunta,historico)},'OpenAI',{'Authorization':'Bearer '+chave})
        try:texto=d['choices'][0]['message']['content']
        except (KeyError,IndexError,TypeError):texto=None
        if not isinstance(texto,str) or not texto.strip():
            raise FalhaAPI('OpenAI',0,'Resposta sem conteúdo textual.','resposta_invalida')
        return texto.strip()
    def claude(self,pergunta,historico=None):
        chave=os.environ.get('ANTHROPIC_API_KEY')
        if not chave:raise FalhaAPI('Claude',0,'Chave não configurada.','configuracao')
        d=postar('https://api.anthropic.com/v1/messages',chave,{
            'model':os.environ.get('ANTHROPIC_MODEL','claude-sonnet-4-5'),
            'max_tokens':1024,'system':SISTEMA,'messages':preparar_mensagens(pergunta,historico)},
            'Claude',{'x-api-key':chave,'anthropic-version':'2023-06-01'})
        conteudo=d.get('content')
        if not isinstance(conteudo,list) or any(not isinstance(x,dict) for x in conteudo):
            raise FalhaAPI('Claude',0,'Resposta sem conteúdo textual.','resposta_invalida')
        textos=[x.get('text') for x in conteudo if x.get('type')=='text']
        if not textos or any(not isinstance(x,str) for x in textos) or not ''.join(textos).strip():
            raise FalhaAPI('Claude',0,'Resposta sem conteúdo textual.','resposta_invalida')
        return ''.join(textos).strip()
    def catalogo_ollama(self):
        """Leitura explícita do serviço no PC; não gera respostas nem baixa modelos."""
        from configurar_ia_local import listar_catalogo, FalhaConfiguracao
        base=endpoint_ollama().removesuffix('/api/chat')
        try:modelos=listar_catalogo(base)
        except FalhaConfiguracao as exc:
            raise FalhaAPI('Ollama',0,str(exc),'configuracao') from None
        return {'modelos':modelos,'padrao':os.getenv('OLLAMA_MODEL','qwen2.5:3b').strip(),
                'habilitado':os.getenv('OLLAMA_HABILITADO')=='1'}

    def ollama(self,pergunta,historico=None,modelo=None):
        if os.getenv('OLLAMA_HABILITADO')!='1':
            raise FalhaAPI('Ollama',0,'Integração local desabilitada. Configure Ollama e habilite OLLAMA_HABILITADO=1.','configuracao')
        endpoint=endpoint_ollama()
        from configurar_ia_local import validar_modelo
        modelo=os.getenv('OLLAMA_MODEL','qwen2.5:3b').strip() if modelo is None else modelo
        try:modelo=validar_modelo(modelo)
        except ValueError:
            raise FalhaAPI('Ollama',0,'OLLAMA_MODEL inválido; informe o nome de um modelo instalado.','configuracao')
        try:timeout=float(os.getenv('OLLAMA_TIMEOUT','90'))
        except ValueError:timeout=90
        if not math.isfinite(timeout):timeout=90
        timeout=max(5,min(120,timeout))
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),SemRedirecionamento())
        dados=postar(endpoint,'',{'model':modelo,'stream':False,
            'messages':[{'role':'system','content':SISTEMA}]+preparar_mensagens(pergunta,historico)},
            'Ollama',timeout=timeout,opener=opener)
        mensagem=dados.get('message')
        texto=mensagem.get('content') if isinstance(mensagem,dict) else None
        if not isinstance(texto,str) or not texto.strip():
            raise FalhaAPI('Ollama',0,'O servidor local retornou resposta sem conteúdo textual.','resposta_invalida')
        return texto.strip()
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
    def _selecionar_provedor(self,provedor,permitir_todos=False):
        nomes={nome.lower():nome for nome in (*PROVEDORES_RESPOSTA,'Exa')}
        valor=str(provedor).strip().lower()
        if valor=='auto':return 'todos' if permitir_todos else 'auto'
        if permitir_todos and valor=='todos':return 'todos'
        if valor not in nomes:raise ValueError('Provedor inválido. Escolha auto, Gemini, OpenAI, Claude ou Ollama.')
        return nomes[valor]

    def verificar_conexoes(self,provedor='todos'):
        """Solicitação explícita: no máximo uma chamada por provedor configurado.

        Pode consumir cota. Não consulta saldo, não instala modelos e não usa
        fallback nem repetição automática. A chamada explícita verifica também
        provedores que estavam em pausa local, sem contornar limites remotos.
        """
        escolhido=self._selecionar_provedor(provedor,permitir_todos=True)
        config=self._configurados()
        nomes=list(config) if escolhido=='todos' else [escolhido]
        funcoes={'Gemini':self.gemini,'OpenAI':self.openai,'Claude':self.claude,
                 'Ollama':self.ollama,'Exa':self.pesquisa_exa}
        resultado={}
        for nome in nomes:
            if not config.get(nome,False):
                resultado[nome]={'ok':False,'categoria':'configuracao','codigo':0,
                    'mensagem':'Integração local desabilitada.' if nome=='Ollama' else 'Chave não configurada.',
                    'verificado_em':None}
                continue
            try:
                texto=funcoes[nome]('Python documentação oficial' if nome=='Exa' else 'Responda somente OK.')
                if not isinstance(texto,str) or not texto.strip():
                    raise FalhaAPI(nome,0,'Resposta vazia.','resposta_invalida')
                self._registrar_sucesso(nome)
                registrar('teste_conexao','sucesso','Resposta recebida nesta solicitação explícita.',nome)
                resultado[nome]={'ok':True,'categoria':'sucesso','codigo':200,
                    'mensagem':'Resposta recebida nesta solicitação; isso não informa créditos disponíveis.',
                    'verificado_em':time.time()}
            except Exception as exc:
                erro=exc if isinstance(exc,FalhaAPI) else FalhaAPI(nome,0,str(redigir(exc))[:180])
                self.registrar_falha(erro)
                resultado[nome]={'ok':False,'categoria':erro.categoria,'codigo':erro.codigo,
                    'mensagem':DESCRICOES_FALHA.get(erro.categoria,'falha temporária')+
                        (f' (HTTP {erro.codigo})' if erro.codigo else ''),
                    'verificado_em':time.time()}
        return resultado

    def responder(self,pergunta,pesquisa=False,historico=None,provedor='auto',modelo_ollama=None):
        escolhido=self._selecionar_provedor(provedor)
        if modelo_ollama is not None:
            from configurar_ia_local import validar_modelo
            modelo_ollama=validar_modelo(modelo_ollama)
            if escolhido!='Ollama' or pesquisa:
                raise ValueError('Selecione Ollama para escolher um modelo dessa integração.')
        mensagens=preparar_mensagens(pergunta,historico)
        pergunta=mensagens[-1]['content']
        if historico is not None:historico=mensagens[:-1]
        if modelo_ollama is not None:
            # Uma consulta explícita ao modelo escolhido. Falhas de um modelo
            # cloud não pausam outro modelo nem alteram o estado do padrão.
            try:
                texto=self.ollama(pergunta,historico=historico,modelo=modelo_ollama)
                self.ultimo_provedor='Ollama'
                registrar('pergunta','sucesso','Modelo '+modelo_ollama+'; '+pergunta[:120],'Ollama')
                return texto,'Ollama'
            except FalhaAPI as exc:
                registrar('api_Ollama','indisponivel','Modelo '+modelo_ollama+'; '+str(exc),'Ollama')
                raise FalhaAPI('Ollama',exc.codigo,'Modelo '+modelo_ollama+': '+exc.detalhe,
                               exc.categoria,exc.retry_after) from None
        if pesquisa:
            if escolhido not in ('auto','Exa'):raise ValueError('Pesquisa usa Exa; escolha auto ou Exa.')
            prov='Exa'
            if not self.disponivel(prov):
                estado=self.estado_local()[prov]
                raise FalhaAPI(prov,estado['codigo'] or 0,self._explicar_indisponibilidade(prov,estado),'suspenso')
            try:
                texto=self.pesquisa_exa(pergunta)
                self.ultimo_provedor=prov
                self._registrar_sucesso(prov)
                registrar('pesquisa','sucesso',pergunta[:120],prov)
                return texto,prov
            except FalhaAPI as e:
                if e.categoria!='configuracao':self.registrar_falha(e)
                raise
        if escolhido=='Exa':raise ValueError('Exa atende somente pesquisas explícitas.')
        config=self._configurados()
        selecionados=[escolhido] if escolhido!='auto' else [nome for nome in PROVEDORES_RESPOSTA
                            if nome!='Ollama' or config.get('Ollama',False)]
        funcoes={'Gemini':self.gemini,'OpenAI':self.openai,'Claude':self.claude,'Ollama':self.ollama}
        for prov in selecionados:
            if not config.get(prov,False) or not self.disponivel(prov):continue
            try:
                texto=funcoes[prov](pergunta) if historico is None else funcoes[prov](pergunta,historico=historico)
                if not isinstance(texto,str) or not texto.strip():raise FalhaAPI(prov,0,'Resposta vazia.','resposta_invalida')
                self.ultimo_provedor=prov
                self._registrar_sucesso(prov)
                registrar('pergunta','sucesso',pergunta[:120],prov)
                return texto,prov
            except FalhaAPI as e:
                self.registrar_falha(e)
            except Exception as e:
                self.registrar_falha(FalhaAPI(prov,0,str(redigir(e))[:180]))
        estados=self.estado_local()
        explicacao='\n'.join(self._explicar_indisponibilidade(nome,estados.get(nome,{'configurado':False})) for nome in selecionados)
        if escolhido=='auto' and estados['Exa']['configurado']:
            explicacao+='\nExa atende apenas /pesquisar; não substitui as APIs de resposta.'
        raise FalhaAPI('Multi-IA',0,'Nenhuma API de resposta disponível.\n'+explicacao+
            '\nNenhuma nova tentativa foi agendada. Os comandos locais continuam disponíveis.','indisponivel')
