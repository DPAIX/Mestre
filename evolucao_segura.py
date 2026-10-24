"""Autoanálise e melhorias auditáveis, sem execução de código fornecido por IA.
Compatível com os JSON existentes. Ciclo automático apenas diagnóstico;
a aplicação de melhorias permitidas exige confirmação explícita do proprietário.
"""
from __future__ import annotations
import ast
import builtins
import symtable
import hashlib
import datetime as dt
import json
import math
import os
from pathlib import Path
import re
import threading
import time
import uuid
import zipfile

import nucleo

_ANALISE_LOCK = threading.RLock()
FONTES = ('assistente_pc.py','nucleo.py','automacao_pc.py','multi_ia.py',
          'colaboracao_chats.py','servicos_chat.py','equipe_ia.py','conversa_equipe.py','voz_assistente.py','rotina_ativa.py','configurar_ia_local.py','interpretacao_natural.py','integracoes_agentes.py',
          'agenda_google.py','autorizar_google.py','configurar_telegram.py','startup_windows.py',
          'caminhos_instalacao.py','redirecionar_assistente.py','idempotencia_painel.py',
          'transcritor_local.py','iniciar_servicos_locais.py','instancia_assistente.py','preparar_inicio_automatico.py','manutencao_assistente.py',
          'roteador_9router.py','integracoes_9stack.py','configurar_9router.py','memoria_assistente.py','configuracao_assistente.py','diagnostico_rede.py','gemini_interactions.py','servicos_gemini.py','configurar_gemini.py','prontidao_assistente.py',
          'evolucao_segura.py','reinicio_seguro.py','reiniciar_assistente.py','verificacao_ambiente.py')
DADOS_CRITICOS = ('gestao_vida.json','minhas_macros.json','base_auto_aprendizado.json')
BACKUP_SEGURO = DADOS_CRITICOS + ('robotask_conhecimento.json','ecossistema_suporte.json')
PROVEDORES = ('Gemini','OpenAI','Claude','Exa','Ollama','9Router')
STATUS_FALHA = ('erro','falha','indisponivel')


def _instante(valor):
    if isinstance(valor,bool):return None
    try:numero=float(valor)
    except (ValueError,TypeError,OverflowError):return None
    return numero if math.isfinite(numero) and numero>0 else None


def _horario_evento(evento):
    try:
        carimbo=dt.datetime.fromisoformat(str(evento.get('timestamp','')))
        if carimbo.tzinfo is None:carimbo=carimbo.astimezone()
        return carimbo.timestamp()
    except (TypeError,ValueError,OverflowError,OSError):return None


def _provedor_evento(evento):
    acao=str(evento.get('acao',''))
    if acao.startswith('api_') and acao[4:] in PROVEDORES:return acao[4:]
    provedor=evento.get('provedor')
    return provedor if provedor in PROVEDORES else None


def _categoria_evento(evento):
    detalhe=str(evento.get('detalhes','')).lower()
    codigo=re.search(r'\b(400|401|402|403|404|429|500|502|503|504|529)\b',detalhe)
    codigo=int(codigo.group()) if codigo else None
    if codigo in (500,502,503,504,529):categoria='servidor_ocupado'
    elif codigo in (401,403):categoria='autenticacao'
    elif codigo==404:categoria='modelo_indisponivel'
    elif codigo==402 or any(x in detalhe for x in ('sem_creditos','sem créditos','insufficient_quota','credit balance','no credits')):categoria='sem_creditos'
    elif codigo==429:categoria='limite_temporario'
    else:
        categoria=next((x for x in ('servidor_ocupado','cota_temporaria','autenticacao','modelo_indisponivel','limite_temporario','tempo_esgotado','rede','resposta_invalida','requisicao_invalida') if x in detalhe),'temporario')
    return categoria,codigo


