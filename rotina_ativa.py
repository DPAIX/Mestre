"""Rotina editável e lembretes locais, ativados explicitamente pelo proprietário.

Este módulo não conecta ao Telegram nem chama provedores de IA. O agendador
recebe callbacks do aplicativo para autorizar e entregar cada mensagem.
"""
from __future__ import annotations

import datetime as dt
import re
import unicodedata
import uuid
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import nucleo

ARQUIVO_LEMBRETES = 'lembretes.json'
FUSO = 'America/Sao_Paulo'
COLUNAS = ('A_Fazer', 'Em_Andamento', 'Concluido')
DIAS = ('Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo')
CAMPOS_TAREFA = {'atividade', 'dia', 'horario', 'fim', 'local', 'prioridade'}
JANELA_ATRASO_SEG = 120
RESERVA_SEG = 120
MAX_TENTATIVAS = 3


def _agora():
    return dt.datetime.now(dt.timezone.utc)


def _fuso():
    try:
        return ZoneInfo(FUSO)
    except ZoneInfoNotFoundError:
        raise RuntimeError('Base de fusos ausente. Instale tzdata no ambiente Python para ativar os lembretes.') from None


def _instante(agora=None):
    valor = _agora() if agora is None else agora
    if not isinstance(valor, dt.datetime) or valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError('Informe uma data e hora com fuso horário.')
    return valor.astimezone(dt.timezone.utc)


def _texto(valor, nome, limite, obrigatorio=False):
    if not isinstance(valor, str):
        raise ValueError(nome+' deve ser um texto.')
    valor = valor.strip()
    if (obrigatorio and not valor) or len(valor) > limite:
        raise ValueError(f'{nome} deve ter '+(f'de 1 a {limite}' if obrigatorio else f'até {limite}')+' caracteres.')
    return str(nucleo.redigir(valor))


def _normalizar(valor):
    return ''.join(c for c in unicodedata.normalize('NFD', valor.casefold()) if not unicodedata.combining(c))


def _dia(valor):
    valor = _texto(valor, 'Dia', 20, True)
    normal = _normalizar(valor).removesuffix('-feira')
    for dia in DIAS:
        if _normalizar(dia) == normal:
            return dia
    try:
        data = dt.date.fromisoformat(valor)
    except ValueError:
        raise ValueError('Dia inválido. Use Segunda a Domingo ou uma data YYYY-MM-DD.') from None
    if data.isoformat() != valor:
        raise ValueError('Use a data no formato YYYY-MM-DD.')
    return valor


def _hora(valor, nome='Horário', opcional=False):
    valor = _texto(valor, nome, 5, not opcional)
    if not valor and opcional:
        return ''
    if not re.fullmatch(r'\d{2}:\d{2}', valor):
        raise ValueError(nome+' deve usar HH:MM.')
    try:
        dt.time.fromisoformat(valor)
    except ValueError:
        raise ValueError(nome+' inválido.') from None
    return valor


def _validar_tarefa(atividade, dia, horario, fim='', local='', prioridade='Normal'):
    return {'atividade': _texto(atividade, 'Atividade', 300, True),
            'dia': _dia(dia), 'horario': _hora(horario),
            'fim': _hora(fim, 'Fim', opcional=True),
            'local': _texto(local, 'Local', 200),
            'prioridade': _texto(prioridade, 'Prioridade', 40, True)}


def cadastrar_tarefa(atividade, dia, horario, fim='', local='', prioridade='Normal'):
    item = _validar_tarefa(atividade, dia, horario, fim, local, prioridade)
    item.update({'id': 'rotina_'+uuid.uuid4().hex[:12], 'status': 'Pendente', 'categoria': 'Manual'})
    with nucleo._LOCK:
        vida = nucleo.vida()
        tarefas = vida.setdefault('rotina', [])
        if not isinstance(tarefas, list):
            raise ValueError('A rotina armazenada deve ser uma lista; arquivo preservado.')
        if len(tarefas) >= 1000:
            raise ValueError('Limite de 1000 atividades alcançado.')
        tarefas.append(item)
        nucleo.gravar_json('gestao_vida.json', vida)
    return item.copy()


