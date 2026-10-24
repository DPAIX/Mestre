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
    'chat_criar','chat_selecionar','chat_provedor','chat_modelo','chat_modo','chat_equipe','chats_modelos_ollama','modelo_testar','modelo_padrao','ollama_perfil','ollama_nuvem','tarefa_projeto','tarefa_status',
    'contribuicao_importar','contribuicao_status','conexoes_ia','equipe_ia','9router_configurar',
    'rotina_criar','rotina_remover','kanban_adicionar','kanban_mover','financeiro',
}


def campo_texto(obj,nome,limite=200,obrigatorio=True):
    valor=obj.get(nome,'')
    if not isinstance(valor,str):raise ValueError('O campo '+nome+' deve ser texto.')
    valor=valor.strip()
    if (obrigatorio and not valor) or len(valor)>limite:
        raise ValueError('Preencha '+nome+' com até '+str(limite)+' caracteres.')
    return valor


def conversar(texto,contexto,roteador,retornar_plano=False,*,progresso=None,parcial=None):
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
        from roteador_9router import configurado as nine_router_configurado
        if politica=='automatica' and nine_router_configurado():
            chat=central.configurar_roteador_automatico(contexto,chat['id'])
        elif politica=='automatica':
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
        prefixo=''
        marcador='\n\nÚLTIMA MENSAGEM DO PROPRIETÁRIO:\n'
        if retornar_plano:
            from interpretacao_natural import instrucoes_ia,extrair_resposta
            import datetime
            from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
            try:agora=datetime.datetime.now(ZoneInfo('America/Sao_Paulo'))
            except ZoneInfoNotFoundError:agora=datetime.datetime.now().astimezone()
            compacto=(os.getenv('OLLAMA_PERFIL','padrao').strip().casefold()=='cpu' and
                      bool(chat.get('equipe_paralela')) and chat.get('equipe_modo','paralela')=='cooperativa')
            prefixo=(instrucoes_ia(compacto=compacto)+'\nData/hora de referência do assistente: '+agora.isoformat(timespec='minutes')+
                     '. Datas relativas devem usar essa referência; se houver ambiguidade, pergunte.')
        # As notas são escritas manualmente após confirmação e pertencem a
        # esta conversa. Reserve espaço sem cortar o último pedido do dono.
        from memoria_assistente import contexto_chat,contexto_ia
        disponivel=min(1500,11000-len(prefixo)-len(marcador)-len(pergunta)-2)
        memoria=(contexto_ia(contexto_chat(contexto,chat['id']),texto,limite=disponivel)
                 if disponivel>=120 else '')
        if retornar_plano:
            pergunta=prefixo+('\n\n'+memoria if memoria else '')+marcador+pergunta
        elif memoria:
            pergunta=memoria+marcador+pergunta
        equipe=bool(chat.get('equipe_paralela'))
        if equipe:
            from conversa_equipe import consultar_modelos
            extras={'parcial':parcial} if parcial is not None else {}
            equipe_resultado=consultar_modelos(pergunta,historico,chat.get('equipe_modelos'),roteador,
                interpretar=retornar_plano,modo=chat.get('equipe_modo','paralela'),
                progresso=progresso,**extras)
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
            linhas.append('  Automática: usa o 9Router quando habilitado com modelo/combo; caso contrário, usa a equipe Ollama do catálogo.')
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
    # Disco, ambiente e seleção do chat devem observar a mesma configuração.
    if acao in ('ollama_perfil','modelo_padrao','ollama_nuvem','9router_configurar'):
        with _CONFIG_OLLAMA_LOCK:
            return _executar_acao(acao,obj,contexto,roteador)
    return _executar_acao(acao,obj,contexto,roteador)


