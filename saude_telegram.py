"""Evidências em memória das consultas de recebimento já feitas pelo bot.

Não consulta a rede, não guarda mensagens, credenciais ou o texto de exceções.
O prazo de 90 segundos admite os 15 segundos do long polling e atrasos de
agendamento/rede. Ele só envelhece a evidência: não é um teste de disponibilidade
nem dispara novas tentativas. As repetições pertencem ao cliente Telegram.
"""
from __future__ import annotations

import math
import threading
import time


CONFIRMACAO_RECENTE_S = 90
_LIMITE_CONTADOR = 1_000_000
_LIMITE_IDADE = 2_147_483_647

_DETALHES = {
    'nao_iniciado': 'Recebimento do Telegram ainda não iniciado nesta sessão.',
    'somente_painel': 'Modo somente painel; recebimento do Telegram desativado nesta sessão.',
    'iniciando': 'Aguardando a primeira confirmação do recebimento do Telegram.',
    'consultando': 'API do Telegram respondeu à consulta de recebimento; entrega de respostas não verificada.',
    'sem_confirmacao_recente': 'Sem confirmação recente do recebimento do Telegram; entrega de respostas não verificada.',
    'encerrado': 'Recebimento do Telegram encerrado nesta sessão.',
}
_FALHAS = {
    'autenticacao': 'A API recusou a autenticação do bot; recebimento não confirmado.',
    'conflito': 'A API informou conflito no recebimento; verifique outro processo do bot ou webhook.',
    'limite': 'A API limitou as consultas de recebimento; aguardando nova tentativa do cliente.',
    'servidor': 'A API informou falha no serviço; aguardando nova tentativa do cliente.',
    'requisicao': 'A API recusou a consulta de recebimento; conexão ainda não confirmada.',
    'resposta_invalida': 'A consulta retornou uma resposta inválida; recebimento não confirmado.',
    'tempo_esgotado': 'A consulta de recebimento excedeu o prazo; aguardando nova tentativa do cliente.',
    'conexao': 'Falha de conexão na consulta de recebimento; aguardando nova tentativa do cliente.',
    'interna': 'Falha na consulta de recebimento; consulte o diagnóstico local.',
}


def _codigo_http(erro):
    # Nunca converter atributos, exceções, descrições ou corpos de resposta em
    # texto: as URLs da API podem conter o token do bot.
    try:
        codigo = getattr(erro, 'error_code', None)
        if type(codigo) is int and 100 <= codigo <= 599:
            return codigo
        for nome in ('result', 'response'):
            codigo = getattr(getattr(erro, nome, None), 'status_code', None)
            if type(codigo) is int and 100 <= codigo <= 599:
                return codigo
    except Exception:
        pass
    return None


def _classificar(erro):
    codigo = _codigo_http(erro)
    if codigo in (401, 403):
        return 'autenticacao', codigo
    if codigo == 409:
        return 'conflito', codigo
    if codigo == 429:
        return 'limite', codigo
    if codigo is not None:
        if codigo >= 500:
            return 'servidor', codigo
        return ('requisicao' if codigo >= 400 else 'resposta_invalida'), codigo
    if isinstance(erro, TimeoutError):
        return 'tempo_esgotado', None
    if isinstance(erro, ConnectionError):
        return 'conexao', None
    # requests é opcional na importação do painel. Só os tipos, quando
    # disponíveis, são consultados; nenhum método HTTP é chamado aqui.
    try:
        from requests.exceptions import ConnectionError as FalhaConexao, Timeout
    except ImportError:
        return 'interna', None
    if isinstance(erro, Timeout):
        return 'tempo_esgotado', None
    if isinstance(erro, FalhaConexao):
        return 'conexao', None
    return 'interna', None


class _ConsultaObservada:
    def __init__(self, original, monitor):
        self.original = original
        self.monitor = monitor

    def __call__(self, *args, **kwargs):
        geracao = self.monitor._geracao_consulta()
        try:
            resultado = self.original(*args, **kwargs)
        except Exception as erro:
            self.monitor._falhou(geracao, erro)
            raise
        self.monitor._respondeu(geracao)
        return resultado


class MonitorTelegram:
    """Snapshot local e thread-safe; observar() não inicia um polling."""

    def __init__(self, relogio=time.monotonic):
        self._relogio = relogio
        self._lock = threading.RLock()
        self._geracao = 0
        self._estado = 'nao_iniciado'
        self._ultima_consulta = None
        self._ultima_falha = None
        self._categoria = None
        self._codigo = None
        self._falhas = 0

    def _trocar_sessao(self, estado):
        with self._lock:
            self._geracao += 1
            self._estado = estado
            self._ultima_consulta = None
            self._ultima_falha = None
            self._categoria = None
            self._codigo = None
            self._falhas = 0

    def iniciar(self):
        self._trocar_sessao('iniciando')

    def somente_painel(self):
        self._trocar_sessao('somente_painel')

    def encerrar(self):
        with self._lock:
            self._geracao += 1
            self._estado = 'encerrado'

    def observar(self, bot):
        """Observa exatamente a chamada existente, preservando sua semântica."""
        with self._lock:
            original = bot.get_updates
            if isinstance(original, _ConsultaObservada):
                if original.monitor is self:
                    return
                original = original.original
            bot.get_updates = _ConsultaObservada(original, self)

    def _geracao_consulta(self):
        with self._lock:
            if self._estado in ('nao_iniciado', 'somente_painel', 'encerrado'):
                return None
            return self._geracao

    def _respondeu(self, geracao):
        with self._lock:
            if geracao is None or geracao != self._geracao:
                return
            self._ultima_consulta = self._relogio()
            self._estado = 'consultando'
            self._falhas = 0
            self._categoria = None
            self._codigo = None

    def _falhou(self, geracao, erro):
        with self._lock:
            if geracao is None or geracao != self._geracao:
                return
            self._ultima_falha = self._relogio()
            self._categoria, self._codigo = _classificar(erro)
            self._estado = 'falha'
            self._falhas = min(_LIMITE_CONTADOR, self._falhas + 1)

    def snapshot(self):
        with self._lock:
            agora = self._relogio()
            def idade(instante):
                if instante is None:
                    return None
                delta = agora - instante
                if not math.isfinite(delta):
                    return None
                return min(_LIMITE_IDADE, max(0, int(delta)))
            consulta = idade(self._ultima_consulta)
            estado = self._estado
            if estado == 'consultando' and (consulta is None or agora - self._ultima_consulta > CONFIRMACAO_RECENTE_S):
                estado = 'sem_confirmacao_recente'
            detalhe = _FALHAS[self._categoria] if estado == 'falha' else _DETALHES[estado]
            return {
                'estado': estado,
                'detalhe': detalhe,
                'ultima_consulta_ha_s': consulta,
                'ultima_falha_ha_s': idade(self._ultima_falha),
                'categoria': self._categoria,
                'codigo_http': self._codigo,
                'falhas_consecutivas': self._falhas,
            }
