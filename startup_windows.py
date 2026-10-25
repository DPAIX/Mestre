"""Inscrição EXPLÍCITA no Startup do usuário Windows (após login, não como serviço)."""
import argparse
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import uuid
from caminhos_instalacao import arquivo_env, diretorio_dados

NOME='MeuControlePC_inicio_ao_logar.cmd'
ASSINATURA='REM Gerenciado por MeuControlePC v2.1'
LEGADOS=('assistente_pc.py - Atalho.lnk',)
MAX_GERENCIADO=65536
_TRAVA=threading.RLock()


def _sem_redirecionamento(caminho):
    """Não segue links, junctions ou outros reparse points nos destinos."""
    caminho=Path(caminho)
    if not caminho.is_absolute():raise ValueError('O destino de inicialização deve ser absoluto.')
    for parte in (caminho,*caminho.parents):
        try:estado=parte.lstat()
        except FileNotFoundError:continue
        if stat.S_ISLNK(estado.st_mode) or bool(getattr(estado,'st_file_attributes',0)&
                getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)):
            raise RuntimeError('O caminho de inicialização está redirecionado; nenhum arquivo será alterado.')
    return caminho


def _legados(arquivo):
    itens=[]
    for nome in LEGADOS:
        candidato=_sem_redirecionamento(arquivo.parent/nome)
        if candidato.exists():
            if not candidato.is_file():raise RuntimeError('Uma entrada antiga aponta para um diretório; confira o Startup.')
            itens.append(candidato)
    return itens


def inspecionar_inicio(arquivo=None):
    """Metadados de nomes fixos, sem ler atalhos, scripts ou o Registro.

    A existência do .cmd não comprova que o Windows o habilitou nem que o
    assistente iniciou. A assinatura é conferida somente ao solicitar alteração.
    """
    resultado={'estado':'indisponivel','gerenciado_presente':False,
               'gerenciado_valido':None,'conflitos':[],'candidatos':[]}
    try:
        arquivo=Path(arquivo) if arquivo is not None else destino()
        _sem_redirecionamento(arquivo)
        if arquivo.exists():
            if not arquivo.is_file():return resultado
            resultado['gerenciado_presente']=True
            resultado['candidatos'].append({'nome':arquivo.name,'gerenciado':True,'tipo':'arquivo'})
        antigos=_legados(arquivo)
        resultado['conflitos']=[p.name for p in antigos]
        resultado['candidatos'].extend({'nome':p.name,'gerenciado':False,'tipo':'arquivo'} for p in antigos)
        resultado['estado']='conflito' if antigos else ('presente' if resultado['gerenciado_presente'] else 'ausente')
    except (OSError,RuntimeError,ValueError):pass
    return resultado

def _argumento_cmd(valor):
    texto=str(valor)
    if any(c in texto for c in ('\x00','\r','\n','"')):
        raise ValueError('Caminho de inicialização inválido.')
    # Em arquivo .cmd, %% é literal. DelayedExpansion fica desligado para !.
    return '"'+texto.replace('%','%%')+'"'

def texto_inicio(pasta=None, python=None, *, arquivo_env_externo=None, dados=None):
    """Persiste os caminhos, sem copiar o .env ou seus valores para o atalho."""
    pasta=Path(pasta) if pasta is not None else Path(__file__).resolve().parent
    linhas=[ASSINATURA,'@echo off','setlocal DisableDelayedExpansion','chcp 65001 >nul',
            'cd /d '+_argumento_cmd(pasta)]
    if arquivo_env_externo is not None or 'MEUCONTROLEPC_ENV' in os.environ:
        env=Path(arquivo_env_externo) if arquivo_env_externo is not None else arquivo_env(pasta)
        dados=Path(dados) if dados is not None else (env.parent/'dados' if arquivo_env_externo is not None else diretorio_dados(pasta))
        comando=[
            python or sys.executable,pasta/'redirecionar_assistente.py',
            '--codigo',pasta,'--env',env]
        # O destino padrão pode ser criado pelo primeiro start. O launcher
        # exige que um --dados explícito já exista, para evitar troca acidental.
        if dados.exists() or dados!=env.parent/'dados':
            comando.extend(['--dados',dados])
        comando.append('start')
        linhas.append(' '.join(_argumento_cmd(x) for x in comando))
    else:
        if 'MEUCONTROLEPC_DADOS' in os.environ:
            dados=diretorio_dados(pasta)
            _argumento_cmd(dados)
            linhas.append('set "MEUCONTROLEPC_DADOS='+str(dados).replace('%','%%')+'"')
        linhas.append(_argumento_cmd(python or sys.executable)+' '+_argumento_cmd(pasta/'assistente_pc.py'))
    return '\n'.join(linhas)+'\n'

def destino():
    if os.name!='nt':raise RuntimeError('Disponível apenas no Windows.')
    appdata=os.environ.get('APPDATA')
    if not appdata:raise RuntimeError('APPDATA não disponível; não é possível localizar Startup.')
    pasta=Path(appdata)
    if not pasta.is_absolute():raise RuntimeError('APPDATA deve ser um caminho absoluto do usuário Windows.')
    return pasta/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup'/NOME


