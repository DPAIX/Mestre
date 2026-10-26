"""Preparacao e abertura explicitas de 9Router/9Remote no Windows.

Pacotes oficiais fixados por versao, separados das fontes e do .env do bot.
Nenhuma instalacao, conexao, leitura de credenciais ou execucao na importacao.
9Remote pertence a outro projeto: suas permissoes e seu pareamento devem ser
conferidos na interface oficial; o painel do MeuControlePC nao e exposto.

Fontes consultadas em 2026-10-23:
https://github.com/decolua/9router/blob/master/cli/cli.js
https://github.com/decolua/9router/blob/master/cli/package.json
https://github.com/decolua/9remote/blob/main/host/cli/index.js
https://github.com/decolua/9remote/blob/main/host/cli/modes/ui.js
https://github.com/decolua/9remote/blob/main/host/cli/modes/headless.js
https://github.com/decolua/9remote/blob/main/host/package.json
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import socket
import stat
import subprocess
import sys
import threading
import webbrowser

BASE = Path(__file__).resolve().parent
NODE_MINIMO = 22
PRAZO_NODE = 5
PRAZO_INSTALACAO = 600
REGISTRO_NPM = 'https://registry.npmjs.org'
OPERACOES = ('instalar', 'abrir', 'iniciar')
SERVICOS = {
    '9router': {'nome':'9Router', 'versao':'0.5.109', 'script':'cli.js',
                'porta':20128, 'painel':'http://127.0.0.1:20128/dashboard'},
    '9remote': {'nome':'9Remote', 'versao':'3.0.43', 'script':'dist/cli.cjs',
                # Na 3.0.43, / e /ui levam ao workspace/login; o painel do
                # host empacotado permanece em /ui/index.html (commit 5f54ea2).
                'porta':2208, 'painel':'http://127.0.0.1:2208/ui/index.html'},
}
_PROCESSOS = {}
_TRAVA = threading.Lock()


def _servico(valor):
    if not isinstance(valor,str) or valor not in SERVICOS:
        raise ValueError('Escolha 9router ou 9remote.')
    return SERVICOS[valor]


def preparar_9stack(servico,operacao='abrir'):
    """Plano puro para uma unica operacao; nunca contem comandos livres."""
    item=_servico(servico)
    if not isinstance(operacao,str) or operacao not in OPERACOES:
        raise ValueError('Escolha instalar, abrir ou iniciar.')
    if operacao=='instalar':
        descricao=(f'Instalar {item["nome"]} {item["versao"]} e dependencias oficiais em pasta propria do usuario. '
                   'Requer Node.js 22+ e rede; o npm executa os scripts desses pacotes. '
                   'Os projetos tambem podem criar runtimes no perfil do usuario. '
                   'Nao inicia o servico nem ativa acesso remoto. Acompanhe a janela do PC.')
    elif servico=='9router':
        descricao=('Abrir o painel local do 9Router. Contas e modelos sao configurados la; nao comprova conexao.'
                   if operacao=='abrir' else
                   'Iniciar 9Router em 127.0.0.1:20128, sem atualizar automaticamente. '
                   'Os provedores configurados nele podem usar contas e cotas. Nenhuma pergunta sera enviada agora.')
    elif operacao=='abrir':
        descricao=('Abrir a interface do 9Remote no PC, sem solicitar inicio do tunel. '
                   'As permissoes, dispositivos e ativacao remota sao controlados pela interface oficial. '
                   'Nao compartilhe chaves ou QR codes do pareamento.')
    else:
        descricao=('Iniciar o host e o tunel REMOTO do 9Remote. Dispositivos autorizados no 9Remote podem acessar '
                   'terminal, arquivos e tela do PC. Confira permissoes e pareamento na janela oficial; '
                   'o servidor segue as regras de rede proprias do 9Remote. Nao compartilhe chaves ou QR codes. '
                   'Encerre pelo 9Remote quando terminar. O painel do assistente continua local.')
    return {'servico':servico,'operacao':operacao,'descricao':descricao}


def _ambiente():
    # O bot carrega chaves no ambiente. Filtrar, em vez de manter uma denylist.
    nomes={'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE',
           'USERPROFILE','HOMEDRIVE','HOMEPATH','APPDATA','LOCALAPPDATA',
           'PROGRAMFILES','PROGRAMFILES(X86)','PROGRAMDATA','TEMP','TMP',
           'USERNAME','USERDOMAIN','OS','PROCESSOR_ARCHITECTURE',
           'NUMBER_OF_PROCESSORS','LANG','LC_ALL','TERM','COLORTERM'}
    return {k:v for k,v in os.environ.items() if k.upper() in nomes}


def _pasta(servico):
    _servico(servico)
    local=os.environ.get('LOCALAPPDATA','')
    raiz=Path(local) if local else None
    if raiz is None or not raiz.is_absolute():
        raise RuntimeError('LOCALAPPDATA do Windows nao foi localizado; nenhuma pasta foi criada.')
    destino=raiz/'MeuControlePC'/'integracoes'/servico
    pacote=destino/'node_modules'/servico
    componentes=(raiz,raiz/'MeuControlePC',destino.parent,destino,
                 destino/'package.json',destino/'package-lock.json',
                 destino/'npm-shrinkwrap.json',destino/'.npmrc',
                 destino/'node_modules',pacote,pacote/'package.json')
    if servico=='9remote':componentes+=((pacote/'dist'),)
    for pasta in componentes:
        try:
            meta=pasta.lstat()
        except FileNotFoundError:continue
        except OSError:
            raise RuntimeError('Nao foi possivel conferir a pasta gerenciada. Verifique as permissoes locais.') from None
        if (stat.S_ISLNK(meta.st_mode) or
                bool(getattr(meta,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0))):
            raise RuntimeError('A pasta gerenciada nao pode usar links ou redirecionamentos de diretorio.')
    return destino


def _script(servico):
    """Metadados do pacote gerenciado; nunca abre bancos ou config do produto."""
    item=_servico(servico)
    try:
        pasta=_pasta(servico)
        pacote=pasta/'node_modules'/servico
        manifesto=pacote/'package.json'
        if manifesto.is_symlink() or not manifesto.is_file() or manifesto.stat().st_size>65536:return None
        dados=json.loads(manifesto.read_text(encoding='utf-8'))
        if not isinstance(dados,dict) or dados.get('name')!=servico or dados.get('version')!=item['versao']:return None
        arquivo=pacote/item['script']
        if (arquivo.is_symlink() or not arquivo.is_file() or
                not arquivo.resolve().is_relative_to(pasta.resolve())):return None
        return arquivo
    except (OSError,RuntimeError,ValueError,UnicodeError):
        return None


def _corrigir_9remote(script):
    # Somente o pacote gerenciado exato recebe a correção com backup/hash.
    # Mantém DNS nativo e evita encerramento de aplicativos por porta/PID salvo.
    from correcao_dns_9remote import aplicar_correcao
    return aplicar_correcao(script.parents[1])


def catalogo_9stack():
    """Sem executar Node/npm e sem testar servicos ou ler credenciais."""
    node=bool(shutil.which('node.exe') or shutil.which('node'))
    return [{'servico':nome,'nome':item['nome'],'versao_fixada':item['versao'],
             'instalado_gerenciado':_script(nome) is not None,'node_no_path':node,
             'painel':item['painel']} for nome,item in SERVICOS.items()]


def resumo_9stack():
    linhas=['9Router e 9Remote: integracoes oficiais separadas do assistente.']
    for item in catalogo_9stack():
        linhas.append(item['nome']+' '+item['versao_fixada']+': '+
                      ('pacote gerenciado localizado' if item['instalado_gerenciado'] else 'pacote gerenciado ainda nao localizado'))
    linhas.extend(['Node.js 22+ e necessario; PATH ou pacote presente nao comprovam funcionamento.',
                   '9Router conecta provedores no painel local. 9Remote controla pareamento e permissoes na propria interface.',
                   'Nenhum tunel ou aplicativo e iniciado por esta consulta.'])
    return '\n'.join(linhas)


def _windows():
    if sys.platform!='win32':raise RuntimeError('Esta integracao abre programas somente no Windows.')


def _node(ambiente):
    caminho=shutil.which('node.exe') or shutil.which('node')
    if not caminho:raise RuntimeError('Instale Node.js 22 LTS ou mais recente pelo site nodejs.org e reabra o terminal.')
    arquivo=Path(caminho).resolve()
    if arquivo.suffix.lower()!='.exe' or not arquivo.is_file():
        raise RuntimeError('Use o node.exe oficial instalado no Windows; scripts de shell nao sao aceitos.')
    try:
        res=subprocess.run([str(arquivo),'--version'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL,timeout=PRAZO_NODE,check=False,shell=False,
                           cwd=str(arquivo.parent),env=ambiente,text=True,encoding='utf-8',errors='replace')
    except (OSError,subprocess.TimeoutExpired):
        raise RuntimeError('Nao foi possivel conferir o Node.js em ate 5 segundos.') from None
    versao=res.stdout.strip() if isinstance(res.stdout,str) else ''
    match=re.fullmatch(r'v([0-9]{1,3})\.[0-9]{1,5}\.[0-9]{1,5}',versao)
    if res.returncode or not match or int(match[1])<NODE_MINIMO:
        raise RuntimeError('Este fluxo requer Node.js 22 ou mais recente; nenhuma instalacao ou abertura foi feita.')
    return arquivo


def _npm_cli(node):
    # Evita npm.cmd/cmd.exe e interpretacao de argumentos pelo shell.
    candidatos=[node.parent/'node_modules'/'npm'/'bin'/'npm-cli.js']
    shim=shutil.which('npm.cmd')
    if shim:candidatos.append(Path(shim).resolve().parent/'node_modules'/'npm'/'bin'/'npm-cli.js')
    for arquivo in candidatos:
        if not arquivo.is_symlink() and arquivo.is_file():return arquivo
    raise RuntimeError('npm-cli.js nao localizado. Repare a instalacao oficial do Node.js com npm.')


def instalar_9stack(servico,*,confirmado=False):
    """Worker finito, executado em console proprio apos autorizacao explicita."""
    item=_servico(servico)
    if confirmado is not True:raise PermissionError('Confirme a instalacao antes de executar npm.')
    _windows()
    ambiente=_ambiente();node=_node(ambiente);npm=_npm_cli(node)
    pasta=_pasta(servico)
    try:pasta.mkdir(parents=True,exist_ok=True)
    except OSError:
        raise RuntimeError('Nao foi possivel preparar a pasta de instalacao. Confira permissoes e espaco livre.') from None
    argumentos=[str(node),str(npm),'install','--prefix',str(pasta),
                '--registry',REGISTRO_NPM,'--no-audit','--no-fund','--save-exact',
                servico+'@'+item['versao']]
    try:
        resultado=subprocess.run(argumentos,shell=False,cwd=str(pasta),env=ambiente,
                                 timeout=PRAZO_INSTALACAO,check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError('O limite de 10 minutos do npm acabou; dependencias podem estar incompletas e scripts filhos podem continuar. Nenhuma nova tentativa foi enviada.') from None
    except OSError:
        raise RuntimeError('Nao foi possivel executar npm; confira a instalacao do Node.js e as permissoes locais.') from None
    script=_script(servico)
    if resultado.returncode or script is None:
        raise RuntimeError('O npm nao confirmou o pacote e a versao esperados; confira o erro na janela do PC.')
    if servico=='9remote':_corrigir_9remote(script)
    return item['nome']+' '+item['versao']+' instalado. O servico nao foi iniciado; nenhuma inferencia ou conexao remota foi testada.'


def _porta_ocupada(porta):
    try:
        with socket.create_connection(('127.0.0.1',porta),timeout=.4):return True
    except OSError:return False


def _janela(chave,argumentos,ambiente,cwd):
    with _TRAVA:
        anterior=_PROCESSOS.get(chave)
        if anterior is not None and anterior.poll() is None:
            return False
        try:
            processo=subprocess.Popen(argumentos,shell=False,cwd=str(cwd),env=ambiente,
                                       close_fds=True,creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0x10))
        except OSError:
            raise RuntimeError('O Windows nao abriu a janela solicitada. Confira os arquivos e permissoes locais.') from None
        _PROCESSOS[chave]=processo
    return True


def executar_9stack(servico,operacao='abrir',*,confirmado=False):
    plano=preparar_9stack(servico,operacao)
    if confirmado is not True:raise PermissionError('Confirme esta operacao antes de executar a integracao.')
    _windows()
    item=SERVICOS[servico]
    ambiente=_ambiente()
    if operacao=='instalar':
        _node(ambiente)
        abriu=_janela('instalar:'+servico,[sys.executable,str(Path(__file__).resolve()),
                        '--instalar',servico,'--confirmar'],ambiente,BASE)
        return ('Instalacao de '+item['nome']+' solicitada na janela do PC; aguarde o resultado la.' if abriu else
                'A instalacao desse pacote ja tem uma janela ativa. Confira o resultado no PC.')
    if servico=='9router' and operacao=='abrir':
        if not webbrowser.open(item['painel']):raise RuntimeError('O navegador nao confirmou a abertura do painel local.')
        return 'Abertura do painel local 9Router solicitada. Isso nao inicia o servico nem comprova provedores disponiveis.'
    if _porta_ocupada(item['porta']):
        if operacao=='abrir':
            webbrowser.open(item['painel'])
            return 'A porta local ja esta em uso; abertura da interface solicitada sem iniciar outra instancia. Confira qual aplicativo responde no PC.'
        return 'A porta local ja esta em uso. Nenhuma instancia foi iniciada ou encerrada; confira a interface oficial para ativar ou parar o servico.'
    script=_script(servico)
    if script is None:raise RuntimeError('Instale primeiro o pacote gerenciado '+item['nome']+' '+item['versao']+'.')
    node=_node(ambiente)
    if servico=='9remote':_corrigir_9remote(script)
    argumentos=[str(node),str(script)]
    if servico=='9router':
        argumentos+=['--host','127.0.0.1','--port','20128','--tray','--no-browser','--skip-update']
    else:
        argumentos+=['ui' if operacao=='abrir' else 'start']
    if not _janela(servico,argumentos,ambiente,_pasta(servico)):
        return 'Ja existe uma janela desta integracao aberta pelo assistente. Confira-a no PC.'
    if servico=='9remote':
        return ('Interface 9Remote solicitada no PC, sem pedir inicio do tunel. Quando estiver pronta, abra '+item['painel']+' no navegador do PC. A configuracao e a aprovacao de dispositivos pertencem ao 9Remote.' if operacao=='abrir' else
                'Host e tunel REMOTO do 9Remote solicitados na janela do PC. Confira as permissoes e os dispositivos na interface oficial. Nenhuma chave ou URL de pareamento foi enviada ao assistente.')
    return 'Inicio do 9Router solicitado em 127.0.0.1:20128. Abra o painel para configurar provedores; nenhuma resposta foi testada.'


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--listar',action='store_true')
    p.add_argument('--instalar',choices=tuple(SERVICOS))
    p.add_argument('--servico',choices=tuple(SERVICOS))
    p.add_argument('--operacao',choices=OPERACOES,default='abrir')
    p.add_argument('--confirmar',action='store_true')
    args=p.parse_args(argv)
    try:
        if args.listar:print(resumo_9stack());return 0
        if args.instalar:
            if not args.confirmar:raise PermissionError('O worker de instalacao exige --confirmar.')
            print(instalar_9stack(args.instalar,confirmado=True))
            return 0
        servico=args.servico;operacao=args.operacao
        if not servico:
            print(resumo_9stack())
            servico=input('Servico (9router/9remote; Enter encerra): ').strip()
            if not servico:return 0
            _servico(servico)
            operacao=input('Operacao (instalar/abrir/iniciar; Enter = '+operacao+'): ').strip() or operacao
        plano=preparar_9stack(servico,operacao)
        print(plano['descricao'])
        if not args.confirmar and input('Confirma? Digite sim: ').strip().casefold()!='sim':
            print('Operacao cancelada.');return 0
        print(executar_9stack(servico,operacao,confirmado=True))
        return 0
    except (ValueError,RuntimeError,PermissionError) as erro:
        print('Integracao nao concluida: '+str(erro));return 1
    except (EOFError,KeyboardInterrupt):
        print('Operacao cancelada.');return 0
    except OSError:
        print('Integracao nao concluida: confira permissoes e espaco livre. Nenhuma nova tentativa foi enviada.');return 1
    finally:
        # O worker abre console proprio: mantenha seu resultado visivel, sem
        # transportar a saida do npm (ou dados do produto) ao bot.
        if args.instalar:
            try:
                if sys.stdin.isatty():input('\nInstalador encerrado. Pressione Enter para fechar esta janela.')
            except (EOFError,KeyboardInterrupt):pass


if __name__=='__main__':raise SystemExit(main())