def atualizar_tarefa(id_tarefa, **campos):
    if not campos or any(campo not in CAMPOS_TAREFA for campo in campos):
        raise ValueError('Informe somente atividade, dia, horario, fim, local e prioridade.')
    with nucleo._LOCK:
        vida = nucleo.vida()
        for item in vida.get('rotina', []):
            if isinstance(item, dict) and str(item.get('id')) == str(id_tarefa):
                atuais = {campo: item.get(campo, 'Normal' if campo == 'prioridade' else '') for campo in CAMPOS_TAREFA}
                atuais.update(campos)
                item.update(_validar_tarefa(**atuais))
                nucleo.gravar_json('gestao_vida.json', vida)
                return item.copy()
    raise ValueError('Atividade não encontrada.')


def remover_tarefa(id_tarefa):
    with nucleo._LOCK:
        vida = nucleo.vida()
        tarefas = vida.get('rotina', [])
        if not isinstance(tarefas, list):
            raise ValueError('A rotina armazenada deve ser uma lista; arquivo preservado.')
        restantes = [item for item in tarefas if not isinstance(item, dict) or str(item.get('id')) != str(id_tarefa)]
        if len(restantes) == len(tarefas):
            return False
        vida['rotina'] = restantes
        nucleo.gravar_json('gestao_vida.json', vida)
    return True


def mover_kanban(origem, indice, destino):
    if origem not in COLUNAS or destino not in COLUNAS or origem == destino:
        raise ValueError('Escolha colunas de origem e destino diferentes e válidas.')
    if isinstance(indice, bool) or not isinstance(indice, int) or indice < 0:
        raise ValueError('Índice do cartão inválido.')
    with nucleo._LOCK:
        vida = nucleo.vida()
        kanban = vida.setdefault('kanban', {})
        fonte = kanban.get(origem, [])
        alvo = kanban.get(destino, [])
        if not isinstance(fonte, list) or not isinstance(alvo, list) or indice >= len(fonte):
            raise ValueError('Cartão não encontrado ou coluna inválida; dados preservados.')
        item = fonte.pop(indice)
        alvo.append(item)
        kanban[origem] = fonte
        kanban[destino] = alvo
        nucleo.gravar_json('gestao_vida.json', vida)
    return {'origem': origem, 'destino': destino, 'indice': len(alvo)-1, 'texto': item}


def _estado():
    valor = nucleo.ler_json(ARQUIVO_LEMBRETES, {})
    if not isinstance(valor, dict):
        raise ValueError('Configuração de lembretes inválida; arquivo preservado.')
    padrao = {'versao': 1, 'ativo': False, 'fuso': FUSO, 'agua_intervalo_min': 60,
              'chat_id': None, 'user_id': None, 'proxima_agua_em': None, 'eventos': {}}
    padrao.update(valor)
    if not isinstance(padrao['eventos'], dict):
        raise ValueError('Histórico de lembretes inválido; arquivo preservado.')
    return padrao


def estado_lembretes():
    with nucleo._LOCK:
        estado = _estado()
        eventos = list(estado['eventos'].values())
        return {chave: estado[chave] for chave in ('ativo', 'fuso', 'agua_intervalo_min', 'chat_id', 'user_id', 'proxima_agua_em')} | {
            'pendentes': sum(isinstance(e, dict) and e.get('estado') == 'pendente' for e in eventos),
            'enviados': sum(isinstance(e, dict) and e.get('estado') == 'enviado' for e in eventos),
            'falhas': sum(isinstance(e, dict) and e.get('estado') == 'falha' for e in eventos)}


