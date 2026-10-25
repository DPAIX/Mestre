"""Prepara e inicia o MeuControlePC por uma janela local, sem perguntas por etapa.

Credenciais ficam no .env externo. A interface retorna somente estado público;
login, 2FA e consentimentos dos provedores permanecem decisões da conta.
"""
from __future__ import annotations
import argparse
import copy
from dataclasses import dataclass
import datetime as dt
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import urllib.error
import webbrowser

VERSAO='2.11.0'
BASE=Path(__file__).resolve().parent
MAX_CORPO=16384
MODULOS=('telebot','google.genai','psutil','PIL','pyautogui','faster_whisper','googleapiclient','google_auth_oauthlib')
CHAVES=frozenset({'GEMINI_API_KEY','OPENAI_API_KEY','ANTHROPIC_API_KEY','TELEGRAM_TOKEN','TELEGRAM_ALLOWED_USER_IDS'})
OPCOES=CHAVES|frozenset({'GOOGLE_API_KEY','OLLAMA_HABILITADO','OLLAMA_INICIAR_SERVICO','OLLAMA_URL','OLLAMA_MODEL',
    'OLLAMA_PERFIL','OLLAMA_NUVEM_HABILITADA','GEMINI_API_MODO','GEMINI_MODEL','NINE_ROUTER_HABILITADO','NINE_ROUTER_URL',
    'NINE_ROUTER_MODEL','NINE_ROUTER_API_KEY','VOZ_PROVEDOR','VOZ_MODELO_LOCAL','MEMORIA_HABILITADA','PAINEL_PORTA'})


@dataclass(frozen=True)
class Caminhos:
    origem: Path
    codigo: Path
    arquivo_env: Path
    dados: Path
    preparacao: Path
    backups: Path
    manifesto: Path


def _seguro(caminho):
    caminho=Path(caminho)
    if not caminho.is_absolute():raise ValueError('Use caminhos absolutos para a instalação.')
    for parte in (caminho,*caminho.parents):
        if parte.is_symlink():raise ValueError('A instalação não pode seguir links ou junctions.')
        if parte.exists():
            m=parte.lstat()
            if getattr(m,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0):
                raise ValueError('A instalação não pode seguir links ou junctions.')
    return caminho


def caminhos(origem=None,codigo=None,arquivo_env=None,dados=None):
    fonte=_seguro(Path(origem or BASE).absolute())
    perfil=Path(os.environ.get('USERPROFILE',str(Path.home())))
    destino=_seguro(Path(codigo) if codigo else perfil/'Documents'/'GitHub'/'Mestre')
    if arquivo_env is None:
        escolhido=os.environ.get('MEUCONTROLEPC_ENV')
        if escolhido:arquivo_env=Path(escolhido)
        elif Path('F:/').is_dir():arquivo_env=Path('F:/MeuControlePC_v2/.env')
        else:arquivo_env=Path(os.environ.get('LOCALAPPDATA',str(perfil/'AppData'/'Local')))/'MeuControlePC'/'.env'
    env=_seguro(Path(arquivo_env));seletor_dados=dados or os.environ.get('MEUCONTROLEPC_DADOS')
    pasta=_seguro(Path(seletor_dados) if seletor_dados else env.parent/'dados')
    if env.is_relative_to(destino) or pasta.is_relative_to(destino):
        raise ValueError('Configuração e dados precisam ficar fora das fontes.')
    if not pasta.exists() and (destino/'dados').exists():
        raise ValueError('Há dados legados no código. Selecione os dados externos existentes antes de continuar.')
    return Caminhos(fonte,destino,env,pasta,_seguro(env.parent/'preparacao'),
                    _seguro(env.parent/'backups_codigo'),fonte/'manifesto_instalacao.json')


def _json_gravar(arquivo,dados):
    arquivo.parent.mkdir(parents=True,exist_ok=True)
    tmp=arquivo.with_name('.'+arquivo.name+'.'+secrets.token_hex(8)+'.tmp')
    try:
        with tmp.open('w',encoding='utf-8') as f:
            json.dump(dados,f,ensure_ascii=False,allow_nan=False);f.flush();os.fsync(f.fileno())
        os.replace(tmp,arquivo)
    finally:tmp.unlink(missing_ok=True)


def _ler_estado(arquivo):
    try:
        _seguro(arquivo)
        if not arquivo.is_file() or arquivo.stat().st_size>100000:return {}
        valor=json.loads(arquivo.read_text(encoding='utf-8'))
        return valor if isinstance(valor,dict) else {}
    except (ValueError,OSError):return {}


