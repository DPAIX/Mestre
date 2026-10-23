"""Núcleo testável sem Telegram/API/Windows. Dados legados compatíveis.
Nenhuma operação aqui executa código recebido de uma IA.
"""
from __future__ import annotations
import csv
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import io
import json
import logging
import math
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import shutil
import threading
import time
import uuid
import zipfile
from caminhos_instalacao import arquivo_env, diretorio_dados, ancestral_existente, SELETORES

BASE = Path(__file__).resolve().parent
DADOS = diretorio_dados(BASE)
_LOG = logging.getLogger('meucontrolepc')
_LOCK = threading.RLock()
_CPU_LOCK = threading.Lock()
_CPU_ESTADO = {'instante': None, 'total': None, 'ocioso': None, 'percentual': None}
_CPU_CACHE_SEGUNDOS = 0.5
SENSITIVE = re.compile(r'(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{14,}|(?<!\d)\d{5,15}:[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{20,}|AQ\.[A-Za-z0-9_-]{20,}|\bBearer\s+\S+)',re.I)
CONFIG_KEYS = {'telegram_token','gemini_api_key','google_api_key','pool_chaves_api','openai_api_key','claude_api_key','anthropic_api_key','exa_api_key','token','api_key','authorization','x-api-key','access_token','refresh_token','client_secret'}
ATRIBUICAO_SENSIVEL = re.compile(
    r'(?<![\w-])(?P<aspas>[\"\']?)(?:' +
    '|'.join(re.escape(chave) for chave in sorted(CONFIG_KEYS, key=len, reverse=True)) +
    r')(?P=aspas)\s*[:=]\s*', re.I)

def redigir(value):
    if isinstance(value, BaseException):
        return redigir(str(value))
    if isinstance(value, str):
        # Campos nomeados também cobrem chaves sem um prefixo reconhecível
        # (por exemplo, Exa/OAuth). A varredura respeita aspas escapadas e
        # coleções JSON, sem deixar partes do segredo após a primeira vírgula.
        partes = []
        anterior = 0
        for campo in ATRIBUICAO_SENSIVEL.finditer(value):
            if campo.start() < anterior or campo.end() == len(value):
                continue
            inicio = campo.end()
            fim = inicio
            aspas_valor = value[inicio] if value[inicio] in ('\"', "'") else ''
            if aspas_valor or value[inicio] in ('[', '{'):
                pilha = []
                citacao = ''
                while fim < len(value):
                    caractere = value[fim]
                    if citacao:
                        if caractere == '\\':
                            fim += 2
                            continue
                        if caractere == citacao:
                            citacao = ''
                            if aspas_valor:
                                fim += 1
                                break
                    elif caractere in ('\"', "'"):
                        citacao = caractere
                    elif caractere in ('[', '{'):
                        pilha.append(']' if caractere == '[' else '}')
                    elif caractere in (']', '}'):
                        if not pilha or pilha.pop() != caractere:
                            fim = len(value)
                            break
                        if not pilha:
                            fim += 1
                            break
                    fim += 1
                fim = min(fim, len(value))
            else:
                esquema = re.match(r'(?i)(?:Bearer|Basic|Digest|ApiKey|Token)\s+', value[inicio:])
                fim = inicio + (esquema.end() if esquema else 0)
                while fim < len(value) and not value[fim].isspace() and value[fim] not in ',;#]})(\"\'':
                    fim += 1
            if fim == inicio:
                continue
            partes.append(value[anterior:inicio])
            citacao_saida = aspas_valor
            if not citacao_saida and campo.group(0).rstrip().endswith(':'):
                citacao_saida = campo.group('aspas')
            partes.append(citacao_saida + '[CREDENCIAL-REDACTADA]' + citacao_saida)
            anterior = fim
        partes.append(value[anterior:])
        return SENSITIVE.sub('[CREDENCIAL-REDACTADA]', ''.join(partes))
    if isinstance(value, (list,tuple)):
        return [redigir(x) for x in value]
    if isinstance(value, dict):
        return {k: ('[REDACTADO]' if str(k).lower() in CONFIG_KEYS else redigir(v)) for k,v in value.items()}
    return value


