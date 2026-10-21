"""Inscrição EXPLÍCITA no Startup do usuário Windows (após login, não como serviço)."""
import argparse
import os
from pathlib import Path

NOME='MeuControlePC_inicio_ao_logar.cmd'
ASSINATURA='REM Gerenciado por MeuControlePC v2.1'

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
        texto=ASSINATURA+'\n@echo off\ncd /d "'+str(pasta)+'"\ncall "'+str(pasta/'iniciar_windows.bat')+'"\n'
        arquivo.parent.mkdir(parents=True,exist_ok=True)
        arquivo.write_text(texto,encoding='utf-8')
        print('Habilitado: MeuControlePC inicia após o próximo logon. Arquivo: '+str(arquivo))

if __name__=='__main__':
    try:main()
    except (OSError,RuntimeError) as exc:raise SystemExit(str(exc))