def _ambiente(ctx):
    permitidas={'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','USERPROFILE',
        'HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA','PROGRAMFILES','PROGRAMFILES(X86)',
        'PROGRAMDATA','TEMP','TMP','LANG','LC_ALL','NUMBER_OF_PROCESSORS','PROCESSOR_ARCHITECTURE',
        'OLLAMA_MODELS','OLLAMA_NO_CLOUD'}
    env={k:v for k,v in os.environ.items() if k.upper() in permitidas}
    env.update(MEUCONTROLEPC_ENV=str(ctx.arquivo_env),MEUCONTROLEPC_DADOS=str(ctx.dados),PYTHONUTF8='1')
    return env


def _python(ctx):
    return next((p for p in (ctx.codigo/'.venv'/'Scripts'/'python.exe',ctx.arquivo_env.parent/'.venv'/'Scripts'/'python.exe') if p.is_file()),Path(sys.executable))


def _filho(ctx,python,argumentos,timeout=30):
    r=subprocess.run([str(python),*argumentos],cwd=str(ctx.codigo),env=_ambiente(ctx),shell=False,
        stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        encoding='utf-8',errors='replace',timeout=timeout,check=False)
    if len(r.stdout)>2000000:raise RuntimeError('Resposta de verificação excedeu o limite.')
    return r


def _dependencias(ctx,python):
    programa=("import importlib.util,importlib.metadata,json; "
        "nomes=['telebot','google.genai','psutil','PIL','pyautogui','faster_whisper','googleapiclient','google_auth_oauthlib']; "
        "faltam=[]\nfor n in nomes:\n try: ok=importlib.util.find_spec(n) is not None\n except (ImportError,ValueError): ok=False\n if not ok: faltam.append(n)\n"
        "try:\n v=tuple(int(p) for p in importlib.metadata.version('google-genai').split('.')[:2]); "
        "ok=(2,9)<=v<(3,0)\nexcept Exception: ok=False\n"
        "if not ok and 'google.genai' not in faltam: faltam.append('google.genai')\n"
        "print(json.dumps({'faltam':faltam}))")
    r=_filho(ctx,python,['-c',programa],30)
    if r.returncode:return False
    try:return json.loads(r.stdout)['faltam']==[]
    except (ValueError,KeyError,TypeError):return False


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def _aguardar_gateway_http(url=None):
    """Espera limitada pelo HTTP local; não cria chaves nem testa inferência.

    A disponibilidade HTTP não comprova identidade, contas ou cota. A ponte
    oficial verifica esses requisitos depois, uma vez, sem repetir POSTs.
    """
    from roteador_9router import validar_url,URL_PADRAO
    from multi_ia import FalhaAPI
    try:base=validar_url(url if url is not None else os.getenv('NINE_ROUTER_URL',URL_PADRAO))
    except (ValueError,TypeError,FalhaAPI):return False
    # Loopback não passa pelo proxy do sistema nem herda cookies/autorização.
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_SemRedirecionamento())
    pedido=urllib.request.Request(base+'/models',headers={'Accept':'application/json'},method='GET')
    fim=time.monotonic()+25
    for _ in range(32):
        restante=fim-time.monotonic()
        if restante<=0:return False
        try:
            with opener.open(pedido,timeout=min(2,restante)) as resposta:
                if 200<=resposta.status<300:return True
        except urllib.error.HTTPError as erro:
            codigo=erro.code;erro.close()
            if codigo in (401,403):return True
            if 300<=codigo<400:return False
        except (OSError,ValueError,urllib.error.URLError):pass
        restante=fim-time.monotonic()
        if restante<=0:return False
        time.sleep(min(.8,restante))
    return False


def _verificar_conta(servico,chave):
    """Uma leitura de metadados, sem geração ou devolução de credencial."""
    if servico not in ('telegram','gemini') or not isinstance(chave,str) or not chave:
        return {'ok':False,'codigo':0}
    if servico=='telegram':
        from configurar_telegram import validar_token
        if not validar_token(chave):return {'ok':False,'codigo':0}
        url='https://api.telegram.org/bot'+chave+'/getMe';headers={}
    else:
        url='https://generativelanguage.googleapis.com/v1beta/models?pageSize=1'
        headers={'x-goog-api-key':chave}
    try:
        pedido=urllib.request.Request(url,headers=headers)
        opener=urllib.request.build_opener(_SemRedirecionamento())
        with opener.open(pedido,timeout=7) as r:
            bruto=r.read(100001)
            if len(bruto)>100000:return {'ok':False,'codigo':0}
            d=json.loads(bruto)
        ok=(d.get('ok') is True and isinstance(d.get('result'),dict) and d['result'].get('is_bot') is True
            if servico=='telegram' else isinstance(d.get('models'),list))
        return {'ok':ok,'codigo':200}
    except urllib.error.HTTPError as erro:
        codigo=erro.code;erro.close();return {'ok':False,'codigo':codigo}
    except Exception:return {'ok':False,'codigo':0}