def _orientacao_provedor(provedor,categoria):
    consulta='/pesquisar' if provedor=='Exa' else '/ia'
    orientacoes={
        'servidor_ocupado':f'O provedor informou alta demanda ou indisponibilidade temporária. Aguarde e repita uma consulta explícita com {consulta}.',
        'cota_temporaria':f'O provedor informou cota temporária esgotada. Aguarde o prazo indicado e repita uma consulta explícita com {consulta}.',
        'limite_temporario':f'Aguarde o prazo do provedor e repita uma consulta explícita com {consulta}, sem tentativas automáticas.',
        'sem_creditos':f'A última falha indica falta de créditos. Confira o saldo na plataforma; depois, libere a pausa local com /reativar_ias e faça uma consulta explícita com {consulta}.',
        'autenticacao':'Revise a credencial no .env local e as permissões da conta; não compartilhe chaves. Depois use /reativar_ias e uma consulta explícita.',
        'modelo_indisponivel':'Confira o modelo configurado e o acesso da sua conta. Depois use /reativar_ias e uma consulta explícita.',
        'rede':f'Confira a conexão e repita uma consulta explícita com {consulta}.',
        'tempo_esgotado':f'O prazo da consulta acabou; isso não comprova falha de rede nem cancelamento no serviço. Confira o Ollama antes de enviar outra consulta explícita com {consulta}.',
    }
    return orientacoes.get(categoria,f'Confira /verificar e os logs; uma nova consulta explícita com {consulta} é necessária para verificar o provedor.')


def _diagnosticar_provedores(eventos,estado_provedores,agora):
    """Consolida evidência local; fim de uma pausa não prova recuperação remota."""
    ultimo_erro={};ultimo_sucesso={}
    for indice,evento in enumerate(eventos):
        if not isinstance(evento,dict):continue
        provedor=_provedor_evento(evento)
        instante=_horario_evento(evento)
        if not provedor or instante is None:continue
        status=str(evento.get('status','')).lower()
        destino=ultimo_erro if status in STATUS_FALHA else ultimo_sucesso if status=='sucesso' else None
        if destino is None:continue
        anterior=destino.get(provedor)
        if anterior is None or (instante,indice)>(anterior[0],anterior[1]):destino[provedor]=(instante,indice,evento)
    snapshot=estado_provedores if isinstance(estado_provedores,dict) else {}
    evidencias={};avisos=[]
    for provedor in PROVEDORES:
        meta=snapshot.get(provedor,{})
        if not isinstance(meta,dict):meta={}
        configurado=meta.get('configurado')
        falha=ultimo_erro.get(provedor)
        sucesso=ultimo_sucesso.get(provedor)
        falha_em=falha[0] if falha else None
        sucesso_em=sucesso[0] if sucesso else None
        categoria,codigo=_categoria_evento(falha[2]) if falha else (None,None)
        falha_router=_instante(meta.get('falha_em'))
        sucesso_router=_instante(meta.get('sucesso_em'))
        evidencia_router=bool(meta.get('categoria') or falha_router is not None)
        origem_router=False
        # O log usa segundos e é emitido após persistir o estado: seu carimbo pode
        # ser posterior ao epoch da mesma falha, sem invalidar a evidência do roteador.
        if falha_router is not None and (falha_em is None or falha_router>=falha_em-0.000001):
            falha_em=falha_router;categoria=meta.get('categoria') or categoria
            codigo=meta.get('codigo') if meta.get('codigo') is not None else codigo
            origem_router=True
        elif falha_em is None and meta.get('categoria'):
            categoria=meta['categoria'];codigo=meta.get('codigo');origem_router=True
        if sucesso_router is not None and (sucesso_em is None or sucesso_router>sucesso_em):sucesso_em=sucesso_router
        superada=bool(falha_em is not None and sucesso_em is not None and sucesso_em>falha_em)
        if (not origem_router and falha and sucesso and sucesso[0]==falha[0] and sucesso[1]>falha[1]):superada=True
        em_pausa=bool(meta.get('em_pausa'))
        # Formatos legados guardavam a categoria, mas não a data da falha.
        # Um sucesso confirmado na sessão supera esse motivo antigo sem prazo ativo.
        if falha_router is None and falha is None and sucesso_router is not None and not em_pausa:superada=True
        pendente=bool(categoria and not superada and configurado is not False)
        recente=falha_em is not None and 0<=agora-falha_em<=600
        orientacao=_orientacao_provedor(provedor,categoria) if pendente else ''
        situacao=('sem_chave' if configurado is False else
                  'falha_sem_nova_verificacao' if pendente else
                  'sucesso_na_ultima_consulta' if sucesso_em is not None else 'nao_verificado')
        evidencias[provedor]={'situacao':situacao,'configurado':configurado,'categoria':categoria,
                             'codigo':codigo,'falha_em':falha_em,'sucesso_em':sucesso_em,
                             'em_pausa':em_pausa,'orientacao':orientacao}
        # Logs antigos permanecem no histórico. O snapshot pode comprovar uma
        # última falha ainda pendente mesmo após o prazo de espera terminar.
        if pendente and (recente or evidencia_router):
            causa=f' (HTTP {codigo})' if codigo else ''
            descricao={
                'servidor_ocupado':'Alta demanda ou indisponibilidade temporária do provedor',
                'limite_temporario':'Limite temporário de consultas',
                'cota_temporaria':'Cota temporária esgotada',
                'sem_creditos':'Créditos insuficientes na última tentativa',
                'autenticacao':'Credencial ou permissão rejeitada',
                'modelo_indisponivel':'Modelo ou rota não acessível',
                'rede':'Falha de conexão',
                'resposta_invalida':'Resposta inválida do provedor',
                'requisicao_invalida':'Requisição rejeitada pelo provedor',
            }.get(categoria,'Falha na consulta ao provedor')
            mensagem=f'{descricao}{causa}. A última consulta falhou; a disponibilidade atual ainda não foi verificada.'
            avisos.append({'nivel':'aviso','alvo':'provedor: '+provedor,'provedor':provedor,
                           'categoria':categoria,'codigo':codigo,'detalhe':mensagem,
                           'orientacao':orientacao,'em_pausa':em_pausa})
    return evidencias,avisos


