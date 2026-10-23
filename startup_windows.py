"""Inscrição EXPLÍCITA no Startup do usuário Windows (após login, não como serviço)."""
import argparse
import os
from pathlib import Path
import sys
import tempfile
from caminhos_instalacao import arquivo_env, diretorio_dados

NOME='MeuControlePC_inicio_ao_logar.cmd'
ASSINATURA='REM Gerenciado por MeuControlePC v2.1'

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
        linhas.append(_argumento_cmd(pasta/'iniciar_windows.bat'))
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
    arquivo=Path(arquivo) if arquivo is not None else destino()
    if arquivo.is_symlink():raise RuntimeError('O atalho de início é um link; não será modificado.')
    if arquivo.exists():
        texto=arquivo.read_text(encoding='utf-8-sig')
        if not texto.splitlines() or texto.splitlines()[0]!=ASSINATURA:
            raise RuntimeError('Já existe arquivo não identificado no caminho de destino; não será modificado.')
    return arquivo


def registrar_inicio(pasta=None,python=None,*,arquivo_env_externo=None,dados=None):
    """Configuração já autorizada pelo usuário; grava uma única entrada atomicamente."""
    arquivo=conferir_destino()
    texto=texto_inicio(pasta,python,arquivo_env_externo=arquivo_env_externo,dados=dados)
    if arquivo.exists() and arquivo.read_text(encoding='utf-8-sig')==texto:return arquivo
    arquivo.parent.mkdir(parents=True,exist_ok=True)
    fd,temporario=tempfile.mkstemp(prefix='.'+NOME+'.',suffix='.tmp',dir=str(arquivo.parent))
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='') as fp:
            fp.write(texto);fp.flush();os.fsync(fp.fileno())
        os.replace(temporario,arquivo)
    finally:Path(temporario).unlink(missing_ok=True)
    return arquivo

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