def configurar_lembretes(ativo, agua_intervalo_min=60, chat_id=None, user_id=None):
    if not isinstance(ativo, bool):
        raise ValueError('Ativo deve ser verdadeiro ou falso.')
    if isinstance(agua_intervalo_min, bool) or not isinstance(agua_intervalo_min, int) or not 15 <= agua_intervalo_min <= 720:
        raise ValueError('Intervalo de água deve ser inteiro entre 15 e 720 minutos.')
    if ativo:
        if isinstance(chat_id, bool) or not isinstance(chat_id, int) or chat_id == 0:
            raise ValueError('Informe o chat Telegram autorizado para os lembretes.')
        if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id <= 0:
            raise ValueError('Informe o proprietário autorizado para os lembretes.')
        _fuso()
    with nucleo._LOCK:
        estado = _estado()
        agora = _agora().timestamp()
        mesmos = estado.get('chat_id') == chat_id and estado.get('user_id') == user_id
        manter_prazo = estado.get('ativo') is True and ativo and mesmos and estado.get('agua_intervalo_min') == agua_intervalo_min
        estado.update({'ativo': ativo, 'fuso': FUSO, 'agua_intervalo_min': agua_intervalo_min})
        if ativo:
            estado.update({'chat_id': chat_id, 'user_id': user_id,
                           'proxima_agua_em': estado.get('proxima_agua_em') if manter_prazo else agora+agua_intervalo_min*60})
            if not mesmos:
                estado['eventos'] = {}
        else:
            # Reservas pendentes não devem reaparecer quando o usuário reativar depois.
            estado['eventos'] = {k: e for k, e in estado['eventos'].items() if isinstance(e, dict) and e.get('estado') == 'enviado'}
            estado['proxima_agua_em'] = None
        nucleo.gravar_json(ARQUIVO_LEMBRETES, estado)
    return estado_lembretes()


def _ocorrencia(item, data, fuso):
    dia = _dia(item.get('dia', ''))
    if dia != DIAS[data.weekday()] and dia != data.isoformat():
        return None
    horario = dt.time.fromisoformat(_hora(item.get('horario', '')))
    alvo = dt.datetime.combine(data, horario, tzinfo=fuso)
    # Em mudanças históricas de horário de verão há horas que não existiram.
    if alvo.astimezone(dt.timezone.utc).astimezone(fuso).replace(tzinfo=None) != alvo.replace(tzinfo=None):
        return None
    return alvo.astimezone(dt.timezone.utc)


def _adicionar_evento(estado, chave, texto, tipo, vencimento):
    if chave not in estado['eventos']:
        estado['eventos'][chave] = {'chave': chave, 'texto': str(nucleo.redigir(texto)), 'tipo': tipo,
                                   'chat_id': estado['chat_id'], 'user_id': estado['user_id'],
                                   'estado': 'pendente', 'tentativas': 0, 'reserva_ate': 0,
                                   'vence_em': vencimento}


