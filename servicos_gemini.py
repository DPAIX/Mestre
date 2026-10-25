"""Tarefas Gemini isoladas por proprietário, tópico e conversa.

Os registros locais permitem acompanhar uma tarefa sem reenviar o pedido.
Conteúdo retornado é referência/proposta; nunca é executado no computador.
"""
from __future__ import annotations
import copy
import datetime as dt
import json
from pathlib import Path
import re
import stat
import threading
import uuid
import nucleo
import gemini_interactions as api
from memoria_assistente import contexto_chat

_OPERACAO = threading.Lock()
MAX_TAREFAS = 25
MAX_PERFIS = 10


def _nome(contexto, chat_id):
    return 'gemini_' + contexto_chat(contexto, chat_id) + '.json'


def _ler(contexto, chat_id):
    arquivo = nucleo.DADOS / _nome(contexto, chat_id)
    if arquivo.is_symlink(): raise ValueError('Registro Gemini inválido; arquivo preservado.')
    if not arquivo.exists(): return {'versao': 1, 'tarefas': [], 'perfis': []}
    meta = arquivo.lstat()
    if (not stat.S_ISREG(meta.st_mode) or meta.st_size > 700000 or
            bool(getattr(meta, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))):
        raise ValueError('Registro Gemini inválido; arquivo preservado.')
    dados = nucleo.ler_json(arquivo.name, None)
    if (not isinstance(dados, dict) or dados.get('versao') != 1 or
        not isinstance(dados.get('tarefas'), list) or len(dados['tarefas']) > MAX_TAREFAS or
        not isinstance(dados.get('perfis'), list) or len(dados['perfis']) > MAX_PERFIS):
        raise ValueError('Registro Gemini inválido; arquivo preservado.')
    for tarefa in dados['tarefas']:
        if (not isinstance(tarefa, dict) or not re.fullmatch(r'g[a-f0-9]{16}', str(tarefa.get('id', ''))) or
            not isinstance(tarefa.get('estado'), str) or not isinstance(tarefa.get('texto', ''), str) or
            len(tarefa.get('texto', '')) > 12000):
            raise ValueError('Tarefa Gemini inválida; arquivo preservado.')
        if tarefa.get('remote_id'): api.validar_id(tarefa['remote_id'])
        api.validar_id(tarefa.get('agente'))
    for perfil in dados['perfis']:
        if not isinstance(perfil, dict): raise ValueError('Perfil Gemini inválido; arquivo preservado.')
        api.validar_id(perfil.get('id'))
    return dados


def estado(contexto, chat_id):
    with nucleo._LOCK:
        dados = _ler(contexto, chat_id)
        return {'configuracao': api.diagnostico_local(), 'tarefas': copy.deepcopy(dados['tarefas']),
                'perfis': copy.deepcopy(dados['perfis']), 'chat_id': chat_id}


def _salvar(contexto, chat_id, dados):
    nucleo.gravar_json(_nome(contexto, chat_id), dados)


def _achar(dados, ident):
    if not isinstance(ident, str) or not re.fullmatch(r'g[a-f0-9]{16}', ident):
        raise ValueError('Informe o ID local de uma tarefa desta conversa.')
    for tarefa in dados['tarefas']:
        if tarefa['id'] == ident: return tarefa
    raise ValueError('Tarefa não encontrada nesta conversa.')


def preparar_tarefa(texto, agente=api.AGENTE_PADRAO, *, rede=False, anterior=''):
    if not isinstance(texto, str) or not 1 <= len(texto.strip()) <= 6000: raise ValueError('Descreva uma tarefa de até 6000 caracteres.')
    if type(rede) is not bool: raise ValueError('A permissão de rede deve ser booleana.')
    api.validar_id(agente)
    if anterior and not re.fullmatch(r'g[a-f0-9]{16}', str(anterior)): raise ValueError('Selecione uma tarefa anterior desta conversa.')
    return {'acao': 'gemini_tarefa', 'campos': {'operacao': 'g' + uuid.uuid4().hex[:16],
        'texto': api.seguro(texto.strip()), 'agente': agente, 'rede': rede, 'anterior': anterior},
        'descricao': ('Enviar esta tarefa ao agente Gemini ' + agente[:100] +
            ' em segundo plano. Usa Internet, chave e cota da API, com registro remoto da interação. '
            + ('O sandbox terá rede externa. ' if rede else 'O sandbox Antigravity terá rede desativada. ')
            + 'Nenhum arquivo ou histórico local é enviado automaticamente. Pedido: ' + api.seguro(texto)[:120])[:500]}


