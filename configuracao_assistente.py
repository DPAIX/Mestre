"""Configuração local guiada, independente de respostas dos modelos.

A interface autenticada confirma apenas a abertura deste configurador. Cada
etapa concreta é apresentada novamente na janela do PC. Nenhum serviço remoto,
modelo em nuvem ou instalação é ativado apenas por importar ou resumir o módulo.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from caminhos_instalacao import arquivo_env,diretorio_dados

BASE=Path(__file__).resolve().parent
_TRAVA=threading.Lock()
_PROCESSO=None
_PUBLICAS=frozenset({
    'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE',
    'USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA',
    'PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','TEMP','TMP',
    'USERNAME','USERDOMAIN','OS','PROCESSOR_ARCHITECTURE','NUMBER_OF_PROCESSORS',
    'LANG','LC_ALL','TERM','COLORTERM','OLLAMA_HABILITADO','OLLAMA_URL',
    'OLLAMA_MODEL','OLLAMA_PERFIL','OLLAMA_MODELS','OLLAMA_NO_CLOUD','OLLAMA_INICIAR_SERVICO','NINE_ROUTER_HABILITADO',
    'NINE_ROUTER_URL','NINE_ROUTER_MODEL','NINE_ROUTER_TIMEOUT','GEMINI_API_MODO','GEMINI_MODEL','VOZ_MODELO_LOCAL','MEMORIA_HABILITADA',
})
_ETAPAS=(
    ('verificar_prontidao','Conferir requisitos e pendências de todos os recursos, sem testar geração'),
    ('dependencias_voz','Preparar bibliotecas Python/Google e pesos da voz local (encerre o bot; requer rede/espaço)'),
    ('instalar_node','Conferir Node.js 22+; se ausente, instalar o LTS oficial pelo winget'),
    ('telegram','Configurar token e proprietários Telegram com entrada oculta no console'),
    ('modelos_ollama','Escolher modelo e perfil Ollama pela configuração local, sem gerar resposta'),
    ('perfil_cpu','Selecionar perfil CPU compacto com Llama local, sem download ou geração'),
    ('politica_ollama','Escolher se o assistente pode iniciar ollama serve quando estiver ausente'),
    ('instalar_9router','Instalar o 9Router gerenciado, se necessário (requer Node.js 22+, npm e rede)'),
    ('instalar_9remote','Instalar o 9Remote gerenciado, se necessário (não inicia acesso remoto)'),
    ('preparar_9router','Iniciar o 9Router em loopback e abrir seu dashboard para contas e combos'),
    ('configurar_9router','Configurar o cliente 9Router deste assistente, com chave opcional em entrada oculta'),
    ('consultar_ollama','Consultar somente versão e catálogo local do Ollama, sem gerar respostas'),
    ('abrir_9remote','Abrir a interface do 9Remote, sem solicitar início do túnel'),
    ('gemini','Configurar Gemini Interactions no console; não cria tarefas nem testa cota'),
    ('agentes','Escolher e configurar aplicativos de agentes pelo lançador oficial do Ollama'),
    ('inicio_gerenciado','Ativar só o início gerenciado do assistente; guardar o atalho legado exato, se existir'),
    ('sondar_servicos','Conferir APIs locais Ollama/9Router; o catálogo do gateway pode contatar provedores'),
)


def preparar_configuracao():
    """Plano puro, revalidável pelo interpretador e sem sondar o computador."""
    return {'acao':'configurar_assistente','campos':{},'descricao':
        'Abrir a configuração local guiada em outra janela do PC. Conferir requisitos e oferecer instalação '
        'de dependências/voz, Telegram, Ollama, agentes, 9Router/9Remote, Gemini e início gerenciado. '
        'Cada etapa será revisada no console. Não inicia túnel remoto, não ativa nuvem e não gera respostas automaticamente'}


def plano_configuracao():
    return preparar_configuracao()


def _dependencia(nome):
    try:return importlib.util.find_spec(nome) is not None
    except (ImportError,ModuleNotFoundError,ValueError):return False


def resumo_configuracao():
    """Somente opções públicas em memória, PATH e metadados de pacotes.

    Não abre .env/dados, executa Node, consulta portas/serviços ou testa geração.
    'Presente' indica somente o requisito observado, não disponibilidade de IA.
    """
    from integracoes_9stack import catalogo_9stack
    from roteador_9router import diagnostico_local
    linhas=['⚙️ Configuração local do assistente — sem consulta às IAs:']
    linhas.append(('Pronto' if sys.version_info>=(3,11) else 'Pendente')+': Python 3.11 ou superior neste processo.')
    for nome,rotulo in (('telebot','biblioteca Telegram'),('faster_whisper','biblioteca de voz local')):
        linhas.append(('Presente' if _dependencia(nome) else 'Pendente')+': '+rotulo+'; funcionamento não testado.')
    node=bool(shutil.which('node.exe') or shutil.which('node'))
    linhas.append('Node.js: '+('comando localizado; a versão 22+ e o npm serão conferidos na instalação.' if node else
                              'pendente. Instale Node.js 22+ com npm em https://nodejs.org/en/download e reabra o terminal.'))
    ollama=bool(shutil.which('ollama.exe') or shutil.which('ollama'))
    linhas.append('Ollama: '+('comando localizado; serviço e geração ainda não testados.' if ollama else
                             'comando não localizado no PATH; confira a instalação no PC.'))
    for item in catalogo_9stack():
        linhas.append(item['nome']+': '+('pacote gerenciado presente; serviço não testado.' if item['instalado_gerenciado'] else
                                        'instalação gerenciada pendente.'))
    meta=diagnostico_local()
    linhas.append('Cliente 9Router: '+('configurado em memória; contas e resposta não verificadas.' if meta.get('configurado') else
                                      'pendente de ativação e seleção de modelo/combo válidos.'))
    linhas.append('A preparação completa também inclui Telegram, voz, Gemini Interactions, agentes e início gerenciado. Use /integracoes ou o painel para o estado por recurso.')
    linhas.extend([
        'Etapas: instalar os pacotes desejados, abrir o dashboard, conectar contas e salvar o modelo/combo no console.',
        'Bibliotecas Python ausentes: encerre o bot e abra atualizar_assistente.bat; não reinstalar o ambiente em uso.',
        'Para executar as etapas, peça “faça as configurações necessárias” e confirme a abertura no PC. '
        'Nenhuma configuração, serviço ou conta foi alterado por este diagnóstico.',
    ])
    return '\n'.join(linhas)[:2400]


def _ambiente_configurador():
    ambiente={k:v for k,v in os.environ.items() if k.upper() in _PUBLICAS}
    # Caminhos públicos selecionam a instalação externa; nenhum conteúdo ou
    # credencial do .env é copiado para o ambiente do configurador.
    ambiente['MEUCONTROLEPC_ENV']=str(arquivo_env(BASE))
    ambiente['MEUCONTROLEPC_DADOS']=str(diretorio_dados(BASE))
    return ambiente


def abrir_configuracao(*,confirmado=False):
    """Abre uma única janela do configurador após autorização do proprietário."""
    global _PROCESSO
    if confirmado is not True:raise PermissionError('Confirme a abertura da configuração local antes de executar.')
    if sys.platform!='win32':raise RuntimeError('A configuração guiada abre uma janela no Windows do assistente.')
    ambiente=_ambiente_configurador()
    with _TRAVA:
        if _PROCESSO is not None and _PROCESSO.poll() is None:
            return 'A configuração local já está aberta. Confira a janela do configurador no PC.'
        try:
            _PROCESSO=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--assistente'],
                cwd=str(BASE),env=ambiente,shell=False,close_fds=True,
                creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0x10))
        except OSError:
            raise RuntimeError('O Windows não abriu o configurador. Confira a sessão local e as permissões do Python.') from None
    return ('Configuração local guiada aberta na janela do PC. Ela mostra as pendências e as etapas de '
            'instalação, dashboard e conta. Acompanhe as opções nessa janela; nenhuma IA ou túnel remoto foi iniciado.')


def _instalar_se_pendente(servico):
    import integracoes_9stack as stack
    presente=next(item['instalado_gerenciado'] for item in stack.catalogo_9stack() if item['servico']==servico)
    if presente:return stack.SERVICOS[servico]['nome']+' já tem o pacote gerenciado esperado. Não foi reinstalado.'
    return stack.instalar_9stack(servico,confirmado=True)


def executar_etapa(etapa,*,confirmado=False):
    """Lista fixa; não aceita comandos, prompts, contas ou código de modelos."""
    if not isinstance(etapa,str) or etapa not in {item[0] for item in _ETAPAS}:raise ValueError('Etapa de configuração não permitida.')
    if confirmado is not True:raise PermissionError('Confirme a etapa concreta antes de executar.')
    if sys.platform!='win32':raise RuntimeError('Execute a configuração guiada na sessão Windows do PC.')
    if etapa in ('verificar_prontidao','sondar_servicos'):
        from prontidao_assistente import resumo_prontidao
        return resumo_prontidao(sondar=etapa=='sondar_servicos')
    if etapa=='dependencias_voz':
        from manutencao_assistente import manter
        manter(BASE,arquivo_env(BASE),diretorio_dados(BASE),iniciar=False)
        return 'Bibliotecas e pesos de voz preparados. O bot e o início automático não foram ativados por esta etapa.'
    if etapa=='instalar_node':
        return _preparar_node()
    if etapa=='telegram':
        resultado=subprocess.run([sys.executable,str(BASE/'configurar_telegram.py')],cwd=str(BASE),env=_ambiente_configurador(),shell=False,check=False)
        return 'Configurador Telegram encerrado; confira a mensagem no console. Reinicie o bot após salvar credenciais.' if resultado.returncode==0 else 'Telegram continua pendente; confira a mensagem no console.'
    if etapa=='modelos_ollama':
        from configurar_ia_local import main as configurar
        codigo=configurar([],caminho=arquivo_env(BASE))
        return 'Configuração Ollama encerrada; confira as escolhas salvas.' if codigo==0 else 'Configuração Ollama pendente.'
    if etapa=='perfil_cpu':
        from configurar_ia_local import main as configurar
        codigo=configurar(['--perfil-cpu'],caminho=arquivo_env(BASE))
        return 'Perfil CPU configurado; geração não testada.' if codigo==0 else 'Perfil CPU pendente; confira o catálogo local.'
    if etapa=='politica_ollama':
        from configurar_ia_local import _atualizar_opcoes_env
        valor=input('Iniciar o serviço Ollama ausente? 0 = somente usar o serviço existente; 1 = permitir início: ').strip()
        if valor not in ('0','1'):raise ValueError('Use 0 ou 1 para a política de início.')
        _atualizar_opcoes_env({'OLLAMA_INICIAR_SERVICO':valor},caminho=arquivo_env(BASE))
        os.environ['OLLAMA_INICIAR_SERVICO']=valor
        return 'Política de início Ollama salva. Nenhum processo foi iniciado ou encerrado agora.'
    if etapa=='gemini':
        from configurar_gemini import main as configurar
        configurar();return 'Configurador Gemini encerrado; nenhuma tarefa ou geração foi enviada.'
    if etapa=='agentes':
        from integracoes_agentes import catalogo_agentes,abrir_agente
        for agente in catalogo_agentes():print(agente['agente']+' — '+agente['nome'])
        escolhido=input('ID de um agente (Enter encerra esta etapa): ').strip()
        if not escolhido:return 'Etapa encerrada sem abrir agente.'
        modelo=input('Modelo opcional (Enter usa a escolha do lançador): ').strip()
        return abrir_agente(escolhido,modelo=modelo,configurar=True,confirmado=True)
    if etapa=='inicio_gerenciado':
        from startup_windows import consolidar_inicio
        resultado=consolidar_inicio(BASE,sys.executable,arquivo_env_externo=arquivo_env(BASE),dados=diretorio_dados(BASE),confirmado=True)
        return 'Entrada gerenciada criada: '+str(resultado['inicio'])+'. Confira sua habilitação na aba Inicializar do Gerenciador de Tarefas. Aplicativos externos e suas opções de início foram preservados.'
    if etapa in ('instalar_9router','instalar_9remote'):
        return _instalar_se_pendente('9router' if etapa=='instalar_9router' else '9remote')
    if etapa=='preparar_9router':
        from integracoes_9stack import executar_9stack
        inicio=executar_9stack('9router','iniciar',confirmado=True)
        if not _aguardar_9router():return inicio+'\nO gateway ainda não respondeu. Abertura do dashboard ficou pendente; use Abrir no painel após conferir a janela do serviço.'
        abertura=executar_9stack('9router','abrir',confirmado=True)
        return inicio+'\n'+abertura+'\nConecte suas contas e escolha um modelo/combo no dashboard antes da próxima etapa.'
    if etapa=='configurar_9router':
        from configurar_9router import main as configurar
        resultado=configurar([])
        return ('Configurador do cliente encerrado. Confira as opções salvas; uma etapa cancelada não ativa o gateway.' if resultado==0 else
                'A configuração do cliente continua pendente. Confira a mensagem acima e os requisitos locais.')
    if etapa=='abrir_9remote':
        from integracoes_9stack import executar_9stack
        return executar_9stack('9remote','abrir',confirmado=True)
    from diagnostico_ollama import consultar,validar_url,URL_PADRAO
    url=validar_url(os.getenv('OLLAMA_URL',URL_PADRAO))
    versao=consultar(url,'/api/version',timeout=3)
    if not versao.get('ok'):return 'Ollama não respondeu à leitura de versão. Nenhuma geração ou nova tentativa foi enviada.'
    catalogo=consultar(url,'/api/tags',timeout=3)
    dados=catalogo.get('dados')
    modelos=dados.get('models') if isinstance(dados,dict) else None
    if not catalogo.get('ok') or not isinstance(modelos,list):
        return 'Ollama respondeu à versão; o catálogo não foi confirmado. Nenhuma geração foi enviada.'
    return f'Ollama respondeu aos metadados: {len(modelos)} modelo(s) registrado(s). A geração de respostas não foi testada.'


def _aguardar_9router():
    from roteador_9router import listar_modelos
    from multi_ia import FalhaAPI
    for tentativa in range(3):
        try:listar_modelos(timeout=2);return True
        except FalhaAPI as erro:
            if erro.codigo in (401,403):return True
        if tentativa<2:time.sleep(0.5)
    return False


def _preparar_node():
    import integracoes_9stack as stack
    try:stack._node(stack._ambiente());return 'Node.js compatível já localizado; nenhum instalador foi executado.'
    except RuntimeError:pass
    winget=shutil.which('winget.exe')
    if not winget:return 'Node.js pendente. Instale o LTS com npm em https://nodejs.org/en/download e reabra o configurador.'
    retorno=subprocess.run([winget,'install','--id','OpenJS.NodeJS.LTS','--exact','--source','winget',
        '--accept-package-agreements','--accept-source-agreements','--disable-interactivity'],
        env=_ambiente_configurador(),shell=False,timeout=600,check=False)
    if retorno.returncode:return 'Instalação Node.js não confirmada. Confira o instalador no PC.'
    pasta=Path(os.getenv('ProgramFiles',r'C:\Program Files'))/'nodejs'
    if (pasta/'node.exe').is_file():os.environ['PATH']=str(pasta)+os.pathsep+os.environ.get('PATH','')
    stack._node(stack._ambiente())
    return 'Node.js compatível localizado após o instalador oficial.'


def assistente():
    """Uma passagem finita; contas e escolhas permanecem com o dono no PC."""
    print(resumo_configuracao())
    print('\nAs etapas abaixo são independentes. Digite sim para executar ou Enter para deixar pendente.')
    print('Não haverá testes de geração, seleção automática de modelo pago ou início de túnel remoto.')
    for etapa,rotulo in _ETAPAS:
        if input('\n'+rotulo+'? ').strip().casefold()!='sim':
            print('Etapa não solicitada; nenhuma alteração foi feita por ela.')
            continue
        try:print(executar_etapa(etapa,confirmado=True))
        except (ValueError,RuntimeError,PermissionError,OSError,subprocess.SubprocessError):
            # Dependências podem repetir dados privados no erro; não imprimir
            # a saída bruta de pacotes ou rastros das contas nesta camada.
            print('Esta etapa não concluiu. Confira Node.js 22+, npm, instalação local, espaço e permissões. '
                  'Nenhuma nova tentativa automática foi enviada; a etapa continua pendente.')
    print('\nConfiguração guiada encerrada. Etapas recusadas ou com falha continuam pendentes.')
    print('Se salvou uma credencial pelo console, reinicie o assistente para recarregá-la. '
          'A geração de respostas e o acesso remoto não foram testados por este configurador.')
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assistente',action='store_true',help='Apresentar as etapas locais de configuração.')
    parser.add_argument('--resumo',action='store_true',help='Somente metadados locais, sem serviços ou alterações.')
    args=parser.parse_args(argv)
    try:
        if args.resumo:print(resumo_configuracao());return 0
        if sys.platform!='win32':raise RuntimeError('Abra o configurador na sessão Windows do PC.')
        from nucleo import ler_env
        if arquivo_env(BASE).is_file():ler_env()
        return assistente()
    except (EOFError,KeyboardInterrupt):
        print('\nConfiguração interrompida. As etapas concluídas foram mantidas; nenhuma nova etapa será enviada.')
        return 0
    except (ValueError,RuntimeError,OSError):
        print('Configuração local não iniciada. Confira a sessão Windows e os requisitos da instalação.')
        return 2
    finally:
        if args.assistente:
            try:
                if sys.stdin.isatty():input('\nPressione Enter para fechar o configurador.')
            except (EOFError,KeyboardInterrupt):pass


if __name__=='__main__':raise SystemExit(main())
