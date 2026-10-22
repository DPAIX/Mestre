"""Resultados de ações HTTP retidos apenas na memória desta sessão do painel.

Chaves são únicas enquanto retidas (TTL/capacidade). Reiniciar o processo ou
expirar um resultado encerra essa garantia; clientes consultam o estado antes
de criar outra intenção. Uma ação em andamento nunca é removida por expiração.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import threading
import time


class FalhaControle(RuntimeError):
    def __init__(self, codigo, mensagem, versao):
        super().__init__(mensagem)
        self.codigo = codigo
        self.resposta = {'erro': mensagem, 'versao_estado': versao}


class ControleAcoes:
    def __init__(self, *, ttl=900, capacidade=256, max_bytes=64_000_000,
                 max_resposta=12_000_000, capacidade_prioritaria=8, relogio=None):
        if ttl <= 0 or capacidade < 1 or max_bytes < max_resposta or max_resposta < 1024:
            raise ValueError('Limites de retenção inválidos.')
        self.ttl = ttl
        self.capacidade = capacidade
        self.max_bytes = max_bytes
        self.max_resposta = max_resposta
        self.capacidade_prioritaria = capacidade_prioritaria
        self._agora = relogio or time.monotonic
        self._trava = threading.RLock()
        self._itens = {}
        self._versao = 0
        self._bytes = 0
        self._legados = 0

    @staticmethod
    def validar_chave(chave):
        if not isinstance(chave, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{7,127}', chave):
            raise ValueError('X-Idempotency-Key deve ter entre 8 e 128 caracteres seguros.')
        return chave

    @staticmethod
    def validar_versao(valor):
        if not isinstance(valor, str) or not 1 <= len(valor) <= 19 or not valor.isascii() or not valor.isdecimal():
            raise ValueError('X-Estado-Versao deve conter a versão inteira recebida do painel.')
        return int(valor)

    def _expirar(self):
        agora = self._agora()
        for chave, item in list(self._itens.items()):
            if item['estado'] == 'concluido' and agora - item['concluido_em'] >= self.ttl:
                self._bytes -= item['bytes']
                del self._itens[chave]

    def versao(self):
        with self._trava:
            return self._versao

    def _ocupado(self):
        return self._legados > 0 or any(i['estado'] == 'em_andamento' and not i['prioridade']
                                        for i in self._itens.values())

    def _resultado(self, chave, item):
        return {'id': chave, 'estado': item['estado'], 'codigo_http': item.get('codigo_http'),
                'resposta': copy.deepcopy(item.get('resposta')), 'versao_estado': self._versao}

    def reservar(self, chave, payload, versao, *, prioridade=False):
        self.validar_chave(chave)
        resumo = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                           separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
        with self._trava:
            self._expirar()
            anterior = self._itens.get(chave)
            if anterior is not None:
                if anterior['resumo'] != resumo:
                    raise FalhaControle(409, 'Esta chave já foi usada para outro pedido. Nenhuma nova ação foi executada.', self._versao)
                if anterior['estado'] == 'concluido':
                    return {'executar': False, 'codigo_http': anterior['codigo_http'],
                            'resposta': copy.deepcopy(anterior['resposta'])}
                return {'executar': False, 'codigo_http': 202,
                        'resposta': self._resultado(chave, anterior)}
            if not prioridade and versao != self._versao:
                raise FalhaControle(409, 'O estado do painel mudou. Atualize e confira o resultado antes de fazer outro pedido; a ação não foi repetida.', self._versao)
            if not prioridade and self._ocupado():
                raise FalhaControle(409, 'Outra ação do painel está em andamento. Aguarde e atualize o estado antes de criar outro pedido.', self._versao)
            quantidade = sum(i['prioridade'] == prioridade for i in self._itens.values())
            capacidade = self.capacidade_prioritaria if prioridade else self.capacidade
            orcamento = min(16384, self.max_resposta) if prioridade else self.max_resposta
            reservados = sum(i['orcamento'] for i in self._itens.values() if i['estado'] == 'em_andamento')
            # Há uma reserva pequena separada para cancelamento do Windows.
            margem = self.capacidade_prioritaria * min(16384, self.max_resposta) if prioridade else 0
            if quantidade >= capacidade or self._bytes + reservados + orcamento > self.max_bytes + margem:
                raise FalhaControle(503, 'A retenção de resultados está cheia. Nenhuma ação foi iniciada; aguarde a expiração dos resultados anteriores.', self._versao)
            self._versao += 1
            self._itens[chave] = {'estado': 'em_andamento', 'resumo': resumo,
                                  'prioridade': prioridade, 'orcamento': orcamento}
            return {'executar': True}

    def finalizar(self, chave, codigo, resposta):
        with self._trava:
            item = self._itens[chave]
            if item['estado'] == 'concluido':
                return item['codigo_http'], copy.deepcopy(item['resposta'])
            self._versao += 1
            resposta = copy.deepcopy(resposta)
            resposta['versao_estado'] = self._versao
            tamanho = len(json.dumps(resposta, ensure_ascii=False, allow_nan=False).encode('utf-8'))
            if tamanho > item['orcamento']:
                codigo = 500
                resposta = {'erro': 'A ação terminou, mas o resultado excedeu o limite de retenção. Confira o estado antes de criar outro pedido.',
                            'resultado_incompleto': True, 'versao_estado': self._versao}
                tamanho = len(json.dumps(resposta).encode('utf-8'))
            item.update({'estado': 'concluido', 'codigo_http': codigo, 'resposta': resposta,
                         'bytes': tamanho, 'concluido_em': self._agora()})
            self._bytes += tamanho
            return codigo, copy.deepcopy(resposta)

    def consultar(self, chave):
        self.validar_chave(chave)
        with self._trava:
            self._expirar()
            item = self._itens.get(chave)
            if item is None:
                raise FalhaControle(404, 'Resultado desconhecido ou expirado nesta sessão. Confira o estado; não reenvie automaticamente a ação.', self._versao)
            return self._resultado(chave, item)

    def iniciar_legado(self):
        """Clientes antigos continuam aceitos; invalidam snapshots dos novos."""
        with self._trava:
            self._legados += 1
            self._versao += 1

    def finalizar_legado(self):
        with self._trava:
            self._legados = max(0, self._legados - 1)
            self._versao += 1
            return self._versao
