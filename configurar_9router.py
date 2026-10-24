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


def _validar_chave(chave):
    if (not isinstance(chave,str) or len(chave)>4096
            or (chave and re.fullmatch(r'[!-~]+',chave) is None)):
        raise ValueError('A chave local do 9Router tem formato inválido; use a chave do dashboard, sem espaços ou quebras de linha.')
    return _valor_persistivel(chave,'A chave')


def _ler_opcao(prompt,validar,padrao=''):
    from multi_ia import FalhaAPI
    for _ in range(3):
        try:return validar(input(prompt).strip() or padrao)
        except (ValueError,FalhaAPI) as erro:print(str(erro))
    raise ValueError('Três entradas inválidas. A etapa continua pendente; nenhuma opção foi salva.')


def _modelo_opcional(valor):
    return _valor_persistivel(validar_modelo(valor),'O modelo') if valor else ''


def _ativacao(valor):
    if valor.casefold() not in {'','sim','nao','não','1','0'}:
        raise ValueError('Digite sim ou não para a ativação; Enter mantém o cliente inativo.')
    return valor.casefold() in {'sim','1'}


def _chave_salva_invalida(caminho):
    """Só devolve um booleano; não expõe nem retorna a credencial persistida."""
    if not caminho.is_file():return False
    for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
        if linha.lstrip().startswith('#') or '=' not in linha:continue
        nome,valor=linha.split('=',1)
        if nome.strip()=='NINE_ROUTER_API_KEY':
            try:_validar_chave(valor.strip().strip('\"\''));return False
            except ValueError:return True
    return False


def _ler_chave(destino,apagar=False):
    if apagar:
        print('A chave opcional será removida somente se você confirmar a gravação.')
        return ''
    invalida=_chave_salva_invalida(destino)
    if invalida:print('A chave salva tem formato inválido. Informe outra ou digite APAGAR na entrada oculta para removê-la.')
    for _ in range(3):
        chave=getpass.getpass('Chave opcional, entrada oculta (Enter preserva; APAGAR remove): ')
        if chave.strip().casefold()=='apagar':
            print('A chave opcional será removida somente se você confirmar a gravação.')
            return ''
        if not chave:
            if not invalida:return None
            print('Não é possível manter uma chave de formato inválido. Digite outra ou APAGAR; Ctrl+C cancela a etapa.')
            continue
        try:return _validar_chave(chave)
        except ValueError as erro:print(str(erro))
    raise ValueError('Chave não corrigida; nenhuma opção foi salva.')


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
        opcoes['NINE_ROUTER_API_KEY']=_validar_chave(chave)
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
        print('Copie o ID do catálogo/dashboard (por exemplo, um combo que você criou). Não cole uma chave neste campo.')
        modelo=_ler_opcao('ID do modelo/combo, não a chave (Enter mantém o salvo): ',_modelo_opcional,atuais.get('NINE_ROUTER_MODEL',''))
        url=_ler_opcao('Base local /v1 [Enter mantém a salva ou 127.0.0.1:20128/v1]: ',validar_url,atuais.get('NINE_ROUTER_URL',URL_PADRAO))
        ativo=_ler_opcao('Ativar o 9Router nas conversas automáticas? sim/não [não]: ',_ativacao)
        if ativo and not modelo:
            modelo=_ler_opcao('Para ativar, informe um ID de modelo/combo do dashboard (não uma chave): ',lambda v:_valor_persistivel(validar_modelo(v),'O modelo'))
        chave=_ler_chave(destino,args.apagar_chave)
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
