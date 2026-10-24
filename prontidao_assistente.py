"""Estado por recurso; instalação, configuração e resposta são evidências distintas.

A leitura padrão é local. A sondagem explícita faz até três requisições a APIs
de loopback com timeouts curtos; o catálogo 9Router pode consultar provedores.
Não gera respostas, abre aplicativos nem testa permissões de controle remoto.
"""
from __future__ import annotations
import importlib.util
import os
import shutil
import sys


def _dependencia(nome):
    try: return importlib.util.find_spec(nome) is not None
    except (ImportError, ModuleNotFoundError, ValueError): return False


def coletar_prontidao(*, sondar=False):
    if type(sondar) is not bool: raise ValueError('A opção de sondagem deve ser booleana.')
    itens = []
    def item(ident, nome, estado, detalhe, proximo=''):
        itens.append({'id': ident, 'nome': nome, 'estado': estado, 'detalhe': detalhe, 'proximo_passo': proximo})
    item('python', 'Python', 'pronto' if sys.version_info >= (3,11) else 'pendente', 'Versão do processo atual: '+'.'.join(map(str,sys.version_info[:3])))
    telegram = _dependencia('telebot')
    chave = bool(os.getenv('TELEGRAM_TOKEN'))
    donos = bool(os.getenv('TELEGRAM_ALLOWED_USER_IDS','').strip())
    item('telegram', 'Telegram', 'presente' if telegram and chave and donos else 'pendente',
         'Biblioteca, token e proprietários definidos; conexão não testada.' if telegram and chave and donos else 'Faltam biblioteca, token ou proprietários.', 'Use configurar_telegram.bat e o painel local.')
    voz = False
    try:
        from transcritor_local import verificar_disponibilidade
        verificar_disponibilidade(); voz = True
    except (ValueError, RuntimeError, OSError, ImportError): pass
    item('voz', 'Transcrição local', 'presente' if voz else 'pendente',
         'Motor e pesos encontrados; transcrição não testada.' if voz else 'Motor ou pesos ainda não preparados.', 'Prepare as dependências e a voz pelo configurador com o bot encerrado.')
    from integracoes_agentes import catalogo_agentes
    item('agentes', 'Aplicativos de agentes', 'presente', str(len(catalogo_agentes()))+' integrações de abertura/configuração pelo lançador oficial; instalação e login individuais não verificados.', 'Escolha e configure cada agente desejado no configurador.')
    node = bool(shutil.which('node.exe') or shutil.which('node'))
    item('node', 'Node.js / npm', 'presente' if node else 'pendente', 'Comando localizado; versão será validada na instalação.' if node else 'Node.js 22+ com npm não localizado.', 'Instale Node.js 22+ pelo site oficial https://nodejs.org/en/download .')
    from integracoes_9stack import catalogo_9stack
    for servico in catalogo_9stack():
        item(servico['servico'], servico['nome'], 'presente' if servico['instalado_gerenciado'] else 'pendente',
             'Pacote gerenciado encontrado; '+('conta, pareamento e sessão remota não verificados.' if servico['servico']=='9remote' else 'provedores e geração não verificados.'), 'Abra a interface oficial para conferir contas e permissões.')
    from roteador_9router import diagnostico_local
    meta = diagnostico_local()
    item('gateway', 'Cliente 9Router', 'presente' if meta.get('configurado') else 'pendente', 'Configuração pública válida em memória.' if meta.get('configurado') else 'Habilitação, endereço ou modelo/combo pendentes.', 'Configure as contas no dashboard e o cliente no console local.')
    item('ollama', 'Ollama', 'nao_verificado', 'Serviço e geração ainda não consultados.', 'Use a sondagem explícita para consultar versão e catálogo.')
    import gemini_interactions
    gemini = gemini_interactions.diagnostico_local()
    item('gemini', 'Gemini Interactions / agentes', 'presente' if gemini['sdk_presente'] and gemini['chave_definida'] else 'pendente',
         'SDK/chave definidos; acesso à API, agentes e cota não testados.' if gemini['sdk_presente'] and gemini['chave_definida'] else 'SDK google-genai>=2.9 e chave da API necessários.', 'Configure a chave no console. Colab Pro e cota Gemini API são serviços separados.')
    from startup_windows import inspecionar_inicio
    inicio = inspecionar_inicio()
    item('inicio', 'Início após logon', 'presente' if inicio['estado']=='presente' else 'pendente',
         'Entrada gerenciada presente; habilitação no Gerenciador de Tarefas não verificada.' if inicio['estado']=='presente' else ('Entradas antigas detectadas: '+', '.join(inicio['conflitos']) if inicio['conflitos'] else 'Início gerenciado não localizado ou indisponível neste ambiente.'), 'O configurador oferece ativação/consolidação explícita apenas do assistente.')
    for ident, nome in (('rotina','Rotina e lembretes'),('financeiro','Finanças'),('kanban','Kanban'),('robotask','Windows e RoboTask'),('memoria','Memória por conversa')):
        item(ident, nome, 'presente', 'Recurso integrado; esta leitura não acessa seus registros nem executa ações.', 'Use o menu ou uma frase para consultar; alterações passam por confirmação.')
    if sondar:
        from diagnostico_ollama import consultar, validar_url, URL_PADRAO
        alvo = next(i for i in itens if i['id']=='ollama')
        try:
            url = validar_url(os.getenv('OLLAMA_URL',URL_PADRAO))
            versao = consultar(url,'/api/version',timeout=3)
            if versao.get('ok') and isinstance(versao.get('dados'),dict) and isinstance(versao['dados'].get('version'),str):
                catalogo = consultar(url,'/api/tags',timeout=3)
                modelos = catalogo.get('dados',{}).get('models') if isinstance(catalogo.get('dados'),dict) else None
                alvo.update(estado='pronto' if catalogo.get('ok') and isinstance(modelos,list) else 'indisponivel',
                    detalhe=('API local respondeu: '+str(len(modelos))+' modelo(s) no catálogo; geração não testada.' if isinstance(modelos,list) and catalogo.get('ok') else 'A versão respondeu, mas o catálogo não foi confirmado.'))
            else: alvo.update(estado='indisponivel',detalhe='Ollama não respondeu com metadados válidos; nenhuma geração foi enviada.')
        except (ValueError, OSError, RuntimeError): alvo.update(estado='indisponivel',detalhe='Não foi possível consultar o endereço local configurado.')
        alvo = next(i for i in itens if i['id']=='gateway')
        if meta.get('configurado'):
            from roteador_9router import listar_modelos
            try:
                catalogo = listar_modelos(timeout=3)
                alvo.update(estado='pronto',detalhe='API respondeu ao catálogo: '+str(len(catalogo['modelos']))+' modelo(s)/combo(s). Geração não testada.')
            except Exception:
                alvo.update(estado='indisponivel',detalhe='O catálogo do gateway não foi confirmado; nenhuma geração foi enviada.')
    return {'itens': itens, 'sondado': sondar, 'geracao_testada': False,
            'limites': 'Até três leituras explícitas com timeout de socket de três segundos; não é prazo absoluto de conclusão nem teste de contas/pareamento.'}


def resumo_prontidao(relatorio=None, *, sondar=False):
    relatorio = coletar_prontidao(sondar=sondar) if relatorio is None else relatorio
    texto = ['Estado das integrações — geração e pareamento não testados:']
    for item in relatorio['itens']:
        texto.append(item['nome']+': '+item['estado']+' — '+item['detalhe'])
        if item['estado'] in ('pendente','indisponivel'): texto.append('Próximo passo: '+item['proximo_passo'])
    from nucleo import redigir
    return str(redigir('\n'.join(texto)))[:6000]