def _falha_conta(codigo):
    if codigo in (401,403):return 'A API recusou a autenticação ou a permissão do projeto; confira a conta e a chave.'
    if codigo==404:return 'A rota de metadados não foi encontrada; o acesso à API continua não confirmado.'
    if codigo==429:return 'A API informou limite ou cota; a chave foi preservada e não houve nova tentativa.'
    if isinstance(codigo,int) and 500<=codigo<=599:return 'O serviço da API está indisponível; não houve nova tentativa.'
    return 'A conexão com a API não foi confirmada; a chave foi preservada.'


def _instalar_ollama_ausente(ctx):
    """Uma instalação oficial, apenas quando o início local está autorizado.

    Não baixa modelos de conversa e nunca usa a presença de uma porta ocupada
    como autorização para reinstalar ou parar o serviço existente.
    """
    if (sys.platform!='win32' or os.getenv('OLLAMA_HABILITADO')!='1'
            or os.getenv('OLLAMA_INICIAR_SERVICO','1')!='1'):
        return False
    import iniciar_servicos_locais as servicos
    servicos.validar_url(os.getenv('OLLAMA_URL',servicos.URL_PADRAO))
    existente=servicos._executavel_ollama()
    if existente is not None:return True
    winget=shutil.which('winget.exe')
    if not winget:return False
    retorno=subprocess.run([winget,'install','--id','Ollama.Ollama','--exact',
        '--source','winget','--scope','user','--silent',
        '--accept-package-agreements','--accept-source-agreements','--disable-interactivity'],
        cwd=str(ctx.codigo),env=_ambiente(ctx),shell=False,stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=600,check=False)
    if retorno.returncode:return False
    existente=servicos._executavel_ollama()
    if existente is None:return False
    os.environ['PATH']=str(existente.parent)+os.pathsep+os.environ.get('PATH','')
    return True


