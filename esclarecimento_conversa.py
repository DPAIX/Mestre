"""Perguntas locais para completar pedidos, sem consultar IA nem executar ações.

Os rascunhos vivem somente em memória por cinco minutos, isolados por usuário,
canal e conversa selecionada. Completar campos produz um plano validado: a
interface ainda precisa pedir a confirmação correspondente antes de agir.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
import math
import re
import threading
import time
import unicodedata

from interpretacao_natural import _normalizar, interpretar_local, validar_plano

PRAZO_SEGUNDOS = 300
MAX_PENDENTES = 500
_DIA = (r'(?:hoje|amanh[aã]|segunda(?:-feira)?|ter[cç]a(?:-feira)?|quarta(?:-feira)?|'
        r'quinta(?:-feira)?|sexta(?:-feira)?|s[aá]bado|domingo|[0-9]{4}-[0-9]{2}-[0-9]{2})')
_HORA = r'(?:[0-9]{1,2}(?::[0-9]{2}|h(?:[0-9]{2})?)?)'
_CANCELAMENTOS = {'cancelar', 'cancele', 'cancelado', 'deixe para la', 'deixa pra la',
                   'esqueca', 'esquece', 'pare', 'nao quero mais', 'nao'}
_CONFIRMACOES = {'sim', 'ok', 'confirmo', 'confirmar', 'pode', 'executar', 'execute',
                 'pode fazer', 'pode executar', 'sim pode executar', 'sim pode fazer'}
_INCERTEZAS = {'nao sei', 'ainda nao sei', 'nao tenho certeza'}


def _hoje_local():
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    try:
        return datetime.now(ZoneInfo('America/Sao_Paulo')).date()
    except ZoneInfoNotFoundError:
        return datetime.now().astimezone().date()


def _entrada(texto):
    if not isinstance(texto, str) or not texto.strip() or len(texto) > 12000:
        return None
    original = unicodedata.normalize('NFC', texto.strip())
    if (original.startswith(('"', "'", '`', '{', '[', '/')) or
            any(c in original for c in ('\n', '\r', ';', '\x00'))):
        return None
    return original.strip(' .!?')


def _pedido(texto):
    normal = ' '.join(_normalizar(texto).split())
    normal = re.sub(r'^por favor[, ]+', '', normal)
    normal = re.sub(r',? por favor$', '', normal)
    normal = re.sub(r'^(?:voce )?(?:pode|consegue) (?:me )?', '', normal)
    if re.search(r'\b(?:nao|nunca|talvez|se|quando|como|explique)\b', normal):
        return None
    if re.search(r'\be\s+(?:abra|registre|execute|adicione|apague|inicie|ative|teste)\b', normal):
        return None
    return normal


def _horario(texto):
    horario = re.fullmatch(r'([0-9]{1,2})(?:(?::|h)([0-9]{2})?)?', texto, re.I)
    if not horario:
        return None
    hora = int(horario[1])
    minuto = int(horario[2] or 0)
    if hora > 23 or minuto > 59:
        return None
    return f'{hora:02}:{minuto:02}'


def _dia(texto, hoje):
    normal = _normalizar(texto).removesuffix('-feira')
    if normal in ('hoje', 'amanha'):
        atual = hoje()
        if type(atual) is not date:
            raise ValueError('A referência local precisa ser uma data.')
        return (atual + timedelta(days=normal == 'amanha')).isoformat()
    nomes = {'segunda': 'Segunda', 'terca': 'Terça', 'quarta': 'Quarta',
             'quinta': 'Quinta', 'sexta': 'Sexta', 'sabado': 'Sábado', 'domingo': 'Domingo'}
    if normal in nomes:
        return nomes[normal]
    try:
        return date.fromisoformat(texto).isoformat()
    except ValueError:
        return None


def _quando(texto, hoje):
    """Aceita somente os campos explícitos, sem supor um horário por período."""
    texto = texto.strip()
    m = re.fullmatch(r'(?:(?:na|no|em|para)\s+)?('+_DIA+r')'
                     r'(?:\s+(?:[aàá]s?\s+)?('+_HORA+r'))?'
                     r'(?:\s+at[eé]\s+('+_HORA+r'))?', texto, re.I)
    if m:
        dia = _dia(m[1], hoje)
        if dia is None:
            return None
        resposta = {'dia': dia}
        if m[2]:
            hora = _horario(m[2])
            if hora is None:
                return None
            resposta['horario'] = hora
        if m[3]:
            fim = _horario(m[3])
            if fim is None:
                return None
            resposta['fim'] = fim
        return resposta
    m = re.fullmatch(r'(?:[aàá]s?\s+)?('+_HORA+r')(?:\s+at[eé]\s+('+_HORA+r'))?', texto, re.I)
    if m:
        hora = _horario(m[1])
        fim = _horario(m[2]) if m[2] else None
        if hora is not None and (not m[2] or fim is not None):
            return {'horario': hora, **({'fim': fim} if fim else {})}
    # "de tarde" não é convertido em uma hora escolhida pelo programa.
    m = re.fullmatch(r'(?:(?:na|no|em|para)\s+)?('+_DIA+r')\s+(?:de|pela|a)\s+(?:manh[aã]|tarde|noite)', texto, re.I)
    if m:
        dia = _dia(m[1], hoje)
        return {'dia': dia} if dia else None
    return None


def _atividade_quando(texto, hoje):
    quando = _quando(texto, hoje)
    if quando is not None:
        return quando
    for m in re.finditer(r'\s+(?:(?:na|no|em|para)\s+)?'+_DIA+r'\b', texto, re.I):
        campos = _quando(texto[m.start():].strip(), hoje)
        if campos is not None:
            return {'atividade': texto[:m.start()].strip(), **campos}
    return {'atividade': texto.strip()} if texto.strip() else {}


def _resposta(estado='nao_tratado', texto='', plano=None):
    return {'estado': estado, 'texto': texto, 'plano': plano}


class GerenciadorEsclarecimentos:
    def __init__(self, *, relogio=time.monotonic, hoje=_hoje_local):
        self._relogio = relogio
        self._hoje = hoje
        self._pendentes = {}
        self._lock = threading.RLock()

    @staticmethod
    def _chave(contexto, usuario, chat_id):
        for valor in (contexto, chat_id):
            if not isinstance(valor, str) or not valor or len(valor) > 500 or any(ord(c) < 32 for c in valor):
                raise ValueError('O esclarecimento exige um contexto e uma conversa válidos.')
        if type(usuario) is int:
            if usuario < 0:
                raise ValueError('Identidade inválida para esclarecimento.')
            usuario = str(usuario)
        if not isinstance(usuario, str) or not usuario or len(usuario) > 100 or any(ord(c) < 32 for c in usuario):
            raise ValueError('Identidade inválida para esclarecimento.')
        return contexto, usuario

    @staticmethod
    def _pergunta(pedido, erro=False):
        campos = pedido['campos']
        acao = pedido['acao']
        if acao == 'kanban_adicionar':
            return 'Qual é o título da tarefa que você quer adicionar ao Kanban?'
        if acao == 'modelo_conversa':
            return 'Qual modelo Ollama você quer usar nesta conversa? Diga o nome da tag; também pode pedir para mostrar os modelos disponíveis.'
        if acao == 'pc':
            return 'Qual programa você quer abrir? Posso preparar, por exemplo, Calculadora, Bloco de Notas, Explorador de Arquivos ou VS Code.'
        if acao == 'financeiro':
            return ('Qual é o valor em reais? Informe somente o valor, por exemplo 15,50.' if not campos.get('valor') else
                    'Qual é a descrição desse lançamento financeiro?')
        if not campos.get('atividade'):
            return 'Qual atividade você quer adicionar à rotina local? Isso não ativa um novo alarme ou aviso.'
        if not campos.get('dia'):
            return 'Para adicionar essa atividade à rotina local, em qual dia? Pode dizer, por exemplo, amanhã às 14h. Isso não ativa um novo alarme ou aviso.'
        if not campos.get('horario'):
            return 'Qual é o horário exato para a atividade na rotina local? Pode dizer, por exemplo, às 14h ou 14:30.'
        return 'Qual deve ser o horário final? Ele precisa ser posterior ao início no mesmo dia; diga sem horário final para omitir.'

    def _iniciar(self, texto):
        normal = _pedido(texto)
        if normal is None:
            return None
        acao = campos = None
        if re.fullmatch(r'(?:adicione|adicionar|crie|criar|inclua|incluir) (?:uma )?tarefa', normal):
            acao, campos = 'kanban_adicionar', {'coluna': 'A_Fazer'}
        elif re.fullmatch(r'(?:mude|mudar|troque|trocar|selecione|selecionar|escolha|escolher) (?:o )?modelo(?: (?:desta|nesta) conversa)?', normal):
            acao, campos = 'modelo_conversa', {}
        elif re.fullmatch(r'(?:abra|abrir|inicie|iniciar)(?: (?:um|o|a) programa)?', normal):
            acao, campos = 'pc', {}
        elif re.fullmatch(r'(?:registre|registrar|adicione|adicionar) (?:um|uma) (gasto|despesa|entrada)', normal):
            acao = 'financeiro'
            campos = {'tipo': 'entrada' if normal.endswith('entrada') else 'saida'}
        else:
            texto = re.sub(r'^por favor[, ]+', '', texto, flags=re.I)
            texto = re.sub(r',? por favor$', '', texto, flags=re.I)
            texto = re.sub(r'^(?:voc[eê] )?(?:pode|consegue) (?:me )?', '', texto, flags=re.I)
            m = re.fullmatch(r'(?:agende|agendar|marque|marcar|(?:me )?lembre(?:-me)?(?: de)?|adicione (?:a|na) rotina|coloque na rotina)(?:\s+(.+))?', texto, re.I)
            if m:
                acao, campos = 'rotina_criar', _atividade_quando(m[1] or '', self._hoje)
                if len(campos.get('atividade', '')) > 200:
                    return None
        if acao is None:
            return None
        return {'acao': acao, 'campos': campos}

    @staticmethod
    def _novo_pedido(texto):
        if interpretar_local(texto) is not None:
            return True
        normal = _normalizar(texto)
        return bool(re.match(r'^(?:mostre|liste|abra|agende|adicione|crie|registre|troque|mude|ative|desative|teste|use|remova|apague|reinicie|desligue|explique|como|qual|quais)\b', normal))

    def _completar(self, pedido, texto):
        campos, acao = pedido['campos'], pedido['acao']
        if acao == 'kanban_adicionar':
            if len(texto) > 200:
                return False
            campos['texto'] = texto
        elif acao == 'modelo_conversa':
            try:
                validado = validar_plano({'acao': acao, 'campos': {'modelo': texto}})
            except ValueError:
                return False
            campos.update(validado['campos'])
        elif acao == 'pc':
            plano = interpretar_local('abra '+texto)
            if plano is None or plano['acao'] != 'pc':
                return False
            campos['comando'] = plano['campos']['comando']
        elif acao == 'financeiro':
            if not campos.get('valor'):
                m = re.fullmatch(r'(?:R\$\s*)?([0-9.,]+)(?:\s*reais?)?', texto, re.I)
                if not m:
                    return False
                try:
                    provisoria = validar_plano({'acao': acao, 'campos': {**campos, 'valor': m[1], 'descricao': 'valor em conferência'}})
                except ValueError:
                    return False
                campos['valor'] = provisoria['campos']['valor']
            else:
                if len(texto) > 150:
                    return False
                campos['descricao'] = texto
        elif not campos.get('atividade'):
            novos = _atividade_quando(texto, self._hoje)
            if len(novos.get('atividade', '')) > 200:
                return False
            campos.update(novos)
        else:
            novos = _quando(texto, self._hoje)
            if novos is None:
                if _normalizar(texto) == 'sem horario final':
                    campos.pop('fim', None)
                else:
                    return False
            else:
                campos.update(novos)
        return True

    @staticmethod
    def _plano(pedido):
        acao, campos = pedido['acao'], pedido['campos']
        obrigatorios = {'kanban_adicionar': ('texto',), 'modelo_conversa': ('modelo',),
            'pc': ('comando',), 'financeiro': ('valor', 'descricao'),
            'rotina_criar': ('atividade', 'dia', 'horario')}[acao]
        if not all(campos.get(campo) for campo in obrigatorios):
            return None
        try:
            return validar_plano({'acao': acao, 'campos': campos})
        except ValueError:
            return None

    def processar(self, texto, *, contexto, usuario, chat_id):
        chave = self._chave(contexto, usuario, chat_id)
        with self._lock:
            agora = self._relogio()
            if not isinstance(agora, (int, float)) or isinstance(agora, bool) or not math.isfinite(agora):
                raise ValueError('Relógio de esclarecimento inválido.')
            for antiga in tuple(self._pendentes):
                if self._pendentes[antiga]['expira'] <= agora:
                    self._pendentes.pop(antiga, None)
            anterior = self._pendentes.get(chave)
            if anterior and anterior['chat_id'] != chat_id:
                self._pendentes.pop(chave, None)
                anterior = None
            original = _entrada(texto)
            if original is None:
                self._pendentes.pop(chave, None)
                return _resposta()
            normal = _normalizar(original)
            if normal in _CANCELAMENTOS:
                if anterior:
                    self._pendentes.pop(chave, None)
                    return _resposta('cancelado', 'Pedido incompleto cancelado. Nenhuma ação foi executada.')
                return _resposta()
            if anterior and normal in _INCERTEZAS:
                return _resposta('pergunta', self._pergunta(anterior))
            confirmacao = ' '.join(re.sub(r'[,;:]', ' ', normal).split())
            if anterior and confirmacao in _CONFIRMACOES:
                return _resposta('pergunta', self._pergunta(anterior))
            if anterior and re.match(r'^(?:nao|nunca|talvez|se|quando|como|qual|quais|por que|o que)\b', normal):
                # Uma negação, condição ou pergunta não é um título/nome
                # fornecido para completar a ação anterior.
                self._pendentes.pop(chave, None)
                return _resposta()
            novo = self._iniciar(original)
            if novo is not None:
                pedido = {**novo, 'chat_id': chat_id, 'expira': agora+PRAZO_SEGUNDOS}
            elif anterior and not self._novo_pedido(original):
                pedido = anterior
                if not self._completar(pedido, original):
                    return _resposta('pergunta', self._pergunta(pedido, erro=True))
            else:
                self._pendentes.pop(chave, None)
                return _resposta()
            plano = self._plano(pedido)
            if plano is not None:
                self._pendentes.pop(chave, None)
                return _resposta('plano', 'O pedido está completo e ainda precisa da confirmação aplicável.', plano)
            if chave not in self._pendentes and len(self._pendentes) >= MAX_PENDENTES:
                self._pendentes.pop(next(iter(self._pendentes)))
            self._pendentes[chave] = pedido
            return _resposta('pergunta', self._pergunta(pedido))