def conferir_destino(arquivo=None):
    """Preserva arquivos alheios; a assinatura deve ser a primeira linha."""
    arquivo=_sem_redirecionamento(Path(arquivo) if arquivo is not None else destino())
    if arquivo.exists():
        if not arquivo.is_file() or arquivo.stat().st_size>MAX_GERENCIADO:
            raise RuntimeError('A entrada de inicialização não é um script gerenciado válido.')
        texto=arquivo.read_text(encoding='utf-8-sig')
        if not texto.splitlines() or texto.splitlines()[0]!=ASSINATURA:
            raise RuntimeError('Já existe arquivo não identificado no caminho de destino; não será modificado.')
    return arquivo


def _gravar_atomico(arquivo,conteudo):
    arquivo.parent.mkdir(parents=True,exist_ok=True)
    fd,temporario=tempfile.mkstemp(prefix='.'+NOME+'.',suffix='.tmp',dir=str(arquivo.parent))
    try:
        with os.fdopen(fd,'wb') as fp:
            fp.write(conteudo);fp.flush();os.fsync(fp.fileno())
        os.replace(temporario,arquivo)
    finally:Path(temporario).unlink(missing_ok=True)


def registrar_inicio(pasta=None,python=None,*,arquivo_env_externo=None,dados=None):
    """Configuração explícita; não convive com o atalho legado conhecido."""
    with _TRAVA:
        arquivo=conferir_destino()
        if _legados(arquivo):
            raise RuntimeError('Há um atalho antigo do assistente no Startup. Use a consolidação explícita com backup antes de ativar.')
        texto=texto_inicio(pasta,python,arquivo_env_externo=arquivo_env_externo,dados=dados)
        if arquivo.exists() and arquivo.read_text(encoding='utf-8-sig')==texto:return arquivo
        _gravar_atomico(arquivo,texto.encode('utf-8'))
    return arquivo


def consolidar_inicio(pasta=None,python=None,*,arquivo_env_externo=None,dados=None,
                      confirmado=False,diretorio_backup=None):
    """Guarda só o atalho legado exato fora de Startup e registra o .cmd atual.

    Não abre .lnk, não toca entradas de Ollama/OpenClaw/Tailscale e não consulta
    o Registro. Falhas restauram o que já tiver sido movido, sem apagar backups
    necessários. Arquivos ou destinos redirecionados são recusados.
    """
    if confirmado is not True:raise PermissionError('Confirme a consolidação do início do assistente antes de alterar o Startup.')
    with _TRAVA:
        arquivo=conferir_destino()
        antigos=_legados(arquivo)
        texto=texto_inicio(pasta,python,arquivo_env_externo=arquivo_env_externo,dados=dados)
        anterior=arquivo.read_bytes() if arquivo.exists() else None
        raiz=Path(diretorio_backup) if diretorio_backup is not None else arquivo.parent.parent/'MeuControlePC_inicio_guardado'
        _sem_redirecionamento(raiz)
        if raiz.resolve().is_relative_to(arquivo.parent.resolve()):
            raise ValueError('O backup de inicialização deve ficar fora da pasta Startup.')
        backup=None;movidos=[]
        try:
            if antigos:
                raiz.mkdir(parents=True,exist_ok=True)
                backup=raiz/('consolidacao_'+uuid.uuid4().hex)
                backup.mkdir(exist_ok=False)
                for original in antigos:
                    destino_backup=backup/original.name
                    os.replace(original,destino_backup)
                    movidos.append((original,destino_backup))
            inicio=registrar_inicio(pasta,python,arquivo_env_externo=arquivo_env_externo,dados=dados)
        except (OSError,RuntimeError,ValueError):
            falha_reversao=False
            for original,salvo in reversed(movidos):
                try:
                    if original.exists():raise RuntimeError('Destino ocupado durante a reversão.')
                    os.replace(salvo,original)
                except (OSError,RuntimeError):falha_reversao=True
            try:
                if arquivo.exists() and arquivo.read_bytes()==texto.encode('utf-8'):
                    if anterior is None:arquivo.unlink()
                    else:_gravar_atomico(arquivo,anterior)
            except OSError:falha_reversao=True
            if backup is not None:
                try:backup.rmdir()
                except OSError:pass
            if falha_reversao:
                raise RuntimeError('Consolidação interrompida; a reversão não foi completa. Preserve a pasta de backup de início para restauração manual.') from None
            raise
        return {'inicio':inicio,'backup':backup,'legados_movidos':[p.name for p in antigos]}

def main():
    parser=argparse.ArgumentParser()
    p=parser.add_mutually_exclusive_group(required=True)
    p.add_argument('--ativar',action='store_true');p.add_argument('--desativar',action='store_true')
    args=parser.parse_args()
    arquivo=conferir_destino()
    if args.desativar:
        arquivo.unlink(missing_ok=True)
        print('Inicialização automática desabilitada. Dados e bot não foram alterados.')
    else:
        pasta=Path(__file__).resolve().parent
        # Lançará o mesmo script atual somente após logon do usuário.
        arquivo=registrar_inicio(pasta)
        print('Habilitado: MeuControlePC inicia após o próximo logon. Arquivo: '+str(arquivo))

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError) as exc:raise SystemExit(str(exc))