def validar_plano(plano):
    acao, campos = plano.get('acao'), plano.get('campos')
    if not isinstance(campos, dict): raise ValueError('Campos Gemini inválidos.')
    if acao == 'gemini_tarefa':
        if set(campos) != {'operacao', 'texto', 'agente', 'rede', 'anterior'}: raise ValueError('Campos da tarefa inválidos.')
        if not re.fullmatch(r'g[a-f0-9]{16}', str(campos['operacao'])): raise ValueError('Operação inválida.')
        base = preparar_tarefa(campos['texto'], campos['agente'], rede=campos['rede'], anterior=campos['anterior'])
        base['campos']['operacao'] = campos['operacao']
        return base
    if acao in ('gemini_cancelar', 'gemini_excluir', 'gemini_contribuir'):
        if set(campos) != {'id'} or not re.fullmatch(r'g[a-f0-9]{16}', str(campos['id'])): raise ValueError('ID da tarefa inválido.')
        verbos = {'gemini_cancelar': 'Solicitar cancelamento da tarefa remota',
                  'gemini_excluir': 'Excluir a interação remota e o registro local concluído',
                  'gemini_contribuir': 'Registrar o resultado como proposta no projeto, sem executar código'}
        return {'acao': acao, 'campos': dict(campos), 'descricao': verbos[acao] + ': ' + campos['id']}
    if acao == 'gemini_perfil_criar':
        if set(campos) != {'operacao', 'titulo', 'instrucoes', 'rede'}: raise ValueError('Campos do perfil inválidos.')
        if not re.fullmatch(r'g[a-f0-9]{16}', str(campos['operacao'])): raise ValueError('Operação inválida.')
        for nome, limite in (('titulo', 80), ('instrucoes', 6000)):
            if not isinstance(campos[nome], str) or not 1 <= len(campos[nome].strip()) <= limite: raise ValueError('Preencha ' + nome + '.')
        if type(campos['rede']) is not bool: raise ValueError('Permissão de rede inválida.')
        return {'acao': acao, 'campos': {**campos, 'titulo': api.seguro(campos['titulo']), 'instrucoes': api.seguro(campos['instrucoes'])},
                'descricao': 'Criar agente gerenciado Gemini no projeto da sua chave: ' + api.seguro(campos['titulo']) + '. Usa API/conta e ambiente remoto; não instala nem executa ferramentas neste PC.'}
    if acao == 'gemini_perfil_excluir':
        if set(campos) != {'id'}: raise ValueError('Campos do perfil inválidos.')
        api.validar_id(campos['id'])
        return {'acao': acao, 'campos': dict(campos), 'descricao': 'Excluir do projeto Gemini este perfil criado nesta conversa: ' + campos['id']}
    raise ValueError('Operação Gemini não permitida.')


def _atualizar(contexto, chat_id, ident, resposta):
    with nucleo._LOCK:
        dados = _ler(contexto, chat_id); tarefa = _achar(dados, ident)
        if tarefa.get('remote_id') and resposta['remote_id'] != tarefa['remote_id']:
            raise ValueError('A API devolveu outra interação; registro local preservado.')
        tarefa.update(resposta)
        tarefa['atualizado_em'] = dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')
        _salvar(contexto, chat_id, dados)
        return copy.deepcopy(tarefa)


def consultar(contexto, chat_id, ident):
    with nucleo._LOCK: tarefa = copy.deepcopy(_achar(_ler(contexto, chat_id), ident))
    if not tarefa.get('remote_id'):
        raise ValueError('O ID remoto não foi confirmado. Confira o AI Studio antes de enviar outro pedido.')
    if not _OPERACAO.acquire(blocking=False): raise RuntimeError('Há uma operação Gemini em andamento; aguarde.')
    try: return _atualizar(contexto, chat_id, ident, api.consultar_tarefa(tarefa['remote_id']))
    finally: _OPERACAO.release()