def _constante_json_invalida(valor):
    raise ValueError('Número não finito em JSON.')


def _float_json_finito(valor):
    numero = float(valor)
    if not math.isfinite(numero):
        raise ValueError('Número não finito em JSON.')
    return numero


def ler_env(caminho=None):
    """Carrega .env sem substituir variáveis do ambiente. Não imprime valores."""
    selecionado = caminho is None and 'MEUCONTROLEPC_ENV' in os.environ
    caminho = Path(caminho) if caminho is not None else arquivo_env(BASE)
    if not caminho.is_file():
        if selecionado:
            raise RuntimeError('O .env externo selecionado não foi encontrado. Confira MEUCONTROLEPC_ENV; nenhuma configuração local foi usada.')
        return
    for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
        linha = linha.strip()
        if not linha or linha.startswith('#') or '=' not in linha: continue
        chave, valor = linha.split('=',1)
        chave = chave.strip()
        if re.fullmatch(r'[A-Z][A-Z0-9_]*',chave) and chave not in SELETORES:
            valor = valor.strip().strip('"\'')
            os.environ.setdefault(chave,valor)


def gravar_json(nome, valor):
    DADOS.mkdir(parents=True,exist_ok=True)
    alvo = DADOS / nome
    with _LOCK:
        tmp = DADOS / ('.'+nome+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with tmp.open('w',encoding='utf-8') as f:
                json.dump(valor,f,ensure_ascii=False,indent=2,allow_nan=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp,alvo)
        finally:
            tmp.unlink(missing_ok=True)


def ler_json(nome, padrao):
    alvo = DADOS / nome
    if not alvo.exists(): return json.loads(json.dumps(padrao,allow_nan=False))
    try:
        with _LOCK, alvo.open(encoding='utf-8-sig') as f:
            return json.load(f,parse_constant=_constante_json_invalida,parse_float=_float_json_finito)
    except (ValueError, OSError) as e:
        _LOG.error('Arquivo JSON inválido %s: %s',nome,e)
        raise ValueError(f'O arquivo {nome} está inválido; preservado para recuperação.') from e


def inicializar(diretorio_legado=None):
    DADOS.mkdir(parents=True,exist_ok=True)
    setup_log()
    origem = Path(diretorio_legado) if diretorio_legado else BASE
    migrar(origem)
    if not (DADOS/'gestao_vida.json').exists():
        inicial = BASE/'dados_iniciais'/'gestao_vida.json'
        gravar_json('gestao_vida.json',json.loads(inicial.read_text(encoding='utf-8')) if inicial.exists() else {'rotina':[],'financeiro':{'saldo':0,'movimentacoes':[]},'kanban':{},'habitos_saude':{}})
    if not (DADOS/'minhas_macros.json').exists():
        gravar_json('minhas_macros.json',{})
    if not (DADOS/'base_auto_aprendizado.json').exists():
        gravar_json('base_auto_aprendizado.json',{'total_comandos_executados':0,'frequencia_acoes':{},'regras_aprendidas':[]})


def setup_log():
    if _LOG.handlers: return
    DADOS.mkdir(parents=True,exist_ok=True)
    _LOG.setLevel(logging.INFO)
    h = RotatingFileHandler(DADOS/'assistente_v2.log',maxBytes=500_000, backupCount=3,encoding='utf-8')
    h.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    _LOG.addHandler(h)


def registrar(acao,status,detalhes='',provedor='local'):
    evento=redigir({'timestamp':dt.datetime.now().isoformat(timespec='seconds'),'acao':acao,'status':status,'detalhes':str(redigir(detalhes))[:400],'provedor':provedor})
    with _LOCK:
        eventos=ler_json('log_acoes_e_erros.json',[])
        if not isinstance(eventos,list): eventos=[]
        eventos.append(evento)
        gravar_json('log_acoes_e_erros.json',eventos[-250:])
    _LOG.info('%s [%s] %s',evento['acao'],evento['status'],evento['detalhes'][:200])
    return evento


def migrar(origem):
    """Copia dados de versões antigas, nunca importa segredos de config_apis.json.
    Se destino já existe, não altera. Mantém arquivo original intacto.
    """
    seguros=['gestao_vida.json','minhas_macros.json','base_auto_aprendizado.json','memoria_aprendizado.json','robotask_conhecimento.json','ecossistema_suporte.json','telemetria_evolucao.json']
    for nome in seguros:
        destino=DADOS/nome
        src=origem/nome
        if destino.exists(): continue
        if not src.exists(): src=BASE/'dados_iniciais'/nome
        if not src.exists() or src.resolve()==destino.resolve(): continue
        try:
            valor=json.loads(src.read_text(encoding='utf-8-sig'))
            # Redige credenciais que podem aparecer em memórias históricas.
            gravar_json(nome,redigir(valor))
            _LOG.info('Migrado arquivo: %s', nome)
        except (OSError, ValueError) as e:
            _LOG.warning('Não foi possível migrar %s: %s',nome,e)
    # Não importa logs legados: podem conter URLs privadas, tokens e dados sensíveis.


def vida():
    valor=ler_json('gestao_vida.json',{})
    def invalido(campo,esperado):
        # Somente nomes do esquema; nenhum valor pessoal é incluído no erro.
        raise ValueError('Estrutura de gestao_vida.json inválida em '+campo+': '+esperado+'. Arquivo preservado.')
    if not isinstance(valor,dict):invalido('raiz','objeto JSON esperado')
    rotina=valor.get('rotina',[])
    if not isinstance(rotina,list) or any(not isinstance(item,dict) for item in rotina):
        invalido('rotina','lista de objetos esperada')
    for campo in ('financeiro','kanban','habitos_saude'):
        if not isinstance(valor.get(campo,{}),dict):invalido(campo,'objeto esperado')
    financeiro=valor.get('financeiro',{})
    movimentos=financeiro.get('movimentacoes',[])
    if not isinstance(movimentos,list) or any(not isinstance(item,dict) for item in movimentos):
        invalido('financeiro.movimentacoes','lista de objetos esperada')
    for campo in ('saldo','custo_unitario_ru'):
        if campo in financeiro:
            try:
                valido=not isinstance(financeiro[campo],bool) and math.isfinite(float(financeiro[campo]))
            except (ValueError,TypeError,OverflowError):valido=False
            if not valido:invalido('financeiro.'+campo,'número finito esperado')
    for itens in valor.get('kanban',{}).values():
        if not isinstance(itens,list):invalido('kanban.*','lista esperada')
    for nome,habito in valor.get('habitos_saude',{}).items():
        if not isinstance(habito,dict):invalido('habitos_saude.*','objeto esperado')
        # Sono pode ser fracionário; foco e outros hábitos podem ser textuais.
        # Somente estes dois contadores participam das operações inteiras.
        if nome not in ('Agua_Copos','Pomodoros_Hoje'):continue
        for campo in ('valor','meta'):
            if campo in habito:
                numero=habito[campo]
                try:
                    valido=not isinstance(numero,bool) and int(numero)==float(numero) and int(numero)>=0
                except (ValueError,TypeError,OverflowError):valido=False
                if not valido:invalido('habitos_saude.'+nome+'.'+campo,'inteiro não negativo esperado')
    return valor


def aprender(acao,ok=True):
    with _LOCK:
        base=ler_json('base_auto_aprendizado.json',{})
        base['total_comandos_executados']=int(base.get('total_comandos_executados',0))+1
        f=base.setdefault('frequencia_acoes',{})
        f[acao]=int(f.get(acao,0))+1
        gravar_json('base_auto_aprendizado.json',base)
    registrar(acao,'sucesso' if ok else 'falha')


def concluir_tarefa(id_tarefa):
    with _LOCK:
        v=vida(); achou=False
        for item in v.get('rotina',[]):
            if str(item.get('id'))==str(id_tarefa):
                item['status']='Concluído' if item.get('status')!='Concluído' else 'Pendente'
                achou=True; status=item['status']; break
        if not achou: raise ValueError('Tarefa não encontrada.')
        gravar_json('gestao_vida.json',v)
    aprender('concluir_tarefa')
    return status


def registrar_agua():
    with _LOCK:
        v=vida(); h=v.setdefault('habitos_saude',{}).setdefault('Agua_Copos',{'valor':0,'meta':8,'unidade':'copos'})
        h['valor']=int(h.get('valor',0))+1; gravar_json('gestao_vida.json',v)
    aprender('agua')
    return h['valor'],int(h.get('meta',8))


def registrar_pomodoro():
    with _LOCK:
        v=vida(); h=v.setdefault('habitos_saude',{}).setdefault('Pomodoros_Hoje',{'valor':0,'meta':6,'unidade':'ciclos'})
        h['valor']=int(h.get('valor',0))+1; gravar_json('gestao_vida.json',v)
    aprender('pomodoro')
    return h['valor']


def movimentar(tipo, valor, descricao):
    if tipo not in ('entrada','saida'): raise ValueError('Tipo de movimentação inválido.')
    try: valor=Decimal(str(valor).replace(',','.'))
    except InvalidOperation as e: raise ValueError('Valor numérico inválido.') from e
    if not valor.is_finite() or not 0<valor<1_000_000:
        raise ValueError('Valor fora do intervalo permitido.')
    if valor != valor.quantize(Decimal('0.01')):
        raise ValueError('Informe um valor com no máximo duas casas decimais.')
    with _LOCK:
        v=vida(); f=v.setdefault('financeiro',{'saldo':0,'movimentacoes':[]})
        try:
            saldo=Decimal(str(f.get('saldo',0)))
            if not saldo.is_finite():raise InvalidOperation
            saldo=(saldo+(valor if tipo=='entrada' else -valor)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        except InvalidOperation as e:
            raise ValueError('Saldo armazenado inválido; confira o arquivo financeiro antes de lançar valores.') from e
        f['saldo']=float(saldo)
        f.setdefault('movimentacoes',[]).append({'data':dt.datetime.now().strftime('%d/%m/%Y %H:%M'),'tipo':tipo,'valor':float(valor),'descricao':str(descricao)[:150],'categoria':'Manual'})
        gravar_json('gestao_vida.json',v)
    aprender('financeiro_'+tipo)
    return f['saldo']


def simular_ru(qtd):
    if not 0<=qtd<=300: raise ValueError('Quantidade inválida.')
    f=vida().get('financeiro',{})
    custo=float(f.get('custo_unitario_ru',6))
    return round(qtd*custo,2), round(float(f.get('saldo',0))-qtd*custo,2)


def adicionar_kanban(coluna,texto):
    if coluna not in ('A_Fazer','Em_Andamento','Concluido'):raise ValueError('Coluna inválida')
    if not 1<=len(texto.strip())<=200: raise ValueError('Texto deve ter de 1 a 200 caracteres.')
    with _LOCK:
        v=vida(); v.setdefault('kanban',{}).setdefault(coluna,[]).append(texto.strip())
        gravar_json('gestao_vida.json',v)
    aprender('kanban')


def _uso_cpu(psutil):
    """Amostra agregada, sem espera e compartilhada entre threads HTTP.

    cpu_percent(None) mantém uma base por thread; em requisições novas isso
    poderia apresentar zero antes de existir uma medição. A primeira amostra
    aqui é N/D. Somente métricas de hardware são guardadas por meio segundo.
    """
    with _CPU_LOCK:
        agora=time.monotonic()
        anterior=_CPU_ESTADO.copy()
        instante=anterior['instante']
        if instante is not None and 0<=agora-instante<_CPU_CACHE_SEGUNDOS:
            return anterior['percentual']
        total=None;ocioso=None;percentual=None
        try:
            campos=psutil.cpu_times()._asdict()
            if not isinstance(campos,dict) or 'idle' not in campos:
                raise ValueError('Contadores CPU indisponíveis.')
            if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) or v<0
                   for v in campos.values()):
                raise ValueError('Contadores CPU inválidos.')
            # Linux já inclui guest/guest_nice em user/nice. iowait é ocioso;
            # Windows não fornece esses campos, mantendo a mesma fórmula.
            total=sum(campos.values())-campos.get('guest',0)-campos.get('guest_nice',0)
            ocioso=campos['idle']+campos.get('iowait',0)
            if not math.isfinite(total) or not math.isfinite(ocioso) or not 0<=ocioso<=total:
                raise ValueError('Contadores CPU inconsistentes.')
            if instante is not None and agora>=instante and anterior['total'] is not None:
                delta=total-anterior['total'];parado=ocioso-anterior['ocioso']
                if delta>0 and 0<=parado<=delta:
                    percentual=round(100*(delta-parado)/delta,1)
        except Exception:
            # Métricas são opcionais. Uma falha não torna os dados locais
            # indisponíveis nem publica mensagens do sistema operacional.
            total=None;ocioso=None
        _CPU_ESTADO.update(instante=agora,total=total,ocioso=ocioso,percentual=percentual)
        return percentual


