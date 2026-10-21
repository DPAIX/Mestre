"""Serviços de conversas e projeto compartilhado, sem dependência do Telegram."""
from __future__ import annotations
import threading
import nucleo
import colaboracao_chats as central

_TRAVAS = {}
_TRAVAS_LOCK = threading.Lock()
ACOES_CENTRAL = {
    'chat_criar','chat_selecionar','chat_provedor','chat_modo','tarefa_projeto','tarefa_status',
    'contribuicao_importar','contribuicao_status','conexoes_ia','equipe_ia',
    'rotina_criar','rotina_remover','kanban_adicionar','kanban_mover','financeiro',
}


def campo_texto(obj,nome,limite=200,obrigatorio=True):
    valor=obj.get(nome,'')
    if not isinstance(valor,str):raise ValueError('O campo '+nome+' deve ser texto.')
    valor=valor.strip()
    if (obrigatorio and not valor) or len(valor)>limite:
        raise ValueError('Preencha '+nome+' com até '+str(limite)+' caracteres.')
    return valor


def conversar(texto,contexto,roteador):
    if not isinstance(texto,str) or not texto.strip():raise ValueError('Digite uma pergunta para a conversa.')
    if len(texto)>12000:raise ValueError('A mensagem deve ter até 12000 caracteres.')
    chat=central.obter_chat_ativo(contexto)
    chave=(contexto,chat['id'])
    with _TRAVAS_LOCK:
        if chave not in _TRAVAS:
            if len(_TRAVAS)>=1000:
                livres=[k for k,v in _TRAVAS.items() if not v.locked()]
                for k in livres[:100]:_TRAVAS.pop(k,None)
            _TRAVAS[chave]=threading.Lock()
        trava=_TRAVAS[chave]
    if not trava.acquire(blocking=False):
        raise RuntimeError('Esta conversa já está respondendo. Aguarde antes de enviar outra pergunta.')
    try:
        historico=central.historico_chat(contexto,chat_id=chat['id'])
        resposta,provedor=roteador.responder(texto.strip(),historico=historico,provedor=chat.get('provedor','auto'))
        central.registrar_troca(contexto,texto.strip(),resposta,provedor,chat_id=chat['id'])
        return f'🤖 {provedor} · {chat["titulo"]}:\n'+resposta
    finally:trava.release()


def resumo_chats(contexto):
    estado=central.estado_central(contexto)
    ativo=estado['chat_ativo']
    linhas=['💬 Conversas deste chat/tópico:']
    for chat in estado['chats'][:30]:
        marca='▶' if chat['id']==ativo['id'] else '•'
        linhas.append(f'{marca} {chat["id"]} | {chat["titulo"]} | {chat["provedor"]}')
    linhas.extend(['/chat novo Nome | /chat usar ID | /chat provedor Ollama',
                   '/chat modo on ativa conversa por mensagens comuns; /chat modo off desativa.',
                   '/ia pergunta usa o histórico da conversa selecionada. /contexto gera um pacote para outros chats.'])
    return '\n'.join(linhas)


def resumo_projeto(contexto):
    estado=central.estado_central(contexto)
    linhas=['🧩 Projeto compartilhado do assistente']
    for tarefa in estado['tarefas'][-20:]:
        linhas.append(f'• {tarefa["id"]} | {tarefa["status"]} | {tarefa["titulo"]}')
    if not estado['tarefas']:linhas.append('Nenhuma tarefa do projeto cadastrada.')
    linhas.append(f'Contribuições registradas: {len(estado["contribuicoes"])}')
    linhas.extend(['/projeto tarefa Título | Descrição | Papel',
                   '/projeto status ID pendente|em_andamento|concluida|cancelada',
                   '/contribuir Origem | Título | Texto (ou envie .md/.txt/.json)',
                   '/contexto exporta fontes, tarefas e prompts para ChatGPT/Gemini/Claude.',
                   '/equipe Objetivo consulta as IAs configuradas após confirmação.'])
    return '\n'.join(linhas)


def texto_conexoes(resultado):
    linhas=['🔌 Resultado de consultas reais solicitadas:']
    for nome,item in resultado.items():
        if not isinstance(item,dict):continue
        marca='✅' if item.get('ok') else '⚠️'
        linhas.append(f'{marca} {nome}: '+str(item.get('mensagem') or item.get('categoria') or 'sem resultado'))
    linhas.append('Uma resposta confirma esta consulta; não representa medição do saldo nem garantia de disponibilidade futura.')
    return str(nucleo.redigir('\n'.join(linhas)))


def texto_equipe(resultado):
    linhas=['👥 Equipe de IAs — contribuições para revisão']
    for item in resultado.get('resultados',[]):
        if item.get('ok'):
            linhas.append(f'✅ {item["provedor"]} · {item.get("papel","contribuição")}: '+str(item.get('contribuicao_id','registrada')))
        else:linhas.append(f'⚠️ {item.get("provedor","IA")}: '+str(item.get('erro') or item.get('mensagem') or 'indisponível'))
    if not resultado.get('resultados'):linhas.append('Nenhum provedor disponível. Use /contexto para colaborar pelos chats web ou configure Ollama.')
    linhas.append(str(resultado.get('resumo') or 'Veja as propostas na aba Chats e projeto. Nenhum código foi aplicado.'))
    return str(nucleo.redigir('\n'.join(linhas)))


