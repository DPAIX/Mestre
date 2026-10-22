"""Inscrição EXPLÍCITA no Startup do usuário Windows (após login, não como serviço)."""
import argparse
import os
from pathlib import Path
import sys
from caminhos_instalacao import arquivo_env, diretorio_dados

NOME='MeuControlePC_inicio_ao_logar.cmd'
ASSINATURA='REM Gerenciado por MeuControlePC v2.1'

def _argumento_cmd(valor):
    texto=str(valor)
    if any(c in texto for c in ('\x00','\r','\n','"')):
        raise ValueError('Caminho de inicialização inválido.')
    # Em arquivo .cmd, %% é literal. DelayedExpansion fica desligado para !.
    return '"'+texto.replace('%','%%')+'"'

def texto_inicio(pasta=None, python=None):
    """Persiste os caminhos, sem copiar o .env ou seus valores para o atalho."""
    pasta=Path(pasta) if pasta is not None else Path(__file__).resolve().parent
    linhas=[ASSINATURA,'@echo off','setlocal DisableDelayedExpansion','chcp 65001 >nul',
            'cd /d '+_argumento_cmd(pasta)]
    if 'MEUCONTROLEPC_ENV' in os.environ:
        env=arquivo_env(pasta)
        dados=diretorio_dados(pasta)
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
    return Path(appdata)/'Microsoft'/'Windows'/'Start Menu'/'Programs'/'Startup'/NOME

def main():
    parser=argparse.ArgumentParser()
    p=parser.add_mutually_exclusive_group(required=True)
    p.add_argument('--ativar',action='store_true');p.add_argument('--desativar',action='store_true')
    args=parser.parse_args()
    arquivo=destino()
    if arquivo.exists() and ASSINATURA not in arquivo.read_text(encoding='utf-8-sig'):
        raise RuntimeError('Já existe arquivo não identificado no caminho de destino; não será modificado.')
    if args.desativar:
        arquivo.unlink(missing_ok=True)
        print('Inicialização automática desabilitada. Dados e bot não foram alterados.')
    else:
        pasta=Path(__file__).resolve().parent
        # Lançará o mesmo script atual somente após logon do usuário.
        texto=texto_inicio(pasta)
        arquivo.parent.mkdir(parents=True,exist_ok=True)
        arquivo.write_text(texto,encoding='utf-8')
        print('Habilitado: MeuControlePC inicia após o próximo logon. Arquivo: '+str(arquivo))

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError,ValueError) as exc:raise SystemExit(str(exc))