def executar(plano, contexto, chat_id):
    plano = validar_plano(plano); acao, campos = plano['acao'], plano['campos']
    if not _OPERACAO.acquire(blocking=False): raise RuntimeError('Há uma operação Gemini em andamento; aguarde.')
    try:
        if acao == 'gemini_tarefa':
            ident = campos['operacao']
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id)
                existente = next((t for t in dados['tarefas'] if t['id'] == ident), None)
                if existente: return 'Tarefa já registrada: ' + ident + ' (' + existente['estado'] + '). Consulte seu estado; não foi reenviada.'
                if len(dados['tarefas']) >= MAX_TAREFAS: raise ValueError('Limite de tarefas atingido; exclua um registro concluído.')
                anterior = copy.deepcopy(_achar(dados, campos['anterior'])) if campos['anterior'] else None
                if anterior and (not anterior.get('remote_id') or anterior['agente'] != campos['agente'] or anterior['estado'] != 'completed'):
                    raise ValueError('Continue apenas uma tarefa concluída do mesmo agente nesta conversa.')
                dados['tarefas'].append({'id': ident, 'agente': campos['agente'], 'titulo': campos['texto'][:120],
                    'estado': 'enviando', 'texto': '', 'remote_id': '', 'ambiente_id': '', 'anterior': campos['anterior']})
                _salvar(contexto, chat_id, dados)
            try:
                resposta = api.criar_tarefa(campos['texto'], campos['agente'], rede=campos['rede'], anterior=anterior, confirmado=True)
                tarefa = _atualizar(contexto, chat_id, ident, resposta)
            except Exception as erro:
                from multi_ia import FalhaAPI
                with nucleo._LOCK:
                    dados = _ler(contexto, chat_id)
                    rejeitado = isinstance(erro, FalhaAPI) and (erro.categoria == 'configuracao' or 400 <= erro.codigo < 500 and erro.codigo not in (408, 409))
                    _achar(dados, ident)['estado'] = 'nao_enviada' if rejeitado else 'resultado_incerto'
                    _salvar(contexto, chat_id, dados)
                raise
            return 'Tarefa Gemini registrada: ' + ident + ' | ' + tarefa['estado'] + '. Consulte pelo painel ou /gemini consultar ' + ident + '. Nenhuma execução local foi realizada.'
        if acao == 'gemini_perfil_criar':
            ident = 'meucontrolepc-' + contexto_chat(contexto, chat_id)[:12] + '-' + campos['operacao'][1:]
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id)
                if any(p['id'] == ident for p in dados['perfis']): return 'Perfil já registrado: ' + ident
                if len(dados['perfis']) >= MAX_PERFIS: raise ValueError('Limite de perfis atingido.')
            api.criar_perfil(ident, campos['instrucoes'], rede=campos['rede'], confirmado=True)
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id)
                dados['perfis'].append({'id': ident, 'titulo': campos['titulo']})
                _salvar(contexto, chat_id, dados)
            return 'Agente gerenciado criado: ' + ident
        if acao == 'gemini_perfil_excluir':
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id)
                if not any(p['id'] == campos['id'] for p in dados['perfis']): raise ValueError('Perfil não encontrado nesta conversa.')
            api.excluir_perfil(campos['id'], confirmado=True)
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id); dados['perfis'] = [p for p in dados['perfis'] if p['id'] != campos['id']]
                _salvar(contexto, chat_id, dados)
            return 'Perfil Gemini excluído.'
        with nucleo._LOCK: tarefa = copy.deepcopy(_achar(_ler(contexto, chat_id), campos['id']))
        if acao == 'gemini_contribuir':
            if tarefa['estado'] != 'completed' or not tarefa['texto'].strip(): raise ValueError('Aguarde um resultado concluído com texto.')
            if tarefa.get('contribuicao_id'): return 'Proposta já registrada: ' + tarefa['contribuicao_id']
            from colaboracao_chats import importar_contribuicao
            proposta = importar_contribuicao(('Gemini / ' + tarefa['agente'])[:80], tarefa['titulo'][:150], tarefa['texto'])
            with nucleo._LOCK:
                dados = _ler(contexto, chat_id); _achar(dados, tarefa['id'])['contribuicao_id'] = proposta['id']; _salvar(contexto, chat_id, dados)
            return 'Proposta registrada para revisão: ' + proposta['id'] + '. Nenhum arquivo de código foi alterado.'
        if not tarefa.get('remote_id'):
            if acao == 'gemini_excluir' and tarefa['estado'] == 'nao_enviada':
                with nucleo._LOCK:
                    dados = _ler(contexto, chat_id)
                    dados['tarefas'] = [t for t in dados['tarefas'] if t['id'] != tarefa['id']]
                    _salvar(contexto, chat_id, dados)
                return 'Registro local de operação recusada excluído; nenhuma chamada remota foi feita nesta exclusão.'
            raise ValueError('Interação remota não confirmada; confira o AI Studio.')
        if acao == 'gemini_cancelar':
            atual = _atualizar(contexto, chat_id, tarefa['id'], api.cancelar_tarefa(tarefa['remote_id'], confirmado=True))
            return 'Estado após solicitar cancelamento: ' + atual['estado']
        if tarefa['estado'] not in ('completed', 'failed', 'cancelled', 'canceled'):
            raise ValueError('Cancele e atualize a tarefa antes de excluir uma interação em andamento.')
        api.excluir_interacao(tarefa['remote_id'], confirmado=True)
        with nucleo._LOCK:
            dados = _ler(contexto, chat_id); dados['tarefas'] = [t for t in dados['tarefas'] if t['id'] != tarefa['id']]; _salvar(contexto, chat_id, dados)
        return 'Interação Gemini e registro local excluídos.'
    finally: _OPERACAO.release()
