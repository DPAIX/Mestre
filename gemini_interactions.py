"""Interactions e agentes Gemini: chamadas explícitas, sem ferramentas no PC.

Modelos usam store=False. Tarefas de agentes usam background/store=True e podem
ser consultadas/canceladas pelo proprietário; nenhuma consulta é repetida aqui.
Referências: ai.google.dev/gemini-api/docs/interactions-overview e /custom-agents.
"""
from __future__ import annotations
import importlib.util
import os
import re

AGENTE_PADRAO = 'antigravity-preview-09-2026'
AGENTES = (AGENTE_PADRAO, 'deep-research-preview-04-2026', 'deep-research-max-preview-04-2026')


def seguro(texto):
    from nucleo import redigir
    texto = str(texto)
    for nome in ('GEMINI_API_KEY', 'GOOGLE_API_KEY'):
        chave = os.getenv(nome, '')
        if chave: texto = texto.replace(chave, '[credencial omitida]')
    return str(redigir(texto))


def validar_id(valor):
    if not isinstance(valor, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:=+\-]{0,299}', valor):
        raise ValueError('Identificador Gemini inválido.')
    return valor


def diagnostico_local():
    try: sdk = importlib.util.find_spec('google.genai') is not None
    except (ImportError, ModuleNotFoundError, ValueError): sdk = False
    return {'sdk_presente': sdk, 'chave_definida': bool(os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')),
            'modo': os.getenv('GEMINI_API_MODO', 'generate_content'), 'agente_padrao': AGENTE_PADRAO,
            'agentes': list(AGENTES), 'conexao_testada': False}


def _cliente():
    from multi_ia import FalhaAPI
    chave = os.getenv('GEMINI_API_KEY') or os.getenv('GOOGLE_API_KEY')
    if not chave: raise FalhaAPI('Gemini', 0, 'Configure a chave Gemini no console local.', 'configuracao')
    try: from google import genai
    except ImportError:
        raise FalhaAPI('Gemini', 0, 'Atualize google-genai>=2.9 com atualizar_assistente.bat.', 'configuracao') from None
    import httpx
    # Algumas versões normalizam attempts=0 para 1 e ainda repetem a chamada.
    # O hook público do transporte impede uma segunda saída antes da rede.
    chamadas = {'enviadas': 0, 'status': 0}
    def antes_da_requisicao(_pedido):
        if chamadas['enviadas']:
            from multi_ia import analisar_erro
            if chamadas['status']:
                raise analisar_erro('Gemini', chamadas['status'], 'A API recusou a operação; nenhuma nova tentativa foi enviada.')
            raise FalhaAPI('Gemini', 0, 'O resultado remoto não foi confirmado. Confira o AI Studio antes de repetir; nenhuma nova tentativa foi enviada.', 'tempo_esgotado')
        chamadas['enviadas'] += 1
    def depois_da_resposta(resposta):
        chamadas['status'] = resposta.status_code
    transporte = httpx.Client(timeout=30, event_hooks={
        'request': [antes_da_requisicao], 'response': [depois_da_resposta]})
    return genai.Client(api_key=chave, vertexai=False, http_options={
        'api_version': 'v1beta', 'base_url': 'https://generativelanguage.googleapis.com',
        'timeout': 30000, 'retry_options': {'attempts': 1}, 'httpx_client': transporte})


def _chamar(grupo, metodo, **opcoes):
    from multi_ia import FalhaAPI, analisar_erro
    cliente = None
    try:
        cliente = _cliente()
        recurso = getattr(cliente, grupo, None)
        funcao = getattr(recurso, metodo, None)
        if not callable(funcao):
            raise FalhaAPI('Gemini', 0, 'O SDK instalado não oferece esta operação. Atualize as dependências.', 'configuracao')
        return funcao(**opcoes)
    except FalhaAPI: raise
    except Exception as erro:
        codigo = getattr(erro, 'code', getattr(erro, 'status_code', 0))
        try: codigo = int(codigo)
        except (ValueError, TypeError): codigo = 0
        detalhe = seguro(str(erro))[:1000]
        if not codigo and any(t in detalhe.casefold() for t in ('timeout', 'timed out', 'connection', 'network')):
            raise FalhaAPI('Gemini', 0, 'A resposta da operação remota não foi confirmada. Confira o AI Studio antes de repetir; nenhuma nova tentativa foi enviada.', 'tempo_esgotado') from None
        raise analisar_erro('Gemini', codigo, detalhe) from None
    finally:
        if cliente is not None:
            fechar = getattr(cliente, 'close', None)
            if callable(fechar):
                try: fechar()
                except Exception: pass


def _campo(obj, nome, padrao=None):
    return obj.get(nome, padrao) if isinstance(obj, dict) else getattr(obj, nome, padrao)


def _texto(obj):
    texto = _campo(obj, 'output_text')
    if isinstance(texto, str) and texto.strip(): return seguro(texto)[:12000]
    partes = []
    for passo in (_campo(obj, 'steps', []) or [])[:100]:
        if _campo(passo, 'type') != 'model_output': continue
        for conteudo in (_campo(passo, 'content', []) or [])[:50]:
            if _campo(conteudo, 'type') == 'text' and isinstance(_campo(conteudo, 'text'), str):
                partes.append(_campo(conteudo, 'text')[:12000])
    return seguro('\n'.join(partes))[:12000]


def resumir_interacao(obj):
    estado = str(_campo(obj, 'status', 'unknown'))
    if estado not in ('completed', 'in_progress', 'requires_action', 'cancelled', 'canceled', 'failed', 'queued'):
        estado = 'unknown'
    ident = validar_id(_campo(obj, 'id'))
    ambiente = _campo(obj, 'environment_id', '') or ''
    if ambiente: ambiente = validar_id(ambiente)
    return {'remote_id': ident, 'estado': estado, 'texto': _texto(obj), 'ambiente_id': ambiente}


def responder(pergunta, historico=None):
    from multi_ia import preparar_mensagens, SISTEMA, FalhaAPI
    passos = [{'type': 'model_output' if m['role'] == 'assistant' else 'user_input',
               'content': [{'type': 'text', 'text': seguro(m['content'])}]}
              for m in preparar_mensagens(pergunta, historico)]
    resposta = _chamar('interactions', 'create', model=os.getenv('GEMINI_MODEL', 'gemini-3.8-flash'),
        input=passos, system_instruction=SISTEMA, store=False, background=False,
        generation_config={'max_output_tokens': 1024})
    texto = _texto(resposta)
    if not texto.strip(): raise FalhaAPI('Gemini', 0, 'Interactions não devolveu texto; nenhuma ferramenta foi executada no PC.', 'resposta_invalida')
    return texto


def criar_tarefa(texto, agente=AGENTE_PADRAO, *, rede=False, anterior=None, confirmado=False):
    if confirmado is not True: raise PermissionError('Confirme o envio à nuvem Gemini e o uso de cota.')
    agente = validar_id(agente)
    if not isinstance(texto, str) or not 1 <= len(texto.strip()) <= 6000: raise ValueError('Descreva uma tarefa de até 6000 caracteres.')
    if type(rede) is not bool: raise ValueError('A permissão de rede deve ser booleana.')
    opcoes = {'agent': agente, 'input': seguro(texto.strip()), 'background': True, 'store': True}
    if agente.startswith('antigravity-') or agente.startswith('meucontrolepc-'):
        opcoes['environment'] = {'type': 'remote', **({} if rede else {'network': 'disabled'})}
    elif rede:
        raise ValueError('A opção de rede do sandbox aplica-se aos agentes Antigravity e perfis deste assistente.')
    if anterior:
        opcoes['previous_interaction_id'] = validar_id(anterior['remote_id'])
        if anterior.get('ambiente_id') and 'environment' in opcoes:
            opcoes['environment'] = {'type': 'remote', 'environment_id': validar_id(anterior['ambiente_id']),
                                    **({} if rede else {'network': 'disabled'})}
    return resumir_interacao(_chamar('interactions', 'create', **opcoes))


def consultar_tarefa(ident):
    return resumir_interacao(_chamar('interactions', 'get', id=validar_id(ident)))


def cancelar_tarefa(ident, *, confirmado=False):
    if confirmado is not True: raise PermissionError('Confirme o cancelamento da tarefa Gemini.')
    return resumir_interacao(_chamar('interactions', 'cancel', id=validar_id(ident)))


def excluir_interacao(ident, *, confirmado=False):
    if confirmado is not True: raise PermissionError('Confirme a exclusão do registro remoto Gemini.')
    _chamar('interactions', 'delete', id=validar_id(ident))


def criar_perfil(ident, instrucoes, *, rede=False, confirmado=False):
    if confirmado is not True: raise PermissionError('Confirme a criação do agente no projeto Gemini.')
    ident = validar_id(ident)
    if not ident.startswith('meucontrolepc-'): raise ValueError('Use um identificador de agente deste assistente.')
    if not isinstance(instrucoes, str) or not 1 <= len(instrucoes.strip()) <= 6000: raise ValueError('Informe instruções de até 6000 caracteres.')
    if type(rede) is not bool: raise ValueError('A permissão de rede deve ser booleana.')
    resposta = _chamar('agents', 'create', id=ident, base_agent=AGENTE_PADRAO,
        system_instruction=seguro(instrucoes.strip()),
        base_environment={'type': 'remote', **({} if rede else {'network': 'disabled'})})
    if validar_id(_campo(resposta, 'id')) != ident: raise ValueError('O projeto devolveu outro identificador de agente.')
    return ident


def excluir_perfil(ident, *, confirmado=False):
    if confirmado is not True: raise PermissionError('Confirme a exclusão do agente Gemini.')
    ident = validar_id(ident)
    if not ident.startswith('meucontrolepc-'): raise ValueError('Somente perfis criados por este assistente podem ser excluídos.')
    _chamar('agents', 'delete', id=ident)