def _executar_acao(acao,obj,contexto,roteador):
    if acao=='9router_configurar':
        if not isinstance(obj,dict) or set(obj)-{'acao','ativo','modelo','url','confirmacao','contexto'}:
            raise ValueError('Use somente as opções públicas de ativação, modelo e base local do 9Router. A chave só pode ser configurada no console local.')
        if obj.get('confirmacao')!='CONFIGURAR 9ROUTER':raise ValueError('Confirme CONFIGURAR 9ROUTER.')
        from configurar_9router import salvar_configuracao
        from roteador_9router import URL_PADRAO
        salvar_configuracao(obj.get('ativo'),obj.get('modelo',''),obj.get('url',URL_PADRAO),
                            caminho=nucleo.arquivo_env(nucleo.BASE))
        atualizar=getattr(type(roteador),'atualizar_configuracao_9router',None)
        if callable(atualizar):atualizar(roteador)
        nucleo.registrar('9router_configuracao','configurado','Opções públicas do 9Router atualizadas; nenhuma consulta executada.')
        return ('Configuração pública do 9Router salva. Conversas automáticas usarão o modelo/combo habilitado; escolhas manuais permanecem. '
                'Mensagens e o histórico usado na resposta podem ser encaminhados a provedores externos com cota. '
                'Nenhuma conta ou conexão foi testada. Configure a chave opcional somente no console local.')
    if acao=='ollama_nuvem':
        ativo=obj.get('ativo')
        if type(ativo) is not bool:raise ValueError('A autorização de nuvem deve ser booleana.')
        esperado='AUTORIZAR NUVEM' if ativo else 'DESATIVAR NUVEM'
        if obj.get('confirmacao')!=esperado:raise ValueError('Confirme '+esperado+'.')
        from configurar_ia_local import configurar_nuvem
        configurar_nuvem(ativo,caminho=nucleo.arquivo_env(nucleo.BASE))
        os.environ['OLLAMA_NUVEM_HABILITADA']='1' if ativo else '0'
        nucleo.registrar('ollama_nuvem','configurado','Nuvem no perfil CPU '+('autorizada' if ativo else 'restrita'))
        return ('Nuvem no perfil CPU '+('autorizada: modelos remotos registrados podem receber as próximas mensagens e histórico, usando conta, Internet e cota.' if ativo else 'restrita: próximas consultas CPU usam somente modelos locais. Consultas já enviadas não foram canceladas.')+
                ' O perfil padrão do serviço e os aplicativos externos mantêm suas próprias configurações. Nenhum modelo foi registrado, baixado ou consultado agora.')
    if acao=='ollama_perfil':
        perfil=campo_texto(obj,'perfil',20).casefold()
        if perfil not in ('cpu','padrao'):raise ValueError('Escolha o perfil cpu ou padrao.')
        if obj.get('confirmacao')!='CONFIGURAR '+perfil.upper():raise ValueError('Confirme a configuração do perfil Ollama.')
        chat=central.obter_chat_ativo(contexto)
        if obj.get('chat_id') and obj['chat_id']!=chat['id']:
            raise ValueError('Volte à conversa de origem antes de configurar o perfil.')
        from configurar_ia_local import configurar_perfil
        from multi_ia import endpoint_ollama
        url=endpoint_ollama().removesuffix('/api/chat')
        modelo=configurar_perfil(perfil,url,caminho=nucleo.arquivo_env(nucleo.BASE))
        os.environ.update({'OLLAMA_HABILITADO':'1','OLLAMA_URL':url,'OLLAMA_MODEL':modelo,'OLLAMA_PERFIL':perfil})
        roteador.atualizar_configuracao_ollama()
        central.configurar_chat(contexto,chat['id'],provedor='Ollama',modelo_ollama=modelo,modo_conversa=True)
        nucleo.registrar('ollama_perfil','configurado','Perfil '+perfil+'; modelo '+modelo,'Ollama')
        return ('Perfil '+perfil+' do Ollama salvo e aplicado. Modelo individual desta conversa: '+modelo+
                '. Equipe desativada nesta conversa; histórico preservado. '+
                ('O perfil CPU usa contexto pequeno e respostas curtas. ' if perfil=='cpu' else 'O serviço volta a escolher a execução nas próximas chamadas. ')+
                'Esse perfil vale globalmente para as próximas consultas Ollama deste assistente. '
                'Não houve geração, download ou alteração de driver. Envie uma mensagem curta para testar.')
    if acao=='chat_equipe':
        ativo=obj.get('ativo')
        if not isinstance(ativo,bool):raise ValueError('O modo equipe deve ser verdadeiro ou falso.')
        modo=obj.get('modo','cooperativa')
        if modo not in ('cooperativa','paralela'):raise ValueError('Escolha equipe cooperativa ou paralela.')
        chat=central.obter_chat_ativo(contexto)
        if obj.get('id') and obj['id']!=chat['id']:raise ValueError('Selecione a conversa antes de configurar a equipe.')
        if not ativo:
            central.configurar_chat(contexto,chat['id'],equipe_paralela=False,equipe_modelos=[])
            return 'Equipe desativada nesta conversa. O modelo individual será utilizado.'
        catalogo=roteador.catalogo_ollama()
        if not catalogo.get('habilitado'):raise ValueError('Habilite a integração Ollama antes de ativar a equipe.')
        modelos=list(dict.fromkeys(m['nome'] for m in catalogo['modelos']))
        if not 1<=len(modelos)<=8:raise ValueError('O catálogo precisa ter entre um e oito modelos para ativar todos.')
        central.configurar_chat(contexto,chat['id'],provedor='Ollama',modo_conversa=True,
            equipe_modelos=modelos,equipe_paralela=True,equipe_modo=modo)
        nuvem=any(m.get('nuvem') for m in catalogo['modelos'])
        return ('Equipe '+modo+' ativada nesta conversa: '+', '.join(modelos)+
            ('. Cada mensagem que precisar de IA consulta uma vez cada modelo, um por vez, e pode fazer uma síntese adicional. O perfil CPU atual é preservado. '
             if modo=='cooperativa' else '. Cada mensagem de conversa consulta uma vez cada modelo simultaneamente. O Ollama pode enfileirar conforme a memória. ')+
            'Nenhum modelo foi baixado ou consultado nesta ativação.'+
            (' Há modelos cloud: as mensagens usam a conta, internet e cota Ollama.' if nuvem else ''))
    if acao=='modelo_padrao':
        from configurar_ia_local import configurar_modelo
        from multi_ia import endpoint_ollama
        modelo=campo_texto(obj,'modelo',200)
        chat=central.obter_chat_ativo(contexto)
        url=endpoint_ollama().removesuffix('/api/chat')
        encontrado=configurar_modelo(modelo,url,caminho=nucleo.arquivo_env(nucleo.BASE))
        os.environ.update({'OLLAMA_HABILITADO':'1','OLLAMA_URL':url,'OLLAMA_MODEL':encontrado})
        roteador.atualizar_configuracao_ollama()
        central.configurar_chat(contexto,chat['id'],provedor='Ollama',modelo_ollama='')
        nucleo.registrar('modelo_padrao','configurado','Modelo Ollama selecionado: '+encontrado,'Ollama')
        return ('Padrão do Ollama atualizado: '+encontrado+'. Esta conversa agora usa Ollama com esse padrão; seu histórico foi preservado. '
                'Configuração salva e carregada. Pausas de outros provedores não foram alteradas. '
                'A presença no catálogo foi verificada, sem gerar resposta nem baixar modelos. Use /modelos testar '+encontrado+
                ' ou /ia para testar. Modelos cloud dependem de conta, internet e cota.')
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