def nomes_globais_indefinidos(codigo: str, arquivo: str = "<codigo>") -> list[str]:
    """Inspeção estática conservadora: detecta uso de globais inexistentes.

    Não importa nem executa o código analisado. Não substitui um teste em execução,
    mas encontra casos como `chat` dentro de `menu_secundario(chat_id, ...)`.
    """
    tabela = symtable.symtable(codigo, arquivo, "exec")
    declarados = {s.get_name() for s in tabela.get_symbols()
                  if s.is_assigned() or s.is_imported() or s.is_namespace()}
    builtin = set(dir(builtins)) | {'__file__', '__name__', '__package__', '__spec__', '__builtins__'}
    achados = set()
    def visitar(escopo):
        for simbolo in escopo.get_symbols():
            nome = simbolo.get_name()
            if simbolo.is_global() and simbolo.is_referenced() and nome not in declarados | builtin:
                achados.add((escopo.get_name(), nome))
        for filho in escopo.get_children():
            visitar(filho)
    for filho in tabela.get_children():
        visitar(filho)
    return [f"{funcao}: nome '{nome}' não definido" for funcao, nome in sorted(achados)]


def analisar(*, registrar_resultado=True, estado_provedores=None):
    """Inspeção local sem consultas remotas; estado opcional vem do roteador."""
    with _ANALISE_LOCK:
        problemas=[]; ok=[]; sugestoes=[]
        for nome in FONTES:
            arquivo=nucleo.BASE/nome
            if not arquivo.is_file():
                problemas.append({'nivel':'erro','alvo':nome,'detalhe':'Arquivo principal ausente.'})
                continue
            try:
                codigo=arquivo.read_text(encoding='utf-8-sig')
                ast.parse(codigo, filename=nome)
                ok.append('Sintaxe: '+nome)
                indefinidos=nomes_globais_indefinidos(codigo,nome)
                if indefinidos:
                    for item in indefinidos[:5]:
                        problemas.append({'nivel':'erro','alvo':nome,'detalhe':'Referência indefinida: '+item})
                else:
                    ok.append('Nomes globais: '+nome)
            except (SyntaxError,UnicodeError,OSError) as exc:
                problemas.append({'nivel':'erro','alvo':nome,'detalhe':str(nucleo.redigir(exc))[:180]})
        for nome in DADOS_CRITICOS:
            try:
                dado=nucleo.ler_json(nome,None)
                if dado is None or not isinstance(dado,dict):
                    raise ValueError('É necessário um objeto JSON.')
                ok.append('Dados: '+nome)
            except (ValueError,OSError) as exc:
                problemas.append({'nivel':'erro','alvo':nome,'detalhe':str(nucleo.redigir(exc))[:180]})
        try:
            resumo=nucleo.resumo_status()
            if resumo['disco_livre_mb']<2048:
                problemas.append({'nivel':'aviso','alvo':'disco','detalhe':'Menos de 2 GiB livres. Não haverá limpeza automática.'})
        except Exception as exc:
            resumo={}
            problemas.append({'nivel':'erro','alvo':'status','detalhe':str(nucleo.redigir(exc))[:180]})
        eventos=nucleo.ler_json('log_acoes_e_erros.json',[])
        if not isinstance(eventos,list):
            problemas.append({'nivel':'erro','alvo':'log_acoes_e_erros.json','detalhe':'O histórico deve ser uma lista JSON.'})
            eventos=[]
        eventos=eventos[-100:]
        agora=dt.datetime.now().astimezone().timestamp()
        historicas=[];recentes=[];locais_recentes=[];externas_recentes=[]
        for evento in eventos:
            if not isinstance(evento,dict) or str(evento.get('status','')).lower() not in STATUS_FALHA:continue
            historicas.append(evento)
            instante=_horario_evento(evento)
            if instante is not None and 0<=agora-instante<=600:
                recentes.append(evento)
                (externas_recentes if _provedor_evento(evento) else locais_recentes).append(evento)
        if locais_recentes:
            problemas.append({'nivel':'aviso','alvo':'falhas_ativas','detalhe':f'{len(locais_recentes)} ocorrência(s) de falha local nos últimos 10 minutos. Veja /logs.'})
            for evento in locais_recentes[-3:]:
                acao=str(evento.get('acao','desconhecida'))[:45]
                detalhe=str(nucleo.redigir(evento.get('detalhes','')))[:140]
                problemas.append({'nivel':'aviso','alvo':'log: '+acao,'detalhe':detalhe or 'Falha sem mensagem detalhada.'})
        problemas_locais=list(problemas)
        evidencias,avisos_externos=_diagnosticar_provedores(eventos,estado_provedores,agora)
        for aviso in avisos_externos:sugestoes.append(aviso['provedor']+': '+aviso['orientacao'])
        token=os.environ.get('TELEGRAM_TOKEN','')
        if not token:
            sugestoes.append('Telegram sem token nesta sessão: configure o .env e reinicie o aplicativo.')
        if not os.environ.get('TELEGRAM_ALLOWED_USER_IDS','').strip():
            sugestoes.append('Permissões Telegram pendentes: configure TELEGRAM_ALLOWED_USER_IDS.')
        if problemas_locais:
            sugestoes.append('Revise os problemas locais sinalizados antes de reiniciar ou ativar tarefas automáticas.')
        else:
            sugestoes.append('Verificações locais sem erros detectados. Esta análise não consultou APIs nem executou ações do Windows.')
        sugestoes.append('Manutenção local opcional mediante confirmação: backup dos dados, CSV/Jupyter e índice RoboTask. Essas ações não alteram a disponibilidade das APIs.')
        problemas=problemas_locais+avisos_externos
        estado_local='atenção' if problemas_locais else 'sem falhas locais detectadas'
        resultado={'quando':dt.datetime.now().isoformat(timespec='seconds'),
                   'modo':'inspecao_sem_alteracao', 'verificacoes_ok':len(ok),
                   'falhas_recentes':len(recentes),'falhas_historicas':len(historicas)-len(recentes),'problemas':problemas,
                   'problemas_locais':problemas_locais,'avisos_externos':avisos_externos,
                   'estado_local':estado_local,'estado_provedores':evidencias,
                   'falhas_locais_recentes':len(locais_recentes),'falhas_externas_recentes':len(externas_recentes),
                   'falhas_externas_pendentes':len(avisos_externos),
                   'sugestoes':sugestoes,'melhorias_disponiveis':['backup','notebook','robotask'],
                   'estado':'atenção local' if problemas_locais else 'sem falhas locais; há avisos de serviços externos' if avisos_externos else estado_local}
        if registrar_resultado:
            nucleo.gravar_json('ultima_autoanalise.json',resultado)
            nucleo.registrar('auto_analise','executado',f"{len(problemas_locais)} problemas locais; {len(avisos_externos)} avisos externos; {len(recentes)} ocorrências de falha recentes")
        return resultado


