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
import os
from pathlib import Path
import threading
import time
import uuid
import zipfile

import nucleo

_ANALISE_LOCK = threading.RLock()
FONTES = ('assistente_pc.py','nucleo.py','automacao_pc.py','multi_ia.py',
          'agenda_google.py','evolucao_segura.py','reinicio_seguro.py','reiniciar_assistente.py','verificacao_ambiente.py')
DADOS_CRITICOS = ('gestao_vida.json','minhas_macros.json','base_auto_aprendizado.json')
BACKUP_SEGURO = DADOS_CRITICOS + ('robotask_conhecimento.json','ecossistema_suporte.json')


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


def analisar(*, registrar_resultado=True):
    """Inspeção local sem usar APIs, executar macros ou sobrescrever dados."""
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
        agora=dt.datetime.now().astimezone()
        historicas=[];ativas=[]
        for e in eventos[-100:]:
            if not isinstance(e,dict) or str(e.get('status','')).lower() not in ('erro','falha','indisponivel'):continue
            historicas.append(e)
            try:
                carimbo=dt.datetime.fromisoformat(str(e.get('timestamp','')))
                if carimbo.tzinfo is None:carimbo=carimbo.astimezone()
                if dt.timedelta(0)<=agora-carimbo<=dt.timedelta(minutes=10):ativas.append(e)
            except (TypeError,ValueError):pass
        if ativas:
            problemas.append({'nivel':'aviso','alvo':'falhas_ativas','detalhe':f'{len(ativas)} falha(s) nos últimos 10 minutos. Veja /logs.'})
            # Exibir a causa específica para que o diagnóstico seja acionável.
            for evento in ativas[-3:]:
                acao=str(evento.get('acao','desconhecida'))[:45]
                detalhe=str(nucleo.redigir(evento.get('detalhes','')))[:140]
                problemas.append({'nivel':'aviso','alvo':'log: '+acao,'detalhe':detalhe or 'Falha sem mensagem detalhada.'})
        # Ocorrências antigas permanecem rastreáveis, mas não exigem reparo novamente.
        if any('sem_creditos' in str(e.get('detalhes','')) for e in historicas):
            sugestoes.append('Há falhas anteriores por falta de créditos; adicione saldo na plataforma ou desative o provedor. Nenhum código recupera créditos da conta.')
        token=os.environ.get('TELEGRAM_TOKEN','')
        if not token:
            sugestoes.append('Telegram sem token nesta sessão: configure o .env e reinicie o aplicativo.')
        if not os.environ.get('TELEGRAM_ALLOWED_USER_IDS','').strip():
            sugestoes.append('Permissões Telegram pendentes: configure TELEGRAM_ALLOWED_USER_IDS.')
        if problemas:
            sugestoes.append('Corrija os avisos sinalizados antes de reiniciar ou ativar tarefas automáticas.')
        else:
            sugestoes.append('Verificações locais sem erros detectados; APIs e ações no Windows não foram testadas.')
        sugestoes.append('Melhorias permitidas mediante confirmação: backup local dos dados, atualização de CSV/Jupyter e índice RoboTask.')
        resultado={'quando':dt.datetime.now().isoformat(timespec='seconds'),
                   'modo':'inspecao_sem_alteracao', 'verificacoes_ok':len(ok),
                   'falhas_recentes':len(ativas),'falhas_historicas':len(historicas)-len(ativas),'problemas':problemas,
                   'sugestoes':sugestoes,'melhorias_disponiveis':['backup','notebook','robotask'],
                   'estado':'atenção' if problemas else 'sem falhas locais detectadas'}
        if registrar_resultado:
            nucleo.gravar_json('ultima_autoanalise.json',resultado)
            nucleo.registrar('auto_analise','executado',f"{len(problemas)} alertas; {len(ativas)} falhas ativas; {len(historicas)} no histórico")
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


def executar_agendador(stop_event:threading.Event):
    """Executa *somente análise* de tempos em tempos, nunca reparos por conta própria."""
    try: intervalo=int(os.environ.get('AUTOANALISE_INTERVALO_MIN','360'))
    except ValueError: intervalo=360
    intervalo=max(15,min(intervalo,10080))
    if not stop_event.wait(5):
        while not stop_event.is_set():
            try:analisar()
            except Exception as exc:nucleo.registrar('auto_analise_agendada','falha',str(exc))
            if stop_event.wait(intervalo*60):break