class Preparador:
    def __init__(self,ctx):
        self.ctx=ctx;self.lock=threading.RLock();self.worker=None;self.python=_python(ctx);self._backup_feito=False
        self.estado={'versao':VERSAO,'executando':False,'finalizado':False,'etapa':'Preparando',
            'itens':[],'pendencias':[],'modelos_9router':[],'bot_iniciado':False,'painel_url':'http://127.0.0.1:8765'}

    def snapshot(self):
        with self.lock:return copy.deepcopy(self.estado)

    def item(self,ident,nome,estado,detalhe):
        with self.lock:
            self.estado['etapa']=nome
            self.estado['itens']=[i for i in self.estado['itens'] if i['id']!=ident]
            self.estado['itens'].append({'id':ident,'nome':nome,'estado':estado,'detalhe':str(detalhe)[:900]})

    def pendente(self,ident,tipo,texto,servico=''):
        with self.lock:
            self.estado['pendencias']=[p for p in self.estado['pendencias'] if p['id']!=ident]
            self.estado['pendencias'].append({'id':ident,'tipo':tipo,'texto':texto,'servico':servico})

    def iniciar(self,modelo=None):
        with self.lock:
            if self.estado['executando']:return False
            self.estado.update(executando=True,finalizado=False,pendencias=[],modelos_9router=[])
            self._backup_feito=False
            self.worker=threading.Thread(target=self._executar,args=(modelo,),daemon=True);self.worker.start()
            return True

    def _configuracao(self):
        ctx=self.ctx
        for caminho in (ctx.arquivo_env,ctx.dados,ctx.backups):_seguro(caminho)
        ctx.arquivo_env.parent.mkdir(parents=True,exist_ok=True);ctx.dados.mkdir(parents=True,exist_ok=True)
        if ctx.arquivo_env.exists():
            if not ctx.arquivo_env.is_file() or ctx.arquivo_env.stat().st_size>131072:raise ValueError('Configuração local inválida.')
            if not self._backup_feito:
                backup=ctx.backups/'configuracao';backup.mkdir(parents=True,exist_ok=True)
                alvo=backup/('.env.antes_preparacao_'+secrets.token_hex(8)+'.bak')
                with alvo.open('xb') as f:f.write(ctx.arquivo_env.read_bytes())
                self._backup_feito=True
        else:
            ctx.arquivo_env.write_text('PAINEL_PORTA=8765\nOLLAMA_HABILITADO=1\nOLLAMA_INICIAR_SERVICO=1\nOLLAMA_URL=http://127.0.0.1:11434\nVOZ_PROVEDOR=local\nMEMORIA_HABILITADA=1\n',encoding='utf-8')
        os.environ['MEUCONTROLEPC_ENV']=str(ctx.arquivo_env);os.environ['MEUCONTROLEPC_DADOS']=str(ctx.dados)
        # O leitor Ollama é deliberadamente restrito às suas próprias opções.
        # Aqui precisamos também das contas já autorizadas, sem copiá-las ao estado público.
        valores={}
        for linha in ctx.arquivo_env.read_text(encoding='utf-8-sig').splitlines():
            if '=' in linha and not linha.lstrip().startswith('#'):
                nome,valor=linha.split('=',1);nome=nome.strip()
                if nome in OPCOES:valores[nome]=valor.strip().strip('"\'')
        for nome in OPCOES:
            if nome in valores:os.environ[nome]=valores[nome]
        try:porta=int(valores.get('PAINEL_PORTA','8765'))
        except ValueError:porta=8765
        if not 1<=porta<=65535:porta=8765
        with self.lock:self.estado['painel_url']='http://127.0.0.1:'+str(porta)
        return valores

    def _componentes(self):
        ctx=self.ctx
        self.item('bibliotecas','Bibliotecas e voz','verificando','Conferindo o ambiente já instalado.')
        if _dependencias(ctx,self.python):
            r=_filho(ctx,self.python,['-m','pip','check'],60)
            if r.returncode==0:
                voz=_filho(ctx,self.python,['-c','from nucleo import ler_env;ler_env();from transcritor_local import verificar_disponibilidade;verificar_disponibilidade()'],30)
                if voz.returncode==0:
                    self.item('bibliotecas','Bibliotecas e voz','pronto','Instalação existente conferida; nenhum pacote ou peso reinstalado.');return
        self.item('bibliotecas','Bibliotecas e voz','executando','Preparando o ambiente e reaproveitando pesos existentes; pode usar Internet.')
        import preparar_inicio_automatico as preparar
        plano=preparar.planejar_preparacao(ctx.codigo,ctx.arquivo_env,ctx.dados,incluir_google=True)
        plano=preparar.preparar_componentes(plano,incluir_google=True)
        self.python=Path(plano['python'])
        self.item('bibliotecas','Bibliotecas e voz','pronto','Dependências preparadas e compatibilidade conferida.')

    def _servicos(self):
        import configuracao_assistente as config
        import integracoes_9stack as stack
        node_pronto=False
        try:
            texto=config._preparar_node()
            # O helper legado também devolve orientações de pendência. Apenas
            # a verificação concreta da versão permite continuar com npm.
            stack._node(stack._ambiente());node_pronto=True
            self.item('node','Node.js','pronto',texto)
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            self.item('node','Node.js','pendente','Node.js 22+ com npm ainda não foi confirmado; Ollama e contas continuam sendo conferidos.')
            self.item('gateway_servico','Serviço 9Router','pendente','A preparação do serviço depende de Node.js compatível. O estado de uma instância existente será conferido pelo cliente local.')
            self.item('9remote','9Remote','pendente','A preparação da interface depende de Node.js compatível; nenhum túnel foi solicitado.')
            self.pendente('node','pagina','Concluir a instalação oficial de Node.js LTS e retomar.','node_instalacao')
        if node_pronto:
            for servico in ('9router','9remote'):
                ident='gateway_servico' if servico=='9router' else '9remote'
                nome='Serviço 9Router' if servico=='9router' else '9Remote'
                try:
                    texto=config._instalar_se_pendente(servico)
                    self.item(servico,nome,'presente',texto)
                    if servico=='9router':
                        texto=stack.executar_9stack('9router','iniciar',confirmado=True)
                        self.item(ident,nome,'inicio_solicitado',texto)
                        if _aguardar_gateway_http():
                            self.item(ident,nome,'http_responde','O endpoint HTTP local respondeu. As contas, o modelo e a chave serão conferidos pela ponte oficial; geração ainda não testada.')
                        else:
                            self.item(ident,nome,'pendente','O endpoint HTTP ainda não respondeu dentro de 25 segundos. A configuração local será conferida uma vez; as outras etapas continuam.')
                    else:
                        if not getattr(self,'_9remote_abertura_solicitada',False):
                            texto=stack.executar_9stack('9remote','abrir',confirmado=True)
                            self._9remote_abertura_solicitada=True
                        else:
                            texto='A interface já foi solicitada nesta preparação. Nenhuma nova abertura ou início de túnel foi pedido.'
                        self.item(ident,nome,'interface_solicitada',texto)
                        self.pendente('9remote','pagina','Confira ou conclua o pareamento do dispositivo na interface oficial.','9remote_pareamento')
                except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                    self.item(ident,nome,'pendente','A preparação deste serviço não concluiu; as outras etapas continuam.')
                    self.pendente(ident,'pagina','Conferir o serviço na interface oficial e retomar.',
                                  '9router_contas' if servico=='9router' else '9remote_pareamento')
        from iniciar_servicos_locais import garantir_ollama
        try:
            resultado=garantir_ollama()
            if (not resultado['ok'] and resultado['mensagem'].startswith('Ollama não foi encontrado no PC.')
                    and os.getenv('OLLAMA_HABILITADO')=='1' and os.getenv('OLLAMA_INICIAR_SERVICO','1')=='1'):
                self.item('ollama','Ollama','executando','Instalando o aplicativo oficial ausente; nenhum modelo de conversa será baixado.')
                if _instalar_ollama_ausente(self.ctx):resultado=garantir_ollama()
                else:self.pendente('ollama','pagina','Concluir a instalação oficial do Ollama e retomar.','ollama_instalacao')
        except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
            resultado={'ok':False,'mensagem':'O serviço Ollama não foi confirmado. Confira a instalação existente; nenhuma instância adicional foi criada.'}
        self.item('ollama','Ollama','pronto' if resultado['ok'] else 'pendente',resultado['mensagem'])
        if resultado['ok']:
            from configurar_ia_local import listar_catalogo,usar_existente,modelo_instalado
            try:
                catalogo=listar_catalogo(os.getenv('OLLAMA_URL','http://127.0.0.1:11434'))
                atual=os.getenv('OLLAMA_MODEL','')
                if not atual or not modelo_instalado(atual,[m['nome'] for m in catalogo]):
                    escolhido=usar_existente(os.getenv('OLLAMA_URL','http://127.0.0.1:11434'),self.ctx.arquivo_env,atual or 'llama3.2:latest')
                    if escolhido is None:
                        self.item('modelos','Modelos Ollama','pendente','Nenhum modelo local foi selecionado no catálogo existente; nenhum peso foi baixado.');return
                self.item('modelos','Modelos Ollama','presente',str(len(catalogo))+' tags no catálogo; nenhuma geração ou download de modelo de conversa.')
            except (OSError,ValueError,RuntimeError):self.item('modelos','Modelos Ollama','pendente','O catálogo ainda não foi confirmado; nenhum modelo foi baixado.')

    def _gateway(self,modelo):
        from configurar_gateway_automatico import configurar_gateway
        resultado=configurar_gateway(caminho_env=self.ctx.arquivo_env,modelo=modelo,
                                      autorizado=True,selecionar_recomendado=True)
        # A ponte tem contrato público: não copiar seus campos internos/credenciais.
        estado=str(resultado.get('estado','pendente'))
        pendencias=resultado.get('pendencias',[])
        mensagem=('Chave dedicada e modelo configurados; geração/cota ainda não testadas.'
                  if resultado.get('configurado') else '\n'.join(pendencias) if pendencias else
                  'Configuração do gateway pendente; confira as contas no dashboard local.')
        self.item('gateway','Cliente 9Router',estado,mensagem)
        modelos=resultado.get('modelos',[])
        if isinstance(modelos,list):
            with self.lock:self.estado['modelos_9router']=modelos[:1000]
        if estado not in ('configurado','pronto','ja_configurado'):
            self.pendente('gateway','modelo' if modelos else 'pagina','Concluir a seleção de conversa/combo ou autenticação do dashboard.','9router_contas')

    def _contas(self,valores):
        from configurar_telegram import validar_token,validar_ids
        ids=valores.get('TELEGRAM_ALLOWED_USER_IDS','').strip()
        telegram=validar_token(valores.get('TELEGRAM_TOKEN','')) and bool(ids) and validar_ids(ids)
        falha_telegram='Token/proprietário Telegram ainda não configurados.'
        if telegram:
            confirmado=_verificar_conta('telegram',valores['TELEGRAM_TOKEN'])
            telegram=confirmado['ok']
            if not telegram:falha_telegram=_falha_conta(confirmado.get('codigo',0))
        self.item('telegram','Telegram','pronto' if telegram else 'pendente','Token confirmado por getMe e proprietários preservados.' if telegram else falha_telegram)
        if not telegram:self.pendente('telegram','chave','Concluir token e ID do Telegram no formulário local.','telegram_token')
        from configurar_gemini import salvar_configuracao,_validar_modelo
        chave=valores.get('GEMINI_API_KEY') or valores.get('GOOGLE_API_KEY')
        if chave:
            modo=valores.get('GEMINI_API_MODO','interactions')
            if modo not in ('interactions','generate_content'):modo='interactions'
            try:modelo=_validar_modelo(valores.get('GEMINI_MODEL','gemini-3.8-flash'))
            except ValueError:modelo='gemini-3.8-flash'
            salvar_configuracao(modo,modelo,caminho=self.ctx.arquivo_env)
            confirmado=_verificar_conta('gemini',chave)
            self.item('gemini','Gemini','metadados_confirmados' if confirmado['ok'] else 'pendente',
                'Chave preservada e catálogo da API respondeu; geração/cota dos agentes não testadas.' if confirmado['ok'] else
                _falha_conta(confirmado.get('codigo',0)))
            if not confirmado['ok']:self.pendente('gemini','chave','Conferir o acesso ao projeto e a chave Gemini.','gemini_chave')
        else:
            self.item('gemini','Gemini','pendente','Uma chave do projeto Google é necessária para Interactions/Managed Agents.')
            self.pendente('gemini','chave','Concluir chave Gemini se quiser usar a API e os agentes gerenciados.','gemini_chave')
        from ponte_preparacao_windows import detectar_robotask
        meta=detectar_robotask()
        self.item('robotask','RoboTask','presente' if meta.get('executavel_localizado') else 'nao_verificado',
            'Automação usa os serviços e scripts locais. Macros existentes não auditadas não foram disparadas.')
        return telegram

    def _executar(self,modelo):
        ctx=self.ctx
        try:
            self.item('inicio','Preparação automática','executando','Conferindo somente esta instalação do assistente.')
            from instancia_assistente import instancia_unica,InstanciaAtiva
            ultima=_ler_estado(ctx.preparacao/'ultima.json')
            try:
                with instancia_unica(ctx.dados):pass
            except InstanciaAtiva:
                if (ultima.get('versao')==VERSAO and ultima.get('bot_iniciado') and ultima.get('codigo')==str(ctx.codigo)
                    and ctx.origem==ctx.codigo and ctx.arquivo_env.exists()
                    and ultima.get('config_mtime')==ctx.arquivo_env.stat().st_mtime_ns):
                    with self.lock:self.estado.update(bot_iniciado=True,painel_url=ultima.get('painel_url','http://127.0.0.1:8765'))
                    self.item('inicio','Assistente','pronto','A versão preparada já está em execução; nenhuma segunda instância foi iniciada.');return
            from controlar_instancia_preparacao import parar_assistente
            self.item('parada','Instância anterior','verificando','Só a identidade comprovada deste assistente pode ser encerrada para atualizar.')
            parada=parar_assistente(ctx.codigo,ctx.dados,autorizado=True)
            if not parada['livre']:
                self.item('parada','Instância anterior','pendente',parada['mensagem'])
                self.pendente('parada','retomar','Feche somente a janela do assistente indicada e clique em Retomar.');return
            with instancia_unica(ctx.dados):
                self._configuracao()
                import implantacao_assistente as implantar
                self.item('fontes','Fontes e backup','verificando','Conferindo o pacote e preparando cópia reversível das fontes.')
                resultado=implantar.implantar(ctx.origem,ctx.codigo,ctx.backups,ctx.manifesto,autorizado=True,dados=ctx.dados)
                manifesto_destino=_seguro(ctx.codigo/'manifesto_instalacao.json')
                if ctx.origem!=ctx.codigo:
                    if manifesto_destino.exists():
                        backup=ctx.backups/'manifestos';backup.mkdir(parents=True,exist_ok=True)
                        shutil.copyfile(manifesto_destino,backup/('manifesto_'+secrets.token_hex(8)+'.json'))
                    _json_gravar(manifesto_destino,{'versao':1,'arquivos':implantar.carregar_manifesto(ctx.manifesto)})
                self.item('fontes','Fontes e backup','pronto',str(resultado['arquivos_verificados'])+' fontes verificadas; arquivos privados preservados.')
                self._componentes()
                valores=self._configuracao()
                self._servicos()
                try:self._gateway(modelo)
                except (OSError,ValueError,RuntimeError,subprocess.SubprocessError):
                    self.item('gateway','Cliente 9Router','pendente','A configuração local não foi confirmada; confira o dashboard.')
                    self.pendente('gateway','pagina','Concluir a autenticação/seleção no 9Router local.','9router_contas')
                valores=self._configuracao();telegram=self._contas(valores)
                try:
                    from startup_windows import consolidar_inicio
                    consolidar_inicio(ctx.codigo,self.python,arquivo_env_externo=ctx.arquivo_env,dados=ctx.dados,confirmado=True)
                    self.item('startup','Início após logon','presente','Entrada gerenciada preparada; aplicativos externos preservados. Habilitação do Windows não verificada.')
                except (OSError,ValueError,RuntimeError):
                    self.item('startup','Início após logon','pendente','O registro não foi confirmado; o início manual continua disponível.')
            from redirecionar_assistente import plano_execucao
            plano=plano_execucao(ctx.codigo,ctx.arquivo_env,ctx.dados,self.python,modo='start' if telegram else 'painel',ambiente=_ambiente(ctx))
            subprocess.Popen(plano['comando'],cwd=plano['cwd'],env=plano['ambiente'],shell=False,stdin=subprocess.DEVNULL,
                creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0x10) if sys.platform=='win32' else 0)
            with self.lock:self.estado['bot_iniciado']=True
            self.item('aplicacao','Assistente','iniciado','Início solicitado com a configuração externa. A resposta de cada modelo é verificada no uso.')
            _json_gravar(ctx.preparacao/'ultima.json',{'versao':VERSAO,'codigo':str(ctx.codigo),'bot_iniciado':True,
                'config_mtime':ctx.arquivo_env.stat().st_mtime_ns,'painel_url':self.estado['painel_url']})
        except Exception:
            # Bibliotecas/instaladores podem incluir segredos nas exceções.
            etapa=self.snapshot()['etapa']
            self.item('erro','Preparação','pendente','A etapa '+etapa+' não concluiu. Confira o requisito indicado acima e use Retomar; configuração e dados foram preservados.')
            self.pendente('erro','retomar','Conferir a última etapa e retomar a preparação.')
        finally:
            with self.lock:self.estado.update(executando=False,finalizado=True)

    def salvar_credencial(self,nome,valor):
        if not isinstance(nome,str) or nome not in CHAVES or not isinstance(valor,str) or not 1<=len(valor)<=4096:
            raise ValueError('Campo de configuração inválido.')
        valor=valor.strip()
        if not valor or valor[0] in "\"'" or valor[-1] in "\"'":raise ValueError('Digite a chave sem aspas.')
        if any(ord(c)<32 for c in valor):raise ValueError('A entrada não pode conter controles.')
        from configurar_telegram import validar_token,validar_ids
        if nome=='TELEGRAM_TOKEN' and not validar_token(valor):raise ValueError('Formato de token Telegram inválido.')
        if nome=='TELEGRAM_ALLOWED_USER_IDS' and not validar_ids(valor):raise ValueError('Informe IDs numéricos válidos do proprietário.')
        if nome!='TELEGRAM_ALLOWED_USER_IDS' and any(c.isspace() for c in valor):raise ValueError('A chave não pode conter espaços.')
        with self.lock:
            if self.estado['executando']:raise RuntimeError('Aguarde a etapa em andamento.')
            # Também vale quando o formulário é usado antes da primeira execução.
            self._configuracao()
            from configurar_ia_local import _atualizar_opcoes_env
            _atualizar_opcoes_env({nome:valor},caminho=self.ctx.arquivo_env)
            os.environ[nome]=valor
        return {'ok':True,'mensagem':'Opção salva localmente; o conteúdo não será exibido. Clique Retomar para aplicar.'}


