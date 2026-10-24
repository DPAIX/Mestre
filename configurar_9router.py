"""Configuração local do cliente 9Router, sem instalar ou consultar provedores.

A interface HTTP só altera opções públicas. A chave opcional é fornecida no
console com getpass, nunca como argumento de processo, mensagem ou resposta.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import re

from caminhos_instalacao import arquivo_env
from configurar_ia_local import _atualizar_opcoes_env
from roteador_9router import URL_PADRAO, validar_modelo, validar_url

BASE=Path(__file__).resolve().parent
CHAVES_PUBLICAS=('NINE_ROUTER_HABILITADO','NINE_ROUTER_URL','NINE_ROUTER_MODEL')


def _valor_persistivel(valor,nome):
    # O leitor legado remove aspas nas bordas; recusá-las evita alterar o
    # identificador silenciosamente após reinício. Aspas internas são dados.
    if valor and (valor[0] in "\"'" or valor[-1] in "\"'"):
        raise ValueError(nome+' não pode começar ou terminar com aspas.')
    return valor


def salvar_configuracao(ativo,modelo='',url=URL_PADRAO,*,chave=None,caminho=None):
    """Persiste somente opções 9Router e atualiza o processo após o replace.

    chave=None preserva a credencial já salva. Uma string vazia a remove, ação
    disponível apenas no console local. Não existe chamada de rede nesta API.
    """
    if type(ativo) is not bool:raise ValueError('A ativação do 9Router deve ser booleana.')
    if not isinstance(modelo,str):raise ValueError('O identificador do 9Router deve ser texto.')
    modelo=_valor_persistivel(validar_modelo(modelo),'O modelo') if modelo or ativo else ''
    url=validar_url(url)
    opcoes={'NINE_ROUTER_HABILITADO':'1' if ativo else '0',
            'NINE_ROUTER_URL':url,'NINE_ROUTER_MODEL':modelo}
    if chave is not None:
        if (not isinstance(chave,str) or len(chave)>4096
                or (chave and re.fullmatch(r'[!-~]+',chave) is None)):
            raise ValueError('A chave local do 9Router tem formato inválido; não compartilhe seu conteúdo.')
        _valor_persistivel(chave,'A chave')
        opcoes['NINE_ROUTER_API_KEY']=chave
    destino=Path(caminho) if caminho is not None else arquivo_env(BASE)
    _atualizar_opcoes_env(opcoes,destino)
    os.environ.update(opcoes)
    return {'habilitado':ativo,'url':url,'modelo':modelo,
            'chave_definida':bool(os.environ.get('NINE_ROUTER_API_KEY',''))}


def _publicas_salvas(caminho):
    """Lê somente três opções públicas para o assistente interativo local."""
    if not caminho.is_file():return {}
    atuais={}
    for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
        if linha.lstrip().startswith('#') or '=' not in linha:continue
        nome,valor=linha.split('=',1)
        if nome.strip() in CHAVES_PUBLICAS:
            atuais[nome.strip()]=valor.strip().strip('\"\'')
    return atuais


def main(argv=None,caminho=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env',help='Caminho do arquivo de configuração; nenhum conteúdo será exibido.')
    parser.add_argument('--apagar-chave',action='store_true',help='Remover a chave opcional mediante confirmação local.')
    args=parser.parse_args(argv)
    destino=Path(args.env or caminho) if args.env or caminho else arquivo_env(BASE)
    try:
        atuais=_publicas_salvas(destino)
        print('9Router: configure primeiro suas contas e combos no dashboard oficial.')
        print('Este cliente pode enviar mensagens e histórico a provedores externos e consumir cota.')
        print('Nenhum provedor será consultado nesta configuração.')
        modelo=input('ID do modelo ou combo (Enter mantém o salvo): ').strip() or atuais.get('NINE_ROUTER_MODEL','')
        url=input('Base local /v1 (Enter mantém a base salva ou 127.0.0.1:20128/v1): ').strip() or atuais.get('NINE_ROUTER_URL',URL_PADRAO)
        ativo=input('Ativar o 9Router nas conversas automáticas? Digite sim para ativar: ').strip().casefold()=='sim'
        chave='' if args.apagar_chave else (getpass.getpass('Chave opcional, entrada oculta (Enter preserva a salva): ') or None)
        if input('Salvar essas opções? Digite confirmar: ').strip().casefold()!='confirmar':
            print('Configuração cancelada.');return 0
        salvar_configuracao(ativo,modelo,url,chave=chave,caminho=destino)
        print('Configuração salva sem testar conexão. Se o assistente estiver aberto, reinicie-o para recarregar a credencial.')
        return 0
    except (EOFError,KeyboardInterrupt):
        print('\nConfiguração cancelada.');return 0
    except Exception as erro:
        from multi_ia import FalhaAPI
        if isinstance(erro,(ValueError,FalhaAPI)):
            print('Configuração não concluída: '+str(erro));return 2
        if isinstance(erro,OSError):
            print('Não foi possível gravar a configuração local. Confira permissões e espaço.');return 2
        raise


if __name__=='__main__':raise SystemExit(main())