def _fazer_backup():
    """Snapshot JSON redigido, criado atomicamente, sem .env ou executáveis."""
    destino=nucleo.DADOS/'backups';destino.mkdir(parents=True,exist_ok=True)
    nome='dados_'+dt.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]+'.zip'
    alvo=destino/nome; temporario=destino/('.'+nome+'.tmp')
    try:
        with zipfile.ZipFile(temporario,'w',zipfile.ZIP_DEFLATED) as pacote:
            for arquivo in BACKUP_SEGURO:
                original=nucleo.DADOS/arquivo
                if not original.exists():continue
                obj=json.loads(original.read_text(encoding='utf-8-sig'))
                pacote.writestr(arquivo,json.dumps(nucleo.redigir(obj),ensure_ascii=False,indent=2))
        os.replace(temporario,alvo)
        return str(alvo)
    finally:temporario.unlink(missing_ok=True)


def _impressao_dados():
    """Fingerprint de entradas efetivas, não de logs nem contadores gerados pelo próprio app."""
    hash_=hashlib.sha256()
    for nome in ('gestao_vida.json','minhas_macros.json'):
        item=nucleo.DADOS/nome
        hash_.update(nome.encode())
        if item.exists():hash_.update(item.read_bytes())
    pasta=os.environ.get('ROBOTASK_TASKS_DIR') or str(os.path.join(os.environ.get('LOCALAPPDATA',str(nucleo.BASE)),'RoboTask','Tasks'))
    caminho=Path(pasta)
    if caminho.is_dir():
        for item in sorted(caminho.glob('*.tsk'))[:1000]:
            try:
                st=item.stat();hash_.update(str((item.name,st.st_mtime_ns,st.st_size)).encode())
            except OSError:pass
    # Uma atualização de código muda a versão da operação e exige novo snapshot.
    hash_.update((nucleo.BASE/'evolucao_segura.py').read_bytes())
    return hash_.hexdigest()