def _json_unico(pares):
    d={}
    for k,v in pares:
        if k in d:raise ValueError('Campo repetido.')
        d[k]=v
    return d


class Interface(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,preparador):
        self.preparador=preparador;self.token=secrets.token_urlsafe(32)
        super().__init__(('127.0.0.1',0),Handler)


class Handler(BaseHTTPRequestHandler):
    server_version='MeuControlePCPreparacao/2.11.0'
    def setup(self):
        super().setup();self.connection.settimeout(10)
    def log_message(self,*args):pass
    def _host(self):return self.headers.get_all('Host',[]) in ([f'127.0.0.1:{self.server.server_port}'],[f'localhost:{self.server.server_port}'])
    def _auth(self):
        tokens=self.headers.get_all('X-Preparacao-Token',[])
        return len(tokens)==1 and secrets.compare_digest(tokens[0].encode(),self.server.token.encode())
    def _resposta(self,obj,codigo=200,html=False):
        bruto=(obj if html else json.dumps(obj,ensure_ascii=False,allow_nan=False)).encode('utf-8')
        self.send_response(codigo);self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.send_header('Content-Length',str(len(bruto)));self.end_headers()
        try:self.wfile.write(bruto)
        except (OSError,ConnectionError):pass
    def do_GET(self):
        if not self._host():return self._resposta({'erro':'Host não permitido.'},403)
        if self.path=='/':
            pagina=(BASE/'preparacao_autonoma.html').read_text(encoding='utf-8').replace('__PREPARACAO_TOKEN__',self.server.token)
            return self._resposta(pagina,html=True)
        if not self._auth():return self._resposta({'erro':'Acesso negado.'},403)
        if self.path=='/api/estado':return self._resposta(self.server.preparador.snapshot())
        return self._resposta({'erro':'Rota não encontrada.'},404)
    def do_POST(self):
        self.connection.settimeout(10)
        if not self._host() or not self._auth():return self._resposta({'erro':'Acesso negado.'},403)
        if self.headers.get_all('Origin',[])!=['http://'+self.headers.get('Host','')]:return self._resposta({'erro':'Origem não permitida.'},403)
        if self.path!='/api/acao':return self._resposta({'erro':'Rota não encontrada.'},404)
        try:
            if self.headers.get_all('Transfer-Encoding'):raise ValueError('Formato de envio inválido.')
            tamanhos=self.headers.get_all('Content-Length',[])
            if len(tamanhos)!=1 or not tamanhos[0].isdigit() or not 1<=int(tamanhos[0])<=MAX_CORPO:raise ValueError('Tamanho inválido.')
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':raise ValueError('Envie JSON.')
            d=json.loads(self.rfile.read(int(tamanhos[0])).decode('utf-8'),object_pairs_hook=_json_unico,
                         parse_constant=lambda _:(_ for _ in ()).throw(ValueError('JSON inválido.')))
            if not isinstance(d,dict):raise ValueError('Pedido inválido.')
            tipo=d.get('tipo')
            if tipo=='retomar' and set(d)<= {'tipo','modelo'}:
                modelo=d.get('modelo')
                if modelo is not None:
                    from roteador_9router import validar_modelo
                    modelo=validar_modelo(modelo)
                return self._resposta({'ok':self.server.preparador.iniciar(modelo)})
            if tipo=='chave' and set(d)=={'tipo','nome','valor'}:
                return self._resposta(self.server.preparador.salvar_credencial(d['nome'],d['valor']))
            if tipo=='abrir' and set(d)=={'tipo','servico'}:
                from ponte_preparacao_windows import abrir_ajudas
                # O próprio módulo valida o ID fechado e URLs fixas.
                return self._resposta({'ok':True,'resultado':abrir_ajudas([d['servico']],confirmado=True)})
            raise ValueError('Ação inválida.')
        except Exception:
            return self._resposta({'erro':'A solicitação não concluiu. Confira os campos e o estado; nenhum segredo será exibido.'},400)


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--origem');p.add_argument('--codigo');p.add_argument('--env',dest='arquivo_env');p.add_argument('--dados')
    p.add_argument('--sem-interface',action='store_true')
    args=p.parse_args(argv)
    try:
        if sys.platform!='win32':raise RuntimeError('Execute a preparação na sessão Windows do PC.')
        ctx=caminhos(args.origem,args.codigo,args.arquivo_env,args.dados)
        from instancia_assistente import instancia_unica,InstanciaAtiva
        try:
            with instancia_unica(ctx.preparacao):
                motor=Preparador(ctx)
                if args.sem_interface:
                    motor._executar(None);print(json.dumps(motor.snapshot(),ensure_ascii=False));return 0
                servidor=Interface(motor)
                try:
                    url=f'http://127.0.0.1:{servidor.server_port}'
                    _json_gravar(ctx.preparacao/'interface.json',{'pid':os.getpid(),'url':url})
                    webbrowser.open(url);motor.iniciar()
                    print('Preparação automática: '+url)
                    print('A janela local acompanha o progresso e mostra somente as decisões de conta que faltarem.')
                    servidor.serve_forever(poll_interval=0.5)
                finally:servidor.server_close()
        except InstanciaAtiva:
            registro=_ler_estado(ctx.preparacao/'interface.json');url=registro.get('url','')
            if isinstance(url,str) and url.startswith('http://127.0.0.1:') and url[17:].isdigit():webbrowser.open(url)
            print('A preparação já está aberta. Confira a janela local.');return 0
    except KeyboardInterrupt:return 0
    except (OSError,RuntimeError,ValueError):
        print('Preparação não iniciada. Confira os caminhos e o pacote completo; configuração e dados foram preservados.');return 2


if __name__=='__main__':raise SystemExit(main())
