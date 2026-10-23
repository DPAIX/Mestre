"""Prepara uma vez a voz local e o início ao logar, usando configuração externa.

Não divulga o .env nem lê dados pessoais. O início normal/logon não executa o pip ou
baixa modelos; o assistente usa seu controle de instância para evitar duplicatas.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

import redirecionar_assistente as redirecionar
import startup_windows as startup
from instancia_assistente import InstanciaAtiva, instancia_unica

BASE=Path(__file__).resolve().parent
TIMEOUT_PIP=900
TIMEOUT_MODELO=900
PUBLICAS={'PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','TEMP','TMP','LANG','LC_ALL',
          'USERPROFILE','HOME','HOMEDRIVE','HOMEPATH','LOCALAPPDATA','APPDATA',
          'SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY',
          'VOZ_MODELO_LOCAL'}


def ambiente_preparacao(plano):
    """Pip/modelo não recebem chaves, PYTHONPATH ou credenciais de provedores."""
    ambiente={k:v for k,v in plano['ambiente'].items() if k.upper() in PUBLICAS}
    ambiente['MEUCONTROLEPC_ENV']=str(plano['arquivo_env'])
    ambiente['MEUCONTROLEPC_DADOS']=str(plano['dados'])
    return ambiente


def _executar(comando,plano,ambiente,prazo,rotulo):
    try:
        resultado=subprocess.run(comando,cwd=plano['cwd'],env=ambiente,shell=False,
                                 stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE,text=True,encoding='utf-8',errors='replace',
                                 timeout=prazo,check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError(rotulo+' excedeu o prazo. Nada foi apagado; execute a preparação novamente após conferir rede e espaço.') from None
    except OSError:
        raise RuntimeError('Não foi possível executar '+rotulo+'. Confira o Python e as permissões locais.') from None
    if resultado.returncode:
        # Pip/SDK podem repetir credenciais presentes na configuração do usuário.
        raise RuntimeError(rotulo+' não concluiu (código '+str(resultado.returncode)+'). Confira Python, conexão, espaço em disco e suporte das dependências; configuração e dados foram preservados.')
    return resultado


def planejar_preparacao(codigo=None,arquivo_env_externo=None,dados=None,python=None,*,incluir_google=False):
    """Valida caminhos/requisitos sem instalar pacotes ou ler a configuração."""
    if os.name!='nt':raise RuntimeError('A preparação do início automático está disponível apenas no Windows.')
    if not isinstance(incluir_google,bool):raise ValueError('A opção de Google deve ser verdadeira ou falsa.')
    codigo=Path(codigo) if codigo is not None else BASE
    env=arquivo_env_externo if arquivo_env_externo is not None else redirecionar.ENV_PADRAO
    plano=redirecionar.plano_execucao(codigo,env,dados,python,modo='start')
    requisitos=[plano['codigo']/'requirements.txt',plano['codigo']/'requirements-voz-local.txt']
    if incluir_google:requisitos.append(plano['codigo']/'requirements-google.txt')
    if any(not p.is_file() or not p.resolve().is_relative_to(plano['codigo']) for p in requisitos):
        raise RuntimeError('Atualize todas as fontes: faltam os requisitos da aplicação e das integrações selecionadas.')
    if not (plano['codigo']/'transcritor_local.py').is_file():
        raise RuntimeError('Atualize todas as fontes: falta transcritor_local.py.')
    return plano


def preparar_componentes(plano,*,python_explicito=False,incluir_google=False):
    """Reutiliza/cria venv, instala requisitos e verifica bibliotecas/pesos.

    Compartilhado pela primeira ativação e pela manutenção; não altera Startup
    nem inicia o assistente. Os pesos já preparados são reutilizados.
    """
    if not isinstance(python_explicito,bool) or not isinstance(incluir_google,bool):
        raise ValueError('As opções da preparação devem ser booleanas.')
    ambiente=ambiente_preparacao(plano)
    _executar([str(plano['python']),'-c','import sys; raise SystemExit(0 if sys.version_info >= (3,11) else 2)'],
              plano,ambiente,15,'A verificação de Python 3.11 ou superior')
    # Reaproveita as .venv existentes. Sem uma delas, cria uma .venv do projeto,
    # evitando instalar bibliotecas de voz no Python global.
    candidatos=(plano['codigo']/'.venv'/'Scripts'/'python.exe',plano['arquivo_env'].parent/'.venv'/'Scripts'/'python.exe')
    if not python_explicito and not any(p.is_file() for p in candidatos):
        alvo=plano['codigo']/'.venv'
        print('Preparando ambiente Python do projeto...')
        _executar([str(plano['python']),'-m','venv',str(alvo)],plano,ambiente,180,'A criação do ambiente Python')
        plano=redirecionar.plano_execucao(plano['codigo'],plano['arquivo_env'],plano['dados'],alvo/'Scripts'/'python.exe',modo='start')
        ambiente=ambiente_preparacao(plano)
    print('Conferindo dependências da aplicação e da voz local...')
    requisitos=[plano['codigo']/'requirements.txt',plano['codigo']/'requirements-voz-local.txt']
    if incluir_google:requisitos.append(plano['codigo']/'requirements-google.txt')
    comando=[str(plano['python']),'-m','pip','install','--no-input','--no-cache-dir','--disable-pip-version-check']
    for requisito in requisitos:comando.extend(['-r',str(requisito)])
    _executar(comando,plano,ambiente,TIMEOUT_PIP,'A instalação das dependências')
    _executar([str(plano['python']),'-m','pip','check'],plano,ambiente,60,'A verificação de compatibilidade das dependências')
    print('Conferindo o transcritor local; pesos existentes serão reutilizados...')
    _executar([str(plano['python']),'-c','from nucleo import ler_env; ler_env(); from transcritor_local import preparar_modelo; preparar_modelo()'],
              plano,ambiente,TIMEOUT_MODELO,'A preparação do modelo de voz')
    return plano


def iniciar_assistente(plano):
    try:
        return subprocess.Popen(plano['comando'],cwd=plano['cwd'],env=plano['ambiente'],
                                shell=False,stdin=subprocess.DEVNULL)
    except OSError:
        raise RuntimeError('Não foi possível iniciar o bot agora. Abra iniciar_redirecionado.bat; configuração e dados foram preservados.') from None


def preparar(codigo=None,arquivo_env_externo=None,dados=None,python=None,*,iniciar=True):
    """Instala dependências, prepara o modelo, registra o logon e inicia o bot."""
    if not isinstance(iniciar,bool):raise ValueError('A opção de início deve ser verdadeira ou falsa.')
    plano=planejar_preparacao(codigo,arquivo_env_externo,dados,python)
    startup.conferir_destino()
    try:
        with instancia_unica(plano['dados']):
            plano=preparar_componentes(plano,python_explicito=python is not None)
            arquivo=startup.registrar_inicio(plano['codigo'],plano['python'],
                arquivo_env_externo=plano['arquivo_env'],dados=plano['dados'])
    except InstanciaAtiva:
        raise RuntimeError('Encerre a janela do assistente antes da preparação e abra ativar_assistente_automatico.bat novamente. Nenhum processo foi encerrado.') from None
    print('Início automático configurado após o logon do usuário. A voz local e a equipe padrão ficam prontas para mensagens comuns.')
    processo=None
    if iniciar:
        processo=iniciar_assistente(plano)
    return {'inicio':arquivo,'processo':processo,'python':plano['python']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codigo',default=str(BASE))
    parser.add_argument('--env',dest='arquivo_env',default=redirecionar.ENV_PADRAO)
    parser.add_argument('--dados')
    parser.add_argument('--python')
    args=parser.parse_args(argv)
    try:
        preparar(args.codigo,args.arquivo_env,args.dados,args.python)
        return 0
    except (OSError,RuntimeError,ValueError) as erro:
        print('Preparação não concluída: '+str(erro))
        return 2
    except KeyboardInterrupt:
        print('\nPreparação interrompida. Configuração e dados foram preservados.')
        return 130


if __name__=='__main__':sys.exit(main())
