"""Instala bibliotecas e remove somente bytecode gerado das fontes/testes.

O fluxo de manutenção não altera Startup, configuração, dados, pesos ou fontes.
Não procura arquivos pessoais nem usa a existência de um arquivo de trava como
prova de processo ativo: mantém a trava do sistema durante a atualização.
"""
from __future__ import annotations

import argparse
from itertools import islice
from pathlib import Path
import re
import stat
import sys

from instancia_assistente import InstanciaAtiva, instancia_unica
import preparar_inicio_automatico as preparar

BASE=Path(__file__).resolve().parent
MAX_ENTRADAS=10000
_CACHE=re.compile(r'[^/\\]+\.(?:cpython-\d+|pypy[^.]*)(?:\.opt-\d+)?\.py[co]',re.I)


def _redirecionado(caminho):
    """Recusa links simbólicos, junctions e outros reparse points do Windows."""
    estado=caminho.lstat()
    return (stat.S_ISLNK(estado.st_mode) or
            bool(getattr(estado,'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0)))


def _pasta_segura(pasta,raiz):
    try:
        return (not _redirecionado(pasta) and pasta.is_dir() and
                pasta.resolve().is_relative_to(raiz))
    except OSError:
        return False


def limpar_gerados(codigo):
    """Limpa apenas caches Python conhecidos na raiz do código e em testes.

    Não há busca recursiva nem rmtree. Bytecode solto só é removido quando sua
    fonte .py existe; bytecode de __pycache__ exige o nome gerado pelo Python.
    Arquivos desconhecidos no cache são preservados, assim como links/junctions.
    """
    raiz=Path(codigo)
    if not raiz.is_absolute() or not _pasta_segura(raiz,raiz.resolve()):
        raise ValueError('A limpeza precisa da pasta absoluta de código, sem redirecionamento.')
    raiz=raiz.resolve()
    for nome in preparar.redirecionar.FONTES_NECESSARIAS:
        fonte=raiz/nome
        try:
            valida=not _redirecionado(fonte) and fonte.is_file()
        except OSError:
            valida=False
        if not valida:raise ValueError('A limpeza só é permitida na raiz completa das fontes do assistente.')
    resultado={'arquivos_removidos':0,'diretorios_removidos':0,'bytes_liberados':0,
               'ignorados':0,'limite_atingido':False}

    def remover(arquivo,pasta):
        try:
            if not _pasta_segura(pasta,raiz) or _redirecionado(arquivo) or not arquivo.is_file():
                resultado['ignorados']+=1
                return
            tamanho=arquivo.stat().st_size
            arquivo.unlink()
        except OSError:
            resultado['ignorados']+=1
            return
        resultado['arquivos_removidos']+=1
        resultado['bytes_liberados']+=tamanho

    def listar(pasta):
        try:
            arquivos=list(islice(pasta.iterdir(),MAX_ENTRADAS+1))
        except OSError:
            resultado['ignorados']+=1
            return []
        if len(arquivos)>MAX_ENTRADAS:resultado['limite_atingido']=True
        return arquivos[:MAX_ENTRADAS]

    for pasta in (raiz,raiz/'testes'):
        if not _pasta_segura(pasta,raiz):continue
        for arquivo in listar(pasta):
            if arquivo.suffix.casefold() not in ('.pyc','.pyo'):continue
            fonte=arquivo.with_suffix('.py')
            try:
                if _redirecionado(fonte) or not fonte.is_file():continue
            except OSError:
                continue
            remover(arquivo,pasta)
        cache=pasta/'__pycache__'
        if not _pasta_segura(cache,raiz):continue
        for arquivo in listar(cache):
            if _CACHE.fullmatch(arquivo.name):remover(arquivo,cache)
        try:
            if _pasta_segura(cache,raiz):
                cache.rmdir()
                resultado['diretorios_removidos']+=1
        except OSError:
            # Cache ainda não vazio ou sem permissão: preservar os demais itens.
            pass
    return resultado


def manter(codigo=None,arquivo_env_externo=None,dados=None,python=None,*,iniciar=True):
    """Manutenção completa e finita; não registra ou remove início automático."""
    if not isinstance(iniciar,bool):raise ValueError('A opção de início deve ser verdadeira ou falsa.')
    plano=preparar.planejar_preparacao(codigo,arquivo_env_externo,dados,python,incluir_google=True)
    try:
        with instancia_unica(plano['dados']):
            plano=preparar.preparar_componentes(plano,python_explicito=python is not None,incluir_google=True)
            limpeza=limpar_gerados(plano['codigo'])
    except InstanciaAtiva:
        raise RuntimeError('Encerre a janela do assistente antes da manutenção e abra atualizar_assistente.bat novamente. Nenhum processo foi encerrado.') from None
    print('Dependências instaladas e compatibilidade conferida. '+str(limpeza['arquivos_removidos'])+
          ' arquivo(s) de bytecode removido(s), '+str(limpeza['bytes_liberados'])+' byte(s) liberado(s).')
    if limpeza['ignorados'] or limpeza['limite_atingido']:
        print('Alguns itens foram preservados por tipo, limite ou acesso; nenhuma exclusão foi forçada.')
    print('Configuração, dados, modelos de voz/Ollama, fontes e início automático foram preservados.')
    processo=preparar.iniciar_assistente(plano) if iniciar else None
    return {'limpeza':limpeza,'processo':processo,'python':plano['python']}


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--codigo',default=str(BASE))
    parser.add_argument('--env',dest='arquivo_env',default=preparar.redirecionar.ENV_PADRAO)
    parser.add_argument('--dados')
    parser.add_argument('--python')
    parser.add_argument('--nao-iniciar',action='store_true')
    args=parser.parse_args(argv)
    try:
        manter(args.codigo,args.arquivo_env,args.dados,args.python,iniciar=not args.nao_iniciar)
        return 0
    except (OSError,RuntimeError,ValueError) as erro:
        print('Manutenção não concluída: '+str(erro))
        return 2
    except KeyboardInterrupt:
        print('\nManutenção interrompida. Configuração, dados e modelos foram preservados.')
        return 130


if __name__=='__main__':sys.exit(main())