def resumo_status(*,dados_vida=None,dados_robotask=None):
    """Resumo sem espera; permite reaproveitar snapshots já lidos na requisição."""
    v=vida() if dados_vida is None else dados_vida
    robotask=ler_json('robotask_conhecimento.json',{}) if dados_robotask is None else dados_robotask
    if not isinstance(v,dict) or not isinstance(robotask,dict):
        raise ValueError('Estrutura inválida para o resumo local.')
    tarefas=v.get('rotina',[])
    feito=sum(x.get('status')=='Concluído' for x in tarefas)
    base=ler_json('base_auto_aprendizado.json',{})
    disk=shutil.disk_usage(ancestral_existente(DADOS))
    cpu=None;ram=None
    try:
        import psutil
        cpu=_uso_cpu(psutil)
        try:
            percentual=psutil.virtual_memory().percent
            if not isinstance(percentual,bool) and isinstance(percentual,(int,float)) and math.isfinite(percentual) and 0<=percentual<=100:
                ram=round(percentual,1)
        except Exception:pass
    except ImportError:
        pass
    return {'concluidas':feito,'total_tarefas':len(tarefas),'saldo':v.get('financeiro',{}).get('saldo',0),
            'cpu_percentual':cpu,'ram_percentual':ram,
            'comandos':base.get('total_comandos_executados',0),'disco_livre_mb':round(disk.free/1048576),
            'agua':v.get('habitos_saude',{}).get('Agua_Copos',{}).get('valor',0),
            'robotask_total':len(robotask.get('tarefas',[]))}