def processar_lembretes(agora=None):
    """Reserva avisos vencendo agora; confirmação de entrega é feita separadamente.

    Avisos da rotina têm tolerância de dois minutos. Paradas prolongadas não
    disparam todos os compromissos antigos. Hidratação gera no máximo um aviso
    por ciclo e começa a contar a partir da ativação explícita.
    """
    instante = _instante(agora)
    epoch = instante.timestamp()
    fuso = _fuso()
    with nucleo._LOCK:
        estado = _estado()
        if estado.get('ativo') is not True:
            return []
        chat_id = estado.get('chat_id'); user_id = estado.get('user_id')
        if not isinstance(chat_id, int) or isinstance(chat_id, bool) or not chat_id or not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
            raise ValueError('Reative os lembretes com um chat e proprietário autorizados.')
        hoje = instante.astimezone(fuso).date()
        tarefas = nucleo.vida().get('rotina', [])
        if not isinstance(tarefas, list):
            raise ValueError('Rotina inválida; os lembretes não alteraram o arquivo.')
        for item in tarefas:
            if not isinstance(item, dict) or not item.get('id') or _normalizar(str(item.get('status', ''))) in ('concluido', 'concluida', 'cancelado', 'cancelada'):
                continue
            for delta in (-1, 0, 1):
                try:
                    alvo = _ocorrencia(item, hoje+dt.timedelta(days=delta), fuso)
                except (ValueError, TypeError):
                    continue  # Um registro legado inválido não interrompe os demais.
                if alvo is None:
                    continue
                for antecedencia in (15, 0):
                    quando = alvo-dt.timedelta(minutes=antecedencia)
                    atraso = (instante-quando).total_seconds()
                    if 0 <= atraso <= JANELA_ATRASO_SEG:
                        chave = 'rotina:'+str(item['id'])+':'+alvo.isoformat()+':'+str(antecedencia)
                        prefixo = 'Daqui a 15 minutos' if antecedencia else 'Agora'
                        texto = f"📅 {prefixo}: {str(item.get('atividade', 'Atividade'))[:300]} ({alvo.astimezone(fuso):%H:%M})"
                        if item.get('local'):
                            texto += '\nLocal: '+str(item['local'])[:200]
                        _adicionar_evento(estado, chave, texto, 'rotina', quando.timestamp()+JANELA_ATRASO_SEG)
        proxima = estado.get('proxima_agua_em')
        intervalo = estado.get('agua_intervalo_min')
        if isinstance(intervalo, bool) or not isinstance(intervalo, int) or not 15 <= intervalo <= 720:
            raise ValueError('Intervalo de água armazenado inválido; reconfigure os lembretes.')
        if isinstance(proxima, (int, float)) and not isinstance(proxima, bool) and proxima <= epoch:
            chave = 'agua:'+str(chat_id)+':'+str(int(proxima))
            _adicionar_evento(estado, chave, '💧 Hora de beber água. Registre um copo com /agua.', 'agua', epoch+JANELA_ATRASO_SEG)
            estado['proxima_agua_em'] = epoch+intervalo*60
        retornos = []
        for chave, evento in list(estado['eventos'].items()):
            if not isinstance(evento, dict):
                continue
            if evento.get('vence_em', 0) < epoch-2*86400:
                del estado['eventos'][chave]
                continue
            if evento.get('estado') != 'pendente':
                continue
            if evento.get('vence_em', 0) < epoch:
                evento['estado'] = 'expirado'
                continue
            if evento.get('reserva_ate', 0) > epoch:
                continue
            if evento.get('tentativas', 0) >= MAX_TENTATIVAS:
                evento['estado'] = 'falha'
                continue
            evento['tentativas'] = evento.get('tentativas', 0)+1
            evento['reserva_ate'] = epoch+RESERVA_SEG
            retornos.append({k: evento[k] for k in ('chave', 'texto', 'chat_id', 'user_id')})
        nucleo.gravar_json(ARQUIVO_LEMBRETES, estado)
        return retornos


def confirmar_envio(chave, sucesso):
    if not isinstance(chave, str) or not isinstance(sucesso, bool):
        raise ValueError('Confirmação de lembrete inválida.')
    with nucleo._LOCK:
        estado = _estado()
        evento = estado['eventos'].get(chave)
        if not isinstance(evento, dict) or evento.get('estado') != 'pendente':
            return False
        evento['estado'] = 'enviado' if sucesso else 'falha' if evento.get('tentativas', 0) >= MAX_TENTATIVAS else 'pendente'
        evento['reserva_ate'] = 0 if sucesso else _agora().timestamp()+30
        nucleo.gravar_json(ARQUIVO_LEMBRETES, estado)
    return True


def executar_agendador(stop_event, enviar, autorizar=None):
    if not callable(enviar) or not callable(autorizar):
        raise ValueError('O agendador exige callbacks de envio e autorização do proprietário.')
    while not stop_event.is_set():
        try:
            for evento in processar_lembretes():
                sucesso = False
                try:
                    if autorizar(evento['user_id']):
                        enviar(evento['chat_id'], evento['texto'])
                        sucesso = True
                finally:
                    confirmar_envio(evento['chave'], sucesso)
        except Exception as exc:
            try:
                nucleo.registrar('lembretes', 'falha', str(nucleo.redigir(exc)))
            except (OSError, ValueError):
                pass
        if stop_event.wait(20):
            break
