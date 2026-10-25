"""Implanta somente fontes públicas enumeradas e verificadas pelo pacote.

Não procura dados do usuário, não lê .env, não baixa arquivos e não controla
processos. O chamador deve manter a trava de preparação e parar o bot antes de
substituir fontes. Backups ficam fora das fontes e dos dados selecionados.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import threading
import uuid

MAX_ARQUIVOS = 1000
MAX_ARQUIVO = 8 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024
MAX_MANIFESTO = 512 * 1024
IDENTIDADE = frozenset({'assistente_pc.py', 'nucleo.py', 'caminhos_instalacao.py'})
_PRIVADOS = frozenset({'.git', '.venv', 'venv', 'dados', 'models', 'modelos',
    'modelos_voz', '__pycache__', 'backups', 'backups_codigo', 'node_modules',
    'diagnosticos_rede', '.hub_runtime'})
_TRAVA = threading.Lock()


class FalhaImplantacao(RuntimeError):
    """Falha com informação de reversão, sem conteúdo das fontes antigas."""
    def __init__(self, mensagem, *, backup=None, conflitos=()):
        super().__init__(mensagem)
        self.backup = str(backup) if backup is not None else None
        self.conflitos = tuple(conflitos)
        self.reversao_completa = not self.conflitos


def _redirecionado(meta):
    return (stat.S_ISLNK(meta.st_mode) or bool(getattr(meta, 'st_file_attributes', 0)
        & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0)))


def _sem_redirecionamento(caminho):
    """Confere os ancestrais antes de usar resolve, inclusive no Windows."""
    for parte in reversed((caminho, *caminho.parents)):
        try: meta = parte.lstat()
        except FileNotFoundError: continue
        if _redirecionado(meta):
            raise ValueError('A implantação não aceita links, junctions ou reparse points.')
        if parte != caminho and not stat.S_ISDIR(meta.st_mode):
            raise ValueError('Um ancestral da implantação não é um diretório.')
    return caminho


def _absoluto(valor, nome):
    if not isinstance(valor, (str, os.PathLike)):
        raise ValueError(nome+' deve ser um caminho absoluto.')
    texto = os.fspath(valor)
    caminho = Path(texto)
    if (not texto or not caminho.is_absolute() or '..' in caminho.parts or
            any(ord(c) < 32 for c in texto)):
        raise ValueError(nome+' deve ser um caminho absoluto sem navegação relativa.')
    _sem_redirecionamento(caminho)
    return caminho.resolve(strict=False)


def _relativo(nome):
    if (not isinstance(nome, str) or not nome or len(nome) > 240 or
            any(ord(c) < 32 or c in '\\<>:"|?*' for c in nome)):
        raise ValueError('Caminho inválido no manifesto público.')
    partes = nome.split('/')
    if any(not p or p in ('.', '..') or p.endswith((' ', '.')) for p in partes):
        raise ValueError('Caminho inválido no manifesto público.')
    if any(p.casefold() in _PRIVADOS or re.fullmatch(r'(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p, re.I)
           for p in partes):
        raise ValueError('O manifesto não pode incluir dados, ambientes, caches ou caminhos reservados.')
    rel = PurePosixPath(nome)
    if rel.is_absolute(): raise ValueError('O manifesto precisa usar caminhos relativos.')
    if nome in ('.env.exemplo', '.gitignore', '.gitattributes'):
        return nome
    arquivo = partes[-1].casefold()
    if (arquivo.startswith(('.env', 'client_secret', 'secrets', 'config_local')) or
            arquivo in {'credentials.json', 'token.json', 'token_google.json', 'config_apis.json'}):
        raise ValueError('Credenciais e configurações pessoais não pertencem ao manifesto público.')
    if any(p.startswith('.') for p in partes):
        if not (len(partes) == 3 and partes[:2] == ['.github', 'workflows']
                and rel.suffix.casefold() in ('.yml', '.yaml')):
            raise ValueError('Arquivo oculto não permitido no manifesto público.')
        return nome
    sufixo = rel.suffix.casefold()
    permitida = sufixo in ('.py', '.bat', '.md', '.html')
    permitida |= len(partes) == 1 and re.fullmatch(r'requirements(?:-[A-Za-z0-9_-]+)?\.txt', nome) is not None
    permitida |= len(partes) == 1 and sufixo == '.json' and 'manifesto' in rel.stem.casefold()
    permitida |= partes[0] == 'testes' and sufixo == '.js'
    permitida |= partes[0] in ('exemplos', 'dados_iniciais') and sufixo == '.json'
    permitida |= partes[0] == 'exemplos' and sufixo == '.ipynb'
    if not permitida:
        raise ValueError('O manifesto inclui um tipo de arquivo não permitido.')
    return nome


def _pares_unicos(pares):
    resultado = {}
    for nome, valor in pares:
        if nome in resultado: raise ValueError('O manifesto contém campos duplicados.')
        resultado[nome] = valor
    return resultado


def _manifesto(valor):
    if not isinstance(valor, dict): raise ValueError('Use um manifesto público de fontes e hashes SHA256.')
    if set(valor) == {'versao', 'arquivos'}:
        if valor['versao'] != 1: raise ValueError('Versão do manifesto público não suportada.')
        valor = valor['arquivos']
    if not isinstance(valor, dict) or not 1 <= len(valor) <= MAX_ARQUIVOS:
        raise ValueError('Quantidade de fontes inválida no manifesto público.')
    arquivos = {}; nomes = set()
    for nome, sha in valor.items():
        nome = _relativo(nome)
        if nome.casefold() in nomes:
            raise ValueError('O manifesto contém caminhos equivalentes no Windows.')
        if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', sha):
            raise ValueError('Hash SHA256 inválido no manifesto público.')
        nomes.add(nome.casefold()); arquivos[nome] = sha.lower()
    if not IDENTIDADE.issubset(arquivos):
        raise ValueError('O pacote não contém a identidade completa do assistente.')
    return dict(sorted(arquivos.items()))


def _ler_regular(arquivo, limite=MAX_ARQUIVO):
    _sem_redirecionamento(arquivo)
    meta = arquivo.lstat()
    if not stat.S_ISREG(meta.st_mode) or meta.st_size > limite:
        raise ValueError('Uma fonte não é arquivo regular ou excede o limite do pacote.')
    flags = os.O_RDONLY | getattr(os, 'O_BINARY', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(arquivo, flags), 'rb') as fp:
        aberto = os.fstat(fp.fileno())
        if not stat.S_ISREG(aberto.st_mode) or (meta.st_dev, meta.st_ino) != (aberto.st_dev, aberto.st_ino):
            raise ValueError('Uma fonte mudou durante a verificação.')
        conteudo = fp.read(limite + 1)
    if len(conteudo) > limite: raise ValueError('Uma fonte excede o limite do pacote.')
    return conteudo


def carregar_manifesto(arquivo):
    """Lê somente JSON público de manifesto; nunca uma configuração pessoal."""
    caminho = _absoluto(arquivo, 'Manifesto')
    if caminho.suffix.casefold() != '.json' or 'manifesto' not in caminho.stem.casefold():
        raise ValueError('Selecione o arquivo JSON de manifesto público do pacote.')
    try:
        dados = json.loads(_ler_regular(caminho, MAX_MANIFESTO).decode('utf-8-sig'),
                           object_pairs_hook=_pares_unicos)
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('O manifesto público não contém JSON válido.') from None
    return _manifesto(dados)


def planejar_implantacao(origem, destino, backup_raiz, manifesto, *, dados=None):
    """Valida caminhos/metadados e mapping já carregado, sem criar arquivos."""
    origem = _absoluto(origem, 'Origem'); destino = _absoluto(destino, 'Destino')
    backup_raiz = _absoluto(backup_raiz, 'Backup')
    if not origem.is_dir(): raise ValueError('A pasta de fontes do pacote não foi encontrada.')
    if destino.exists() and not destino.is_dir(): raise ValueError('O destino não é um diretório.')
    if backup_raiz.exists() and not backup_raiz.is_dir(): raise ValueError('O backup não é um diretório.')
    if origem != destino and (origem.is_relative_to(destino) or destino.is_relative_to(origem)):
        raise ValueError('As pastas de origem e destino não podem ficar uma dentro da outra.')
    if backup_raiz.is_relative_to(origem) or backup_raiz.is_relative_to(destino):
        raise ValueError('O backup precisa ficar fora das pastas de fontes.')
    if dados is not None and backup_raiz.is_relative_to(_absoluto(dados, 'Dados')):
        raise ValueError('O backup de código precisa ficar fora dos dados do assistente.')
    arquivos = _manifesto(manifesto)
    for nome in arquivos:
        fonte = origem.joinpath(*PurePosixPath(nome).parts)
        alvo = destino.joinpath(*PurePosixPath(nome).parts)
        _sem_redirecionamento(fonte); _sem_redirecionamento(alvo)
        if not fonte.is_file(): raise ValueError('Falta uma fonte enumerada pelo manifesto do pacote.')
        if alvo.exists() and not alvo.is_file(): raise ValueError('O destino de uma fonte está ocupado por outro tipo de item.')
    return {'origem': origem, 'destino': destino, 'backup_raiz': backup_raiz,
            'arquivos': arquivos, 'mesmo_destino': origem == destino}


def _gravar_atomico(arquivo, conteudo):
    _sem_redirecionamento(arquivo)
    arquivo.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    _sem_redirecionamento(arquivo.parent)
    fd, nome = tempfile.mkstemp(prefix='.'+arquivo.name+'.', suffix='.tmp', dir=str(arquivo.parent))
    temporario = Path(nome)
    try:
        with os.fdopen(fd, 'wb') as fp:
            fp.write(conteudo); fp.flush(); os.fsync(fp.fileno())
        _sem_redirecionamento(arquivo)
        os.replace(temporario, arquivo)
    finally: temporario.unlink(missing_ok=True)


def _atual(arquivo):
    _sem_redirecionamento(arquivo)
    try: return _ler_regular(arquivo)
    except FileNotFoundError: return None


def implantar(origem, destino, backup_raiz, manifesto, *, autorizado=False, dados=None):
    """Confere o pacote inteiro, guarda fontes anteriores e aplica com reversão.

    Um manifesto é uma verificação de integridade do pacote recebido, não uma
    assinatura de autoria. O instalador/distribuição deve fornecer esse mapping.
    Mudanças concorrentes detectadas no destino são preservadas e reportadas.
    """
    if autorizado is not True: raise PermissionError('Autorize a implantação das fontes antes de alterar a instalação.')
    if not _TRAVA.acquire(blocking=False): raise RuntimeError('Já há uma implantação de fontes em andamento neste processo.')
    try:
        if isinstance(manifesto, (str, os.PathLike)): manifesto = carregar_manifesto(manifesto)
        plano = planejar_implantacao(origem, destino, backup_raiz, manifesto, dados=dados)
        conteudos = {}; total = 0
        for nome, esperado in plano['arquivos'].items():
            conteudo = _ler_regular(plano['origem'].joinpath(*PurePosixPath(nome).parts))
            total += len(conteudo)
            if total > MAX_TOTAL: raise ValueError('As fontes excedem o limite total do pacote.')
            if hashlib.sha256(conteudo).hexdigest() != esperado:
                raise ValueError('O pacote falhou na verificação de integridade. Nenhuma fonte foi implantada.')
            conteudos[nome] = conteudo
        resultado = {'estado': 'verificado', 'origem': str(plano['origem']),
            'destino': str(plano['destino']), 'backup': None,
            'arquivos_verificados': len(conteudos), 'arquivos_alterados': 0}
        if plano['mesmo_destino']: return resultado
        anteriores = {}; alterados = []
        for nome, conteudo in conteudos.items():
            atual = _atual(plano['destino'].joinpath(*PurePosixPath(nome).parts))
            if atual != conteudo:
                anteriores[nome] = atual; alterados.append(nome)
                total += len(atual or b'')
                if total > MAX_TOTAL: raise ValueError('As fontes e seu backup excedem o limite total permitido.')
        if not alterados:
            resultado['estado'] = 'ja_atualizado'; return resultado
        _sem_redirecionamento(plano['backup_raiz'])
        plano['backup_raiz'].mkdir(parents=True, exist_ok=True, mode=0o700)
        backup = plano['backup_raiz'] / ('implantacao_'+uuid.uuid4().hex)
        backup.mkdir(mode=0o700, exist_ok=False)
        resultado['backup'] = str(backup)
        aplicados = []
        try:
            for nome in alterados:
                if anteriores[nome] is not None:
                    _gravar_atomico(backup/'fontes'/Path(*PurePosixPath(nome).parts), anteriores[nome])
            indice = {'versao': 1, 'novos': [n for n in alterados if anteriores[n] is None],
                      'anteriores': {n: hashlib.sha256(b).hexdigest() for n, b in anteriores.items() if b is not None},
                      'instalados': {n: plano['arquivos'][n] for n in alterados}}
            _gravar_atomico(backup/'manifesto_reversao.json', json.dumps(indice, ensure_ascii=False, indent=2).encode('utf-8'))
            for nome in alterados:
                alvo = plano['destino'].joinpath(*PurePosixPath(nome).parts)
                if _atual(alvo) != anteriores[nome]:
                    raise ValueError('Uma fonte de destino mudou; a implantação foi interrompida.')
                # Inclui o arquivo antes da chamada: uma falha na limpeza do
                # temporário pode ocorrer depois de o replace ter concluído.
                aplicados.append(nome); _gravar_atomico(alvo, conteudos[nome])
        except (OSError, ValueError, RuntimeError, KeyboardInterrupt):
            conflitos = []
            for nome in reversed(aplicados):
                alvo = plano['destino'].joinpath(*PurePosixPath(nome).parts)
                try:
                    atual = _atual(alvo)
                    if atual == anteriores[nome]: continue
                    if atual != conteudos[nome]:
                        conflitos.append(nome); continue
                    if anteriores[nome] is None: alvo.unlink()
                    else: _gravar_atomico(alvo, anteriores[nome])
                except (OSError, ValueError, RuntimeError): conflitos.append(nome)
            mensagem = ('Implantação interrompida; alterações concorrentes foram preservadas. Use o backup para conferir a reversão.'
                        if conflitos else 'Implantação interrompida; fontes já alteradas foram restauradas e o backup foi preservado.')
            raise FalhaImplantacao(mensagem, backup=backup, conflitos=conflitos) from None
        resultado.update(estado='implantado', arquivos_alterados=len(alterados))
        return resultado
    finally: _TRAVA.release()