def executar_acao(acao,obj,contexto,roteador):
    if acao=='chat_criar':
        chat=central.criar_chat(contexto,campo_texto(obj,'titulo',100),obj.get('provedor','auto'))
        return 'Conversa criada e selecionada: '+chat['id']
    if acao=='chat_selecionar':
        central.selecionar_chat(contexto,campo_texto(obj,'id',100));return 'Conversa selecionada.'
    if acao=='chat_provedor':
        chat_id=obj.get('id') or central.obter_chat_ativo(contexto)['id']
        central.configurar_chat(contexto,chat_id,provedor=campo_texto(obj,'provedor',30))
        return 'Provedor da conversa atualizado.'
    if acao=='chat_modo':
        if not isinstance(obj.get('ativo'),bool):raise ValueError('O modo de conversa deve ser verdadeiro ou falso.')
        chat_id=obj.get('id') or central.obter_chat_ativo(contexto)['id']
        central.configurar_chat(contexto,chat_id,modo_conversa=obj['ativo'])
        return ('Conversa contínua ativada. Mensagens comuns usam o provedor selecionado e podem consumir cota.'
                if obj['ativo'] else 'Conversa contínua desativada; use /ia para consultar.')
    if acao=='tarefa_projeto':
        tarefa=central.criar_tarefa(campo_texto(obj,'titulo',150),campo_texto(obj,'descricao',4000,False),campo_texto(obj,'papel',60,False) or 'geral')
        return 'Tarefa do projeto criada: '+tarefa['id']
    if acao=='tarefa_status':
        central.alterar_tarefa(campo_texto(obj,'id',100),campo_texto(obj,'status',40));return 'Tarefa atualizada.'
    if acao=='contribuicao_importar':
        proposta=central.importar_contribuicao(campo_texto(obj,'origem',80),campo_texto(obj,'titulo',150),campo_texto(obj,'texto',30000),tarefa_id=obj.get('tarefa_id') or None)
        return 'Contribuição registrada para revisão: '+proposta['id']+'. Nenhum código foi executado.'
    if acao=='contribuicao_status':
        central.decidir_contribuicao(campo_texto(obj,'id',100),campo_texto(obj,'status',30));return 'Decisão registrada. Aceitar uma proposta não aplica código.'
    if acao=='conexoes_ia':
        if obj.get('confirmacao')!='TESTAR CONEXOES':raise ValueError('Confirme TESTAR CONEXOES; consultas podem consumir cota.')
        return texto_conexoes(roteador.verificar_conexoes(provedor=obj.get('provedor','todos')))
    if acao=='equipe_ia':
        from equipe_ia import consultar_equipe
        resultado=consultar_equipe(campo_texto(obj,'texto',8000),roteador,provedores=obj.get('provedores'),tarefa_id=obj.get('tarefa_id') or None,confirmacao=obj.get('confirmacao',''))
        return texto_equipe(resultado)
    if acao=='rotina_criar':
        from rotina_ativa import cadastrar_tarefa
        tarefa=cadastrar_tarefa(campo_texto(obj,'atividade',200),campo_texto(obj,'dia',20),campo_texto(obj,'horario',5),campo_texto(obj,'fim',5,False),campo_texto(obj,'local',150,False),campo_texto(obj,'prioridade',30,False) or 'Normal')
        return 'Atividade criada: '+str(tarefa['id'])
    if acao=='rotina_remover':
        from rotina_ativa import remover_tarefa
        if obj.get('confirmacao')!='REMOVER TAREFA':raise ValueError('Confirme REMOVER TAREFA.')
        if not remover_tarefa(campo_texto(obj,'id',100)):raise ValueError('Atividade não encontrada.')
        return 'Atividade removida.'
    if acao=='kanban_adicionar':
        nucleo.adicionar_kanban(campo_texto(obj,'coluna',30),campo_texto(obj,'texto',200));return 'Tarefa incluída no Kanban.'
    if acao=='kanban_mover':
        from rotina_ativa import mover_kanban
        indice=obj.get('indice')
        if isinstance(indice,bool) or not isinstance(indice,int):raise ValueError('Índice de tarefa inválido.')
        mover_kanban(campo_texto(obj,'origem',30),indice,campo_texto(obj,'destino',30));return 'Tarefa movida.'
    if acao=='financeiro':
        saldo=nucleo.movimentar(campo_texto(obj,'tipo',10),obj.get('valor'),campo_texto(obj,'descricao',150))
        return f'Movimentação registrada. Saldo: R$ {saldo:.2f}'
    raise ValueError('Ação de projeto desconhecida.')
