"""Serviços de conversas e projeto compartilhado, sem dependência do Telegram."""
from __future__ import annotations
import os
import threading
import nucleo
import colaboracao_chats as central

_TRAVAS = {}
_TRAVAS_LOCK = threading.Lock()
_CONFIG_OLLAMA_LOCK = threading.RLock()
ACOES_CENTRAL = {
    'chat_criar','chat_selecionar','chat_provedor','chat_modelo','chat_modo','chats_modelos_ollama','modelo_testar','tarefa_projeto','tarefa_status',
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


def conversar(texto,contexto,roteador,retornar_plano=False,*,progresso=None):
    if not isinstance(texto,str) or not texto.strip():raise ValueError('Digite uma pergunta para a conversa.')
    if len(texto)>12000:raise ValueError('A mensagem deve ter até 12000 caracteres.')
    if retornar_plano and len(texto)>8000:raise ValueError('Envie mensagens de até 8000 caracteres para interpretar pedidos.')
    texto=str(nucleo.redigir(texto.strip()))
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
        politica=chat.get('equipe_politica','automatica')
        if politica not in ('automatica','manual'):raise ValueError('Política de equipe inválida nesta conversa; arquivo preservado.')
        if politica=='automatica':
            from configurar_ia_local import validar_modelo
            catalogo=roteador.catalogo_ollama()
            if not isinstance(catalogo,dict) or catalogo.get('habilitado') is not True:
                raise ValueError('A equipe automática precisa do serviço Ollama local habilitado. Confira a instalação automática; nenhuma API externa foi consultada.')
            itens=catalogo.get('modelos')
            if not isinstance(itens,list):raise ValueError('O catálogo da equipe automática é inválido.')
            try:modelos=list(dict.fromkeys(validar_modelo(item['nome']) for item in itens))
            except (KeyError,TypeError):raise ValueError('O catálogo da equipe automática é inválido.') from None
            if not 1<=len(modelos)<=8:
                raise ValueError('A equipe automática precisa de um a oito modelos no catálogo Ollama; nenhum participante foi descartado silenciosamente.')
            chat=central.configurar_equipe_automatica(contexto,chat['id'],modelos)
        historico=central.historico_chat(contexto,chat_id=chat['id'])
        opcoes={'historico':historico,'provedor':chat.get('provedor','auto')}
        modelo=chat.get('modelo_ollama','') if opcoes['provedor']=='Ollama' else ''
        if modelo:opcoes['modelo_ollama']=modelo
        pergunta=texto.strip()
        if retornar_plano:
            from interpretacao_natural import instrucoes_ia,extrair_resposta
            import datetime
            from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
            try:agora=datetime.datetime.now(ZoneInfo('America/Sao_Paulo'))
            except ZoneInfoNotFoundError:agora=datetime.datetime.now().astimezone()
            compacto=(os.getenv('OLLAMA_PERFIL','padrao').strip().casefold()=='cpu' and
                      bool(chat.get('equipe_paralela')) and chat.get('equipe_modo','paralela')=='cooperativa')
            pergunta=(instrucoes_ia(compacto=compacto)+'\nData/hora de referência do assistente: '+agora.isoformat(timespec='minutes')+
                      '. Datas relativas devem usar essa referência; se houver ambiguidade, pergunte.\n\nÚLTIMA MENSAGEM DO PROPRIETÁRIO:\n'+pergunta[:8000])
        equipe=bool(chat.get('equipe_paralela'))
        if equipe:
            from conversa_equipe import consultar_modelos
            equipe_resultado=consultar_modelos(pergunta,historico,chat.get('equipe_modelos'),roteador,
                interpretar=retornar_plano,modo=chat.get('equipe_modo','paralela'),
                progresso=progresso)
            resposta=equipe_resultado['texto'];provedor='Ollama'
        else:resposta,provedor=roteador.responder(pergunta,**opcoes)
        resposta=nucleo.redigir(resposta)
        plano=None
        if retornar_plano and equipe:
            plano=equipe_resultado['plano']
        elif retornar_plano:
            resultado=extrair_resposta(resposta);resposta=resultado['texto'];plano=resultado['plano']
            if plano:resposta='Entendi: '+plano['descricao']+'. O pedido ainda não foi executado.'
        central.registrar_troca(contexto,texto.strip(),resposta,provedor,chat_id=chat['id'],modelo_ollama=modelo)
        rotulo=('Equipe Ollama' if equipe else provedor+(' / '+modelo if modelo else ''))
        if retornar_plano:return {'texto':f'🤖 {rotulo} · {chat["titulo"]}:\n'+resposta,'plano':plano,'chat_id':chat['id']}
        return f'🤖 {rotulo} · {chat["titulo"]}:\n'+resposta
    finally:trava.release()


def resumo_chats(contexto):
    estado=central.estado_central(contexto)
    ativo=estado['chat_ativo']
    linhas=['💬 Conversas deste chat/tópico:']
    for chat in estado['chats'][:30]:
        marca='▶' if chat['id']==ativo['id'] else '•'
        modelo=(' / '+chat['modelo_ollama']) if chat.get('modelo_ollama') and chat['provedor']=='Ollama' else ''
        linhas.append(f'{marca} {chat["id"]} | {chat["titulo"]} | {chat["provedor"]}'+modelo)
        if chat.get('equipe_paralela'):linhas.append('  Equipe '+chat.get('equipe_modo','paralela')+': '+', '.join(chat['equipe_modelos']))
        if chat.get('equipe_politica','automatica')=='automatica':
            linhas.append('  Automática: todos os modelos do catálogo serão usados na próxima mensagem que precisar de IA.')
    linhas.extend(['/chat novo Nome | /chat usar ID | /chat provedor Ollama',
                   '/modelos ollama lista o catálogo; /chat modelo NOME seleciona por conversa; /chat modelo padrao usa a configuração geral.',
                   '/chat modo on ativa conversa por mensagens comuns; /chat modo off desativa.',
                   '/chat equipe on usa todos os modelos Ollama em cooperação sequencial e síntese; /chat equipe paralelo consulta simultaneamente; /chat equipe off volta ao individual.',
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
                   '/contexto exporta fontes, tarefas e prompts para ChatGPT/Gemini/Claude/Manus e agentes de código.',
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
        nome=item.get('provedor','IA')+(' / '+item['modelo'] if item.get('modelo') else '')
        if item.get('ok'):
            linhas.append(f'✅ {nome} · {item.get("papel","contribuição")}: '+str(item.get('contribuicao_id','registrada')))
        else:linhas.append(f'⚠️ {nome}: '+str(item.get('erro') or item.get('mensagem') or 'indisponível'))
    if not resultado.get('resultados'):linhas.append('Nenhum provedor disponível. Use /contexto para colaborar pelos chats web ou configure Ollama.')
    linhas.append(str(resultado.get('resumo') or 'Veja as propostas na aba Chats e projeto. Nenhum código foi aplicado.'))
    return str(nucleo.redigir('\n'.join(linhas)))


def executar_acao(acao,obj,contexto,roteador):
    if acao=='chats_modelos_ollama':
        from configurar_ia_local import validar_modelo,modelo_instalado
        modelos=obj.get('modelos')
        if not isinstance(modelos,list) or not 1<=len(modelos)<=4:
            raise ValueError('Selecione entre um e quatro modelos.')
        modelos=list(dict.fromkeys(validar_modelo(nome) for nome in modelos))
        catalogo=roteador.catalogo_ollama();nomes=[item['nome'] for item in catalogo['modelos']]
        presentes=[modelo_instalado(nome,nomes) for nome in modelos]
        if None in presentes:raise ValueError('Um dos modelos não está no catálogo do seu Ollama. Atualize a lista antes de criar as conversas.')
        resultado=central.preparar_chats_modelos(contexto,presentes)
        linhas=[f'Conversas preparadas: {resultado["criados"]} nova(s). A primeira foi selecionada.']
        linhas.extend(c['id']+' | '+c['modelo_ollama'] for c in resultado['chats'])
        linhas.append('Nenhuma resposta foi gerada nem modelo baixado. Use /ia ou o teste explícito para verificar cada modelo.')
        if not catalogo.get('habilitado'):linhas.append('Configure Ollama com configurar_ia_local.bat e reinicie o assistente antes de conversar.')
        return '\n'.join(linhas)
    if acao=='modelo_testar':
        if obj.get('confirmacao')!='TESTAR MODELO':raise ValueError('Confirme TESTAR MODELO; será feita uma consulta real que pode consumir cota.')
        from configurar_ia_local import validar_modelo,modelo_instalado
        modelo=validar_modelo(campo_texto(obj,'modelo',200))
        catalogo=roteador.catalogo_ollama()
        modelo=modelo_instalado(modelo,[item['nome'] for item in catalogo['modelos']])
        if modelo is None:raise ValueError('Modelo não encontrado no catálogo Ollama.')
        texto,provedor=roteador.responder('Responda somente OK.',provedor='Ollama',modelo_ollama=modelo)
        if provedor!='Ollama' or not isinstance(texto,str) or not texto.strip():raise RuntimeError('O teste não recebeu uma resposta válida do modelo escolhido.')
        return 'Resposta recebida de '+modelo+': '+str(nucleo.redigir(texto))[:500]+'. Uma consulta concluída não mede saldo nem garante disponibilidade futura. Nenhum histórico de conversa foi enviado.'
    if acao=='chat_criar':
        chat=central.criar_chat(contexto,campo_texto(obj,'titulo',100),obj.get('provedor','auto'))
        return 'Conversa criada e selecionada: '+chat['id']
    if acao=='chat_selecionar':
        central.selecionar_chat(contexto,campo_texto(obj,'id',100));return 'Conversa selecionada.'
    if acao=='chat_provedor':
        chat_id=obj.get('id') or central.obter_chat_ativo(contexto)['id']
        central.configurar_chat(contexto,chat_id,provedor=campo_texto(obj,'provedor',30))
        return 'Provedor da conversa atualizado.'
    if acao=='chat_modelo':
        from configurar_ia_local import validar_modelo,modelo_instalado,modelo_em_nuvem
        modelo=campo_texto(obj,'modelo',200,False)
        nuvem=modelo_em_nuvem(modelo)
        chat_id=obj.get('id') or central.obter_chat_ativo(contexto)['id']
        # Verifica a propriedade do chat antes de consultar o serviço do PC.
        if chat_id not in {c['id'] for c in central.listar_chats(contexto)}:
            raise ValueError('Conversa não encontrada neste contexto.')
        if modelo:
            validar_modelo(modelo)
            catalogo=roteador.catalogo_ollama()
            encontrado=modelo_instalado(modelo,[item['nome'] for item in catalogo['modelos']])
            if not encontrado:raise ValueError('Modelo ausente do catálogo Ollama. Atualize a lista; registre o modelo no Ollama antes de selecioná-lo.')
            modelo=encontrado
            nuvem=any(item['nome']==modelo and item.get('nuvem') for item in catalogo['modelos'])
        central.configurar_chat(contexto,chat_id,provedor='Ollama',modelo_ollama=modelo)
        aviso=' Modelos em nuvem dependem de conta, internet e cota.' if modelo and nuvem else ''
        return 'Modelo da conversa atualizado: '+(modelo or 'padrão da configuração geral')+'.'+aviso
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
        resultado=consultar_equipe(campo_texto(obj,'texto',8000),roteador,provedores=obj.get('provedores'),tarefa_id=obj.get('tarefa_id') or None,confirmacao=obj.get('confirmacao',''),modelos_ollama=obj.get('modelos_ollama'))
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
