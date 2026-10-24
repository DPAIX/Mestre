"""Configura Gemini no console local, com entrada oculta e sem testar a API."""
from __future__ import annotations
import getpass
import os
from pathlib import Path
import re
from caminhos_instalacao import arquivo_env
from configurar_ia_local import _atualizar_opcoes_env


def salvar_configuracao(modo, modelo, *, chave=None, caminho=None):
    if modo not in ('interactions','generate_content'):raise ValueError('Escolha interactions ou generate_content.')
    if not isinstance(modelo,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}',modelo):raise ValueError('Identificador de modelo Gemini inválido.')
    opcoes={'GEMINI_API_MODO':modo,'GEMINI_MODEL':modelo}
    if chave is not None:
        if not isinstance(chave,str) or not 1<=len(chave)<=256 or any(c.isspace() for c in chave):raise ValueError('Chave Gemini inválida.')
        opcoes['GEMINI_API_KEY']=chave
    _atualizar_opcoes_env(opcoes,caminho=Path(caminho) if caminho is not None else arquivo_env(Path(__file__).resolve().parent))
    return {'modo':modo,'modelo':modelo,'chave_alterada':chave is not None,'conexao_testada':False}


def main():
    print('Gemini API: Interactions para modelos e agentes. A cota da API é separada da assinatura Colab.')
    print('Nenhuma pergunta será enviada durante esta configuração.')
    modo=input('API: interactions ou generate_content [interactions]: ').strip() or 'interactions'
    modelo=input('Modelo [gemini-3.8-flash]: ').strip() or 'gemini-3.8-flash'
    chave=getpass.getpass('Chave Gemini (Enter preserva a atual): ').strip() or None
    if input('Digite SALVAR GEMINI para gravar: ').strip()!='SALVAR GEMINI':
        print('Configuração cancelada.');return 0
    salvar_configuracao(modo,modelo,chave=chave)
    print('Opções salvas. Reinicie o assistente para recarregar a configuração. Conta/cota ainda não testadas.')
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,OSError,EOFError,KeyboardInterrupt):raise SystemExit('Configuração não concluída; nenhuma credencial foi exibida.')
