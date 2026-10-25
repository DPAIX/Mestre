"""Configura Gemini no console local, com entrada oculta e sem testar a API."""
from __future__ import annotations
import getpass
import os
from pathlib import Path
import re
from caminhos_instalacao import arquivo_env
from configurar_ia_local import _atualizar_opcoes_env


def _validar_modelo(modelo):
    if (not isinstance(modelo,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,119}',modelo)
            or modelo.casefold() in {'sim','nao','não','yes','no','interactions','generate_content','confirmar'}):
        raise ValueError('Este campo pede um ID de modelo, por exemplo gemini-3.8-flash; Enter usa esse padrão.')
    if re.fullmatch(r'(?:sk-[A-Za-z0-9_-]{20,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})',modelo,re.IGNORECASE):
        raise ValueError('Esse valor parece uma credencial. Informe o ID do modelo aqui e a chave somente na entrada oculta.')
    return modelo


def _escolher(prompt,validar,padrao):
    for _ in range(3):
        try:return validar(input(prompt).strip() or padrao)
        except ValueError as erro:print(str(erro))
    raise ValueError('Três entradas inválidas. A etapa continua pendente; nenhuma opção foi salva.')


def _modo(valor):
    modos={'1':'interactions','2':'generate_content','interactions':'interactions','generate_content':'generate_content'}
    if valor.casefold() not in modos:
        raise ValueError('Escolha 1 ou 2 neste campo; Enter usa 1. Não é uma pergunta de sim/não.')
    return modos[valor.casefold()]


def salvar_configuracao(modo, modelo, *, chave=None, caminho=None):
    if modo not in ('interactions','generate_content'):raise ValueError('Escolha interactions ou generate_content.')
    modelo=_validar_modelo(modelo)
    opcoes={'GEMINI_API_MODO':modo,'GEMINI_MODEL':modelo}
    if chave is not None:
        if not isinstance(chave,str) or not 1<=len(chave)<=256 or any(c.isspace() for c in chave):raise ValueError('Chave Gemini inválida.')
        opcoes['GEMINI_API_KEY']=chave
    _atualizar_opcoes_env(opcoes,caminho=Path(caminho) if caminho is not None else arquivo_env(Path(__file__).resolve().parent))
    return {'modo':modo,'modelo':modelo,'chave_alterada':chave is not None,'conexao_testada':False}


def _main_interativo():
    print('Gemini API: Interactions para modelos e agentes. A cota da API é separada da assinatura Colab.')
    print('Nenhuma pergunta será enviada durante esta configuração.')
    print('As próximas perguntas pedem opções específicas. Enter aceita o padrão; não responda sim a todos os campos.')
    modo=_escolher('API: 1 = interactions, 2 = generate_content [1]: ',_modo,'1')
    modelo=_escolher('ID do modelo, não a chave [gemini-3.8-flash]: ',_validar_modelo,'gemini-3.8-flash')
    chave=getpass.getpass('Chave Gemini (Enter preserva a atual): ').strip() or None
    if input('Digite SALVAR GEMINI para gravar: ').strip()!='SALVAR GEMINI':
        print('Configuração cancelada.');return 0
    salvar_configuracao(modo,modelo,chave=chave)
    print('Opções salvas. Reinicie o assistente para recarregar a configuração. Conta/cota ainda não testadas.')
    return 0


def main():
    try:return _main_interativo()
    except (EOFError,KeyboardInterrupt):
        print('\nConfiguração Gemini cancelada; nenhuma nova opção foi salva.');return 0
    except ValueError as erro:
        print('Configuração Gemini não concluída: '+str(erro));return 2
    except OSError:
        print('Não foi possível gravar a configuração Gemini. Confira permissões e espaço.');return 2


if __name__=='__main__':
    raise SystemExit(main())
