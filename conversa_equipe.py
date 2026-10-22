"""Uma chamada concorrente por modelo; respostas não executam ferramentas."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import threading

from configurar_ia_local import validar_modelo
from interpretacao_natural import extrair_resposta
from nucleo import redigir

_TRAVA = threading.Lock()
MAX_MODELOS = 8


def consultar_modelos(texto, historico, modelos, roteador, *, interpretar=False):
    if not isinstance(texto, str) or not texto.strip() or len(texto)>12000:
        raise ValueError('Envie uma mensagem de até 12000 caracteres para a equipe.')
    if not isinstance(modelos, list) or not 1<=len(modelos)<=MAX_MODELOS:
        raise ValueError('A equipe aceita entre um e oito modelos.')
    modelos=list(dict.fromkeys(validar_modelo(m) for m in modelos))
    if not isinstance(historico, list):raise ValueError('Histórico de equipe inválido.')
    mensagem=str(redigir(texto))
    historico=redigir(historico)
    if not _TRAVA.acquire(blocking=False):
        raise RuntimeError('Uma equipe de modelos já está respondendo. Aguarde a conclusão.')
    try:
        def consultar(modelo):
            base={'modelo':modelo,'ok':False,'texto':'','plano':None}
            try:
                # Cada modelo recebe uma cópia: nenhum participante modifica
                # o contexto do outro. O roteador mantém seus limites HTTP.
                copia=json.loads(json.dumps(historico,allow_nan=False))
                resposta,provedor=roteador.responder(mensagem,historico=copia,
                    provedor='Ollama',modelo_ollama=modelo)
                if provedor!='Ollama' or not isinstance(resposta,str) or not resposta.strip():
                    raise RuntimeError('O modelo não devolveu uma resposta textual válida.')
                resposta=str(redigir(resposta))
                resultado=extrair_resposta(resposta) if interpretar else {'texto':resposta,'plano':None}
                return {**base,'ok':True,'texto':resultado['texto'][:8000], 'plano':resultado['plano']}
            except Exception as erro:
                return {**base,'erro':str(redigir(erro))[:600]}
        respostas={}
        with ThreadPoolExecutor(max_workers=len(modelos),thread_name_prefix='equipe_ollama') as executor:
            futuros={executor.submit(consultar,m):m for m in modelos}
            for futuro in as_completed(futuros):respostas[futuros[futuro]]=futuro.result()
        itens=[respostas[m] for m in modelos]
        sucessos=[r for r in itens if r['ok']]
        if not sucessos:
            raise RuntimeError('Nenhum modelo da equipe respondeu. '+
                '\n'.join(r['modelo']+': '+r['erro'] for r in itens))
        plano=None
        if interpretar and len(sucessos)==len(itens) and all(r['plano'] for r in itens):
            assinaturas={json.dumps({'acao':r['plano']['acao'],'campos':r['plano']['campos']},
                sort_keys=True,allow_nan=False) for r in itens}
            if len(assinaturas)==1:plano=itens[0]['plano']
        linhas=[f'👥 Equipe Ollama: {len(sucessos)}/{len(itens)} modelos responderam.']
        limite=max(350,min(1800,9500//len(itens)))
        for item in itens:
            linhas.append('\n'+('✅ ' if item['ok'] else '⚠️ ')+item['modelo'])
            linhas.append((item['texto'] if item['ok'] else item['erro'])[:limite])
            if item.get('plano'):linhas.append('Proposta: '+item['plano']['descricao'])
        if plano:linhas.append('\nOs modelos concordaram neste pedido: '+plano['descricao']+'. Ainda não foi executado.')
        elif interpretar and any(r.get('plano') for r in itens):
            linhas.append('\nAs propostas não tiveram concordância de todos os participantes. Nenhuma ação foi preparada; esclareça o pedido.')
        return {'texto':'\n'.join(linhas)[:12000],'plano':plano,'resultados':itens}
    finally:_TRAVA.release()