def diagnostico():
    livre=resumo_status()['disco_livre_mb']
    avisos=[]
    if livre < 2048: avisos.append(f'Espaço livre baixo ({livre} MiB). Não será feita limpeza arbitrária de arquivos.')
    import importlib.util
    for mod in ['telebot','pyautogui','google.genai']:
        try: instalado=importlib.util.find_spec(mod) is not None
        except ModuleNotFoundError: instalado=False
        if not instalado: avisos.append('Dependência ausente: '+mod)
    return {'disco_livre_mb':livre,'avisos':avisos,'status':'atenção' if avisos else 'sem alertas básicos'}


def reparo_seguro():
    """Não apaga arquivos de usuário, não mexe no próprio código."""
    DADOS.mkdir(exist_ok=True)
    resumo=diagnostico()
    for nome in ['gestao_vida.json','minhas_macros.json','base_auto_aprendizado.json']:
        ler_json(nome,{}) # detecta corrupção, sem sobrescrever
    registrar('diagnostico_seguro','executado',resumo['status'])
    return resumo


def catalogo_robotask(caminho=None):
    """Somente consulta .tsk. Nunca sobrescreve, executa nem altera tarefas."""
    if caminho is None:
        path=os.environ.get('ROBOTASK_TASKS_DIR') or (Path(os.environ.get('LOCALAPPDATA',str(BASE)))/'RoboTask'/'Tasks')
    else: path=caminho
    pasta=Path(path)
    resultados=[]
    if pasta.is_dir():
        for arq in sorted(pasta.glob('*.tsk'))[:1000]:
            texto=None
            for cod in ('utf-8-sig','utf-16','cp1252'):
                try:
                    candidato=arq.read_text(encoding=cod)
                    if cod=='utf-8-sig' and '\x00' in candidato:continue
                    texto=candidato
                    break
                except (UnicodeDecodeError,UnicodeError): continue
            if texto is None:continue
            cab=texto.split('[Actions]',1)[0].split('[Events]',1)[0]
            nome=re.search(r'^(?:TaskName|Name)\s*=\s*STRING\|"?([^"\r\n]*)',cab,re.M)
            ext=re.search(r'^ExternalName\s*=\s*STRING\|"?([^"\r\n]*)',cab,re.M)
            acoes=sorted(set(re.findall(r'ActionID\s*=\s*STRING\|"?([^"\r\n]*)',texto,re.M)))
            resultados.append({'arquivo':arq.name,'nome':nome.group(1) if nome else arq.stem,'external_name':ext.group(1) if ext else '','acoes_detectadas':acoes})
    gravar_json('robotask_conhecimento.json',{'pasta_tasks':str(pasta),'total_tarefas_lidas':len(resultados),'tarefas':resultados})
    aprender('mapear_robotask')
    return resultados


