"""Testes explícitos e sequenciais dos modelos registrados, sem histórico.

Uma consulta por tag, sem síntese, fallback, download ou repetição. Compartilha
a trava da equipe. Timeout e conclusão incerta interrompem os novos envios.
"""
from __future__ import annotations

import math
import time

from configurar_ia_local import validar_modelo
import conversa_equipe
from interpretacao_natural import extrair_resposta
from nucleo import redigir


def _limites(roteador, total):
    obter = getattr(type(roteador), 'limites_equipe', None)
    limites = obter(roteador, total) if callable(obter) else {
        'por_modelo': 90.0, 'rodada': min(900.0, total * 90.0), 'origem': 'adaptativo',
    }
    if not isinstance(limites, dict):
        raise ValueError('Orçamento dos testes inválido.')
    for nome, minimo, maximo in (('por_modelo', 5, 120), ('rodada', 5, 900)):
        valor = limites.get(nome)
        if (isinstance(valor, bool) or not isinstance(valor, (int, float))
                or not math.isfinite(valor) or not minimo <= valor <= maximo):
            raise ValueError('Orçamento dos testes inválido.')
    return limites


def testar_catalogo(roteador, *, progresso=None):
    if progresso is not None and not callable(progresso):
        raise ValueError('Progresso deve ser uma função.')
    if not conversa_equipe._TRAVA.acquire(blocking=False):
        raise RuntimeError('Uma equipe ou teste de modelos já está trabalhando. Aguarde a conclusão.')
    try:
        catalogo = roteador.catalogo_ollama()
        if not isinstance(catalogo, dict) or catalogo.get('habilitado') is not True:
            raise ValueError('O serviço Ollama precisa estar habilitado para testar seus modelos.')
        registros = catalogo.get('modelos')
        if not isinstance(registros, list) or not 1 <= len(registros) <= 32:
            raise ValueError('O teste aceita de um a 32 modelos registrados; nenhum modelo foi consultado.')
        try:
            modelos = list(dict.fromkeys(validar_modelo(item['nome']) for item in registros))
        except (KeyError, TypeError, ValueError):
            raise ValueError('O catálogo contém um modelo inválido; nenhuma geração foi enviada.') from None
        from alternativa_27b import selecionar
        modelos,aviso_alternativa=selecionar(modelos,registros)
        limites = _limites(roteador, len(modelos))
        ordem = list(modelos)
        ordenar = getattr(type(roteador), 'ordenar_equipe_cpu', None)
        if callable(ordenar):
            ordem = ordenar(roteador, list(modelos))
            if not isinstance(ordem, list) or len(ordem) != len(modelos) or set(ordem) != set(modelos):
                raise ValueError('A ordem dos testes precisa preservar todos os modelos.')
        prazo = time.monotonic() + limites['rodada']
        interrupcao = ''
        resultados = []
        for indice, modelo in enumerate(ordem):
            restante = prazo - time.monotonic()
            if not interrupcao and restante <= 0:
                interrupcao = 'O orçamento total dos testes terminou.'
            if interrupcao:
                resultados.append({'modelo': modelo, 'ok': False, 'enviado': False,
                    'categoria': 'adiado', 'detalhe': interrupcao + ' Nenhuma geração enviada.'})
                continue
            if progresso:
                try:
                    progresso({'modelo': modelo, 'indice': indice + 1, 'total': len(modelos)})
                except Exception:
                    pass
            restante = prazo - time.monotonic()
            if restante <= 0:
                interrupcao = 'O orçamento total dos testes terminou.'
                resultados.append({'modelo': modelo, 'ok': False, 'enviado': False,
                    'categoria': 'adiado', 'detalhe': interrupcao + ' Nenhuma geração enviada.'})
                continue
            inicio = time.monotonic()
            try:
                responder = getattr(type(roteador), 'responder_equipe', None)
                if callable(responder):
                    texto, provedor = responder(roteador, 'Responda somente OK.', historico=[],
                        modelo_ollama=modelo, limite_segundos=min(restante, limites['por_modelo']))
                else:
                    texto, provedor = roteador.responder('Responda somente OK.',
                        provedor='Ollama', modelo_ollama=modelo, historico=[])
                if provedor != 'Ollama' or not isinstance(texto, str) or not texto.strip():
                    raise ValueError('O modelo não devolveu uma resposta textual válida.')
                texto=extrair_resposta(texto,estrito=True)['texto']
                item = {'modelo': modelo, 'ok': True, 'enviado': True, 'categoria': None,
                    'detalhe': str(redigir(texto.strip()))[:140]}
            except Exception as erro:
                categoria = getattr(erro, 'categoria', None)
                if not isinstance(categoria, str):
                    categoria = 'tempo_esgotado' if isinstance(erro, TimeoutError) else 'falha'
                item = {'modelo': modelo, 'ok': False,
                    'enviado': categoria not in ('recursos', 'configuracao', 'adiado'),
                    'categoria': categoria, 'detalhe': str(redigir(str(erro)))[:500]}
                if conversa_equipe._expirou(erro) or categoria == 'geracao_incompleta':
                    interrupcao = ('Uma geração excedeu o prazo ou não confirmou conclusão; '
                        'ela pode continuar no serviço. Os próximos testes foram adiados.')
            item['duracao_s'] = round(max(0, time.monotonic() - inicio), 1)
            resultados.append(item)
        resultados.sort(key=lambda item: modelos.index(item['modelo']))
        return {'resultados': resultados, 'total': len(modelos),
            'responderam': sum(item['ok'] for item in resultados),
            'aviso_alternativa': aviso_alternativa,
            'limites': dict(limites), 'historico_enviado': False}
    finally:
        conversa_equipe._TRAVA.release()


def texto_resultado(resultado):
    linhas = [f"Modelos Ollama: {resultado['responderam']}/{resultado['total']} responderam ao teste."]
    if resultado.get('aviso_alternativa'):linhas.append(resultado['aviso_alternativa'])
    for item in resultado['resultados']:
        estado = 'respondeu' if item['ok'] else item['categoria']
        duracao=item.get('duracao_s')
        tempo=f' ({duracao:g} s)' if type(duracao) in (int,float) and math.isfinite(duracao) and duracao>=0 else ''
        linhas.append(('✅ ' if item['ok'] else '⚠️ ') + item['modelo'] + ' — ' + estado + ': '
            + item['detalhe'][:120]+tempo)
    linhas.append('Uma consulta por modelo, sem histórico ou síntese. Os resultados valem para estes testes.')
    return str(redigir('\n'.join(linhas)))[:12000]