def melhorar(acoes=('backup','notebook','robotask')):
    """Executa somente ações internas pré-definidas. Faz backup antes de mexer nos dados.
    Não corrige / altera o próprio código, não chama LLMs e não altera tarefas .tsk.
    """
    permitidas={'backup','notebook','robotask'}
    solicitadas=tuple(dict.fromkeys(acoes))
    if not solicitadas or any(x not in permitidas for x in solicitadas):
        raise ValueError('Melhoria não permitida: selecione backup, notebook e/ou robotask.')
    with _ANALISE_LOCK:
        inicial=analisar(registrar_resultado=False)
        if any(p['nivel']=='erro' for p in inicial['problemas']):
            raise RuntimeError('Integridade comprometida: corrija erros antes de aplicar melhorias. Nenhum arquivo alterado.')
        # Evita backups duplicados gerados por múltiplos cliques, mas backups manuais explícitos são preservados.
        marca=_impressao_dados()
        anterior=nucleo.ler_json('ultima_melhoria.json',{})
        if not isinstance(anterior,dict):anterior={}
        acoes_anteriores=anterior.get('acoes',[])
        if not isinstance(acoes_anteriores,list):acoes_anteriores=[]
        concluidas={item.get('acao') for item in acoes_anteriores if isinstance(item,dict) and isinstance(item.get('acao'),str) and
                    (item.get('resultado')=='concluído' or
                     (item.get('acao')=='robotask' and item.get('resultado')=='não aplicável' and os.name!='nt'))}
        backup_anterior=anterior.get('backup')
        backup_disponivel=isinstance(backup_anterior,str) and bool(backup_anterior) and (nucleo.DADOS/backup_anterior).is_file()
        padrao=set(solicitadas)=={'backup','notebook','robotask'}
        if (padrao and anterior.get('impressao_dados')==marca and
                set(solicitadas)<=concluidas and backup_disponivel and
                (nucleo.DADOS/'analise_autonoma_rotina.ipynb').exists() and
                (nucleo.DADOS/'tabela_rotina.csv').exists() and
                (nucleo.DADOS/'robotask_conhecimento.json').exists()):
            return {'quando':dt.datetime.now().isoformat(timespec='seconds'),'sem_alteracoes':True,
                    'codigo_modificado':False,'backup':anterior.get('backup',''),
                    'acoes':[{'acao':'backup/notebook/robotask','resultado':'já atualizado',
                              'detalhes':'Entradas sem alterações; nenhum novo backup ou arquivo gerado.'}]}
        # Backup sempre é a primeira operação quando há novas entradas a processar.
        copia=_fazer_backup()
        feitos=[{'acao':'backup','resultado':'concluído','destino':copia}]
        for acao in solicitadas:
            if acao=='backup':continue
            try:
                if acao=='notebook':
                    csv,ipynb=nucleo.gerar_notebook()
                    descricao=f'Arquivos atualizados: {csv.name}, {ipynb.name}'
                elif acao=='robotask':
                    if os.name!='nt':
                        descricao='Não executado: catálogo do RoboTask depende do Windows.'
                    else:
                        lista=nucleo.catalogo_robotask()
                        descricao=f'{len(lista)} tarefas mapeadas sem executar tarefas.'
                feitos.append({'acao':acao,'resultado':'não aplicável' if descricao.startswith('Não executado') else 'concluído','detalhes':descricao})
            except Exception as exc:
                feitos.append({'acao':acao,'resultado':'falha','detalhes':str(nucleo.redigir(exc))[:170]})
                nucleo.registrar('melhoria_'+acao,'falha',str(exc))
        relatorio={'quando':dt.datetime.now().isoformat(timespec='seconds'),
                   'modo':'melhorias_permitidas_confirmadas','acoes':feitos,
                   # Mudanças concorrentes de entrada precisam produzir uma nova execução.
                   'codigo_modificado':False,'backup':copia,'impressao_dados':marca,'sem_alteracoes':False}
        nucleo.gravar_json('ultima_melhoria.json',relatorio)
        nucleo.registrar('melhorias_seguras','executado',', '.join(x['acao'] for x in feitos))
        return relatorio


def executar_agendador(stop_event:threading.Event, obter_estado_provedores=None):
    """Executa *somente análise* de tempos em tempos, nunca reparos por conta própria."""
    try: intervalo=int(os.environ.get('AUTOANALISE_INTERVALO_MIN','360'))
    except ValueError: intervalo=360
    intervalo=max(15,min(intervalo,10080))
    if not stop_event.wait(5):
        while not stop_event.is_set():
            try:analisar(estado_provedores=obter_estado_provedores() if obter_estado_provedores else None)
            except Exception as exc:nucleo.registrar('auto_analise_agendada','falha',str(exc))
            if stop_event.wait(intervalo*60):break