def gerar_notebook():
    v=vida(); DADOS.mkdir(exist_ok=True)
    csvpath=DADOS/'tabela_rotina.csv'
    with csvpath.open('w',encoding='utf-8-sig',newline='') as fp:
        campos=['id','dia','horario','fim','atividade','local','categoria','prioridade','status']
        out=csv.DictWriter(fp,fieldnames=campos,extrasaction='ignore');out.writeheader();out.writerows(v.get('rotina',[]))
    notebook={'cells':[
        {'cell_type':'markdown','metadata':{},'source':['# Rotina FURG — MeuControlePC v2\n','Dados exportados do controle local, sem chaves de API.\n']},
        {'cell_type':'code','metadata':{},'execution_count':None,'outputs':[],
         'source':['import csv, pathlib\n','p = pathlib.Path("tabela_rotina.csv")\n','with p.open(encoding="utf-8-sig", newline="") as f:\n','    rotina=list(csv.DictReader(f))\n','print("Tarefas:", len(rotina))\n','for t in rotina: print(t.get("dia"), t.get("atividade"), t.get("status"))\n']}
    ],'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'nbformat':4,'nbformat_minor':5}
    destino=DADOS/'analise_autonoma_rotina.ipynb'
    destino.write_text(json.dumps(notebook,ensure_ascii=False,indent=2),encoding='utf-8')
    aprender('exportar_notebook')
    return csvpath,destino


def exportacao_segura():
    """Exporta só dados allowlisted, omite credenciais, arquivos externos e logs antigos."""
    DADOS.mkdir(parents=True,exist_ok=True)
    destino=DADOS/('exportacao_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex+'.zip')
    nomes=['gestao_vida.json','minhas_macros.json','base_auto_aprendizado.json','robotask_conhecimento.json','log_acoes_e_erros.json']
    with zipfile.ZipFile(destino,'w',zipfile.ZIP_DEFLATED) as z:
        for nome in nomes:
            p=DADOS/nome
            if not p.exists():continue
            try: obj=ler_json(nome,{})
            except (ValueError,OSError): continue
            z.writestr(nome,json.dumps(redigir(obj),ensure_ascii=False,indent=2))
    aprender('exportar_logs')
    return destino


def classificar_texto(texto):
    """Comandos óbvios nunca são enviados ao mecanismo de pesquisa Exa."""
    t=texto.strip().casefold()
    if not t:return 'vazio'
    # Desligamento remoto foi removido. Bloqueia variantes de linguagem natural
    # sem bloquear perguntas sobre desligar periféricos ou reiniciar o assistente.
    padrao_desligar=r'\b(?:desligar|desligue|desliga|apagar|apague|poweroff)\b(?:\W+[\wÀ-ÿ]+){0,5}\W+(?:pc|computador|windows|m[aá]quina|sistema)\b'
    if re.search(padrao_desligar,t) or re.search(r'\bshutdown\s*/s\b',t) or t.strip()=='poweroff':
        return 'desligamento_bloqueado'
    if t in ('arrume e melhore','arrume e melhore o bot','melhore','otimize','analise e melhore','autoanalise','auto-análise'):
        return 'pedido_melhoria'
    if t in ('reinicie o windows','reiniciar windows','reinicie o pc','reiniciar o pc','reinicie o sistema por completo'):
        return 'pedido_reinicio_windows'
    if t in ('reinicie o assistente','reiniciar assistente','reinicie o bot','reiniciar bot'):
        return 'pedido_reinicio_bot'
    if t in ('arrume','conserte','repare','corrija','arrume o bot','arrume o pc') or any(t.startswith(x) for x in ('repare o bot','conserte o bot','diagnóstico do pc','diagnostico do pc')):
        return 'reparo'
    if any(t.startswith(x) for x in ('pesquise ','pesquisar ','busque na web ','procure na internet ')):
        return 'pesquisa'
    if t in ('status','status pc','como está o pc','como esta o pc'):
        return 'status'
    if t in ('rotina','minha rotina'):
        return 'rotina'
    if t in ('ajuda','menu','comandos'):
        return 'menu'
    return 'conversa'


def analisar_evolucao():
    """Analisa eventos e propõe melhorias auditáveis; não reescreve código."""
    import collections
    logs=ler_json('log_acoes_e_erros.json',[])
    falhas=[x for x in logs[-100:] if str(x.get('status','')).casefold() in ('falha','erro','indisponivel')]
    base=ler_json('base_auto_aprendizado.json',{})
    contagens=collections.Counter(str(x.get('acao','')).split('_')[0] for x in falhas)
    sugestoes=[]
    if len(falhas)>3:sugestoes.append('Revisar erros recentes e recuperar operações indisponíveis antes de novas automações.')
    if contagens.get('api',0)>=2:sugestoes.append('Verificar crédito/modelos da API; evite repetir chamadas enquanto indisponíveis.')
    if resumo_status()['disco_livre_mb']<2048:sugestoes.append('Revisar espaço livre do Windows; limpeza de outros arquivos exige revisão humana.')
    freq=base.get('frequencia_acoes',{})
    if freq:sugestoes.append('Ações mais frequentes: '+', '.join(x[0] for x in sorted(freq.items(),key=lambda t:-t[1])[:3]))
    if not sugestoes:sugestoes.append('Nenhuma correção automática necessária após diagnóstico básico.')
    relatorio={'falhas_recentes':len(falhas),'sugestoes':sugestoes,'modo':'somente analise; sem alteracao de codigo'}
    registrar('auto_analise','executado',f'{len(falhas)} falhas analisadas')
    return relatorio


def detectar_ecossistema():
    import platform
    executaveis=['python','node','npm','git','code','powershell','RoboTask.exe']
    return {'sistema':platform.system()+' '+platform.release(), 'python':platform.python_version(),
            'ferramentas':{nome: bool(shutil.which(nome)) for nome in executaveis}}
