"""Prepara o cliente 9Router usando a autenticação da CLI oficial no mesmo PC.

Contrato 9Router CLI 0.5.109: cli/src/cli/api/client.js, src/dashboardGuard.js,
src/app/api/keys/route.js e src/lib/db/{schema.js,paths.js}. Só a API oficial
cria uma chave dedicada. SQLite é aberto somente para leitura de metadados.
Não lê cookies, captura tela/clipboard, altera login ou testa geração.
"""
from __future__ import annotations

import hashlib
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import threading
import tempfile
import urllib.error
import urllib.request
import uuid

from caminhos_instalacao import arquivo_env
from configurar_ia_local import _atualizar_opcoes_env
from configurar_9router import _validar_chave, _valor_persistivel
from roteador_9router import URL_PADRAO, validar_modelo, validar_url

BASE = Path(__file__).resolve().parent
NOME_CHAVE = 'MeuControlePC automatico'
MAX_JSON = 4_000_000
MAX_MODELOS = 10_000
_TRAVA = threading.Lock()


class _Pendente(RuntimeError):
    """Mensagens estáticas: nunca contém resposta HTTP, chave ou caminho pessoal."""
    def __init__(self, mensagem, *, categoria=''):
        super().__init__(mensagem)
        self.categoria = categoria


def _seguro(caminho, *, existe=False, tamanho=None):
    caminho = Path(caminho)
    if not caminho.is_absolute(): raise _Pendente('Caminho local de configuração inválido.')
    for parte in (*reversed(caminho.parents), caminho):
        try: meta = parte.lstat()
        except FileNotFoundError: continue
        if (stat.S_ISLNK(meta.st_mode) or bool(getattr(meta, 'st_file_attributes', 0) &
                getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0))):
            raise _Pendente('Um caminho redirecionado foi preservado; confira a instalação local.')
    if existe:
        try: meta = caminho.lstat()
        except OSError: raise _Pendente('Recurso local do 9Router ainda não preparado.') from None
        if not stat.S_ISREG(meta.st_mode) or tamanho is not None and meta.st_size > tamanho:
            raise _Pendente('Recurso local do 9Router fora do formato esperado.')
    return caminho


def _diretorio(valor=None):
    if valor is not None: return _seguro(valor)
    appdata = os.getenv('APPDATA', '')
    if not appdata: raise _Pendente('Diretório local do 9Router indisponível nesta sessão.')
    return _seguro(Path(appdata) / '9router')


def _adquirir_trava(caminho):
    """Trava nativa liberada ao fechar o descritor, inclusive após crash."""
    _seguro(caminho)
    if caminho.exists():_seguro(caminho, existe=True, tamanho=4096)
    fd = os.open(caminho, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):raise OSError()
        if os.fstat(fd).st_size == 0:os.write(fd, b'0')
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except Exception:
        os.close(fd)
        raise _Pendente('Outra preparação 9Router está em andamento; aguarde a conclusão.') from None


def _opcoes(caminho):
    _seguro(caminho)
    if not caminho.exists(): return {}
    _seguro(caminho, existe=True, tamanho=1_000_000)
    nomes = {'NINE_ROUTER_HABILITADO', 'NINE_ROUTER_URL', 'NINE_ROUTER_MODEL'}
    saida = {}
    for linha in caminho.read_text(encoding='utf-8-sig').splitlines():
        if linha.lstrip().startswith('#') or '=' not in linha: continue
        nome, valor = linha.split('=', 1)
        if nome.strip() in nomes: saida[nome.strip()] = valor.strip().strip('\"\'')
    return saida


def _metadados(raiz):
    banco = _seguro(raiz / 'db' / 'data.sqlite', existe=True, tamanho=2_000_000_000)
    for sufixo in ('-wal', '-shm'): _seguro(Path(str(banco) + sufixo))
    try:
        with closing(sqlite3.connect(banco.as_uri() + '?mode=ro', uri=True, timeout=1)) as db:
            db.execute('PRAGMA query_only=ON')
            db.execute('PRAGMA trusted_schema=OFF')
            db.set_progress_handler(lambda: 1, 200_000)
            tabelas = {r[0]: r[1] for r in db.execute("SELECT name,type FROM sqlite_master WHERE name IN ('apiKeys','combos','providerConnections','_meta')")}
            requisitos = {'apiKeys': {'id','key','name','isActive','accessRestricted','accessAllow'},
                          'combos': {'id','name','kind','models'},
                          'providerConnections': {'id','provider','isActive','authType','data'},
                          '_meta': {'key','value'}}
            for nome, colunas in requisitos.items():
                if tabelas.get(nome) != 'table' or not colunas <= {r[1] for r in db.execute('PRAGMA table_info(' + nome + ')')}:
                    raise _Pendente('O banco local usa outro esquema; a configuração foi preservada.')
            versao = db.execute("SELECT value FROM _meta WHERE key='schemaVersion'").fetchall()
            if versao != [('2',)]:
                raise _Pendente('O banco local usa outra versão de esquema; a configuração foi preservada.')
            combos = []
            for nome, tipo, modelos in db.execute('SELECT name,kind,CASE WHEN length(CAST(models AS BLOB))<=1000000 THEN models ELSE NULL END FROM combos LIMIT 201'):
                if len(combos) >= 200: raise _Pendente('Catálogo local de combos excede o limite de preparação.')
                if tipo not in (None, '', 'llm'): continue
                try:
                    nome = _valor_persistivel(validar_modelo(nome), 'O modelo')
                    itens = json.loads(modelos)
                    if not isinstance(itens, list) or not itens: continue
                except Exception: continue
                combos.append(nome)
            ativos = db.execute('SELECT COUNT(*) FROM providerConnections WHERE isActive=1').fetchone()[0]
            autenticados = [r[0] for r in db.execute("""SELECT provider FROM providerConnections
                WHERE isActive=1 AND CASE WHEN length(CAST(data AS BLOB))<=1000000 AND json_valid(data)
                THEN (json_type(data,'$.apiKey')='text' AND trim(json_extract(data,'$.apiKey'))<>'')
                  OR (json_type(data,'$.accessToken')='text' AND trim(json_extract(data,'$.accessToken'))<>'')
                ELSE 0 END LIMIT 1001""")]
            if len(autenticados)>1000:raise _Pendente('Conexões locais excedem o limite de preparação.')
            return {'combos': list(dict.fromkeys(combos)), 'provedores_ativos': ativos, 'provedores_com_credencial':autenticados}
    except _Pendente: raise
    except (sqlite3.Error, OSError, ValueError, UnicodeError):
        raise _Pendente('Não foi possível ler metadados do 9Router; banco preservado.') from None


def _selecionar(modelo, combos):
    if modelo:
        try: return _valor_persistivel(validar_modelo(modelo), 'O modelo')
        except Exception: raise _Pendente('Modelo configurado inválido; escolha um ID de conversa no catálogo local.') from None
    nomeados = [c for c in combos if c.casefold() in {'assistente', 'meucontrolepc'}]
    if len(nomeados) == 1: return nomeados[0]
    if len(combos) == 1: return combos[0]
    return ''


def _recomendado(modelos, provedores):
    """Escolha opcional, determinística e compacta em conexões com credencial.

    Mapeamentos confirmados em open-sse/providers/registry/{id}.js. A presença
    de credencial e catálogo não comprova cota/autenticação/geração nem gratuidade.
    IDs de provedores desconhecidos ficam para escolha no painel.
    """
    aliases = {'gemini-cli':'gc', 'gemini':'gemini', 'antigravity':'ag',
               'openai':'openai', 'codex':'cx', 'claude':'cc'}
    prefixos = {aliases[p] for p in provedores if p in aliases}
    candidatos = []
    for ident in modelos:
        prefixo, _, nome = ident.partition('/')
        nome = nome.casefold()
        if prefixo not in prefixos:continue
        if any(p in nome for p in ('tts','speech','embedding','image','video','audio')):continue
        compacto = 0 if 'flash' in nome else 1 if 'mini' in nome or 'nano' in nome else 2 if 'haiku' in nome else None
        if compacto is None:continue
        versao = re.search(r'(?:gemini-|gpt-|claude-)(\d+)(?:[.-](\d+))?', nome)
        numeros = tuple(-int(n or 0) for n in versao.groups()) if versao else (0, 0)
        candidatos.append(((compacto, 1 if 'preview' in nome else 0, numeros, ident), ident))
    return min(candidatos)[1] if candidatos else ''


def _resultado(*, modelo='', combos=None, modelos=None, pendencias=None,
               alterado=False, configurado=False, chave_configurada=False):
    return {'estado': 'configurado' if configurado else 'pendente',
            'configurado': configurado, 'alterado': alterado,
            'modelo': modelo, 'combos': combos or [], 'modelos': modelos or [],
            'pendencias': pendencias or [], 'chave_configurada': chave_configurada,
            'geracao_testada': False}


def planejar_gateway(*, caminho_env=None, diretorio_gateway=None, modelo=None):
    """Lê só opções públicas/metadados locais; não consulta APIs nem retorna chaves."""
    try:
        caminho = Path(caminho_env) if caminho_env is not None else arquivo_env(BASE)
        opcoes = _opcoes(caminho); raiz = _diretorio(diretorio_gateway)
        meta = _metadados(raiz)
        selecionado = _selecionar(modelo if modelo is not None else opcoes.get('NINE_ROUTER_MODEL', ''), meta['combos'])
        validar_url(opcoes.get('NINE_ROUTER_URL', URL_PADRAO))
        pendencias = []
        if not meta['provedores_ativos']: pendencias.append('Conecte um provedor de conversa no dashboard 9Router.')
        if not selecionado: pendencias.append('Escolha um modelo/combinação de conversa; nenhuma opção paga foi escolhida ao acaso.')
        if not all((raiz / n).is_file() for n in ('machine-id', 'auth/cli-secret')):
            pendencias.append('Abra o 9Router para preparar a autenticação oficial da CLI local.')
        return _resultado(modelo=selecionado, combos=meta['combos'], pendencias=pendencias)
    except Exception:
        return _resultado(pendencias=['Preparação local 9Router pendente: confira instalação, caminhos e esquema do banco.'])


def _token_cli(raiz):
    # Algoritmo da própria CLI. Não criar/substituir esses arquivos nem alterar login.
    valores = []
    for nome in ('machine-id', 'auth/cli-secret'):
        arq = _seguro(raiz / nome, existe=True, tamanho=4096)
        valor = arq.read_text(encoding='utf-8').strip()
        if not valor or any(ord(c) < 32 for c in valor):
            raise _Pendente('Autenticação oficial da CLI local ainda não preparada.')
        valores.append(valor)
    return hashlib.sha256((valores[0] + '9r-cli-auth' + valores[1]).encode()).hexdigest()[:16]


class _SemRedirecionamento(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None


def _json_estrito(bruto):
    def pares(itens):
        obj = {}
        for chave, valor in itens:
            if chave in obj: raise ValueError('duplicado')
            obj[chave] = valor
        return obj
    return json.loads(bruto.decode('utf-8'), object_pairs_hook=pares,
                      parse_constant=lambda _valor: (_ for _ in ()).throw(ValueError('constante')))


def _requisicao(url, token, rota, *, corpo=None, chave=''):
    # validar_url remove a possibilidade de host remoto, credencial na URL e query.
    base = validar_url(url)[:-3]
    if rota not in ('/api/keys', '/v1/models'): raise _Pendente('Operação de preparação não permitida.')
    cabecalhos = {'Content-Type': 'application/json', 'x-9r-cli-token': token}
    if chave: cabecalhos['Authorization'] = 'Bearer ' + chave
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(base + rota, data=dados, headers=cabecalhos,
                                 method='POST' if corpo is not None else 'GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _SemRedirecionamento())
    try:
        with opener.open(req, timeout=4) as resposta:
            bruto = resposta.read(MAX_JSON + 1)
        if len(bruto) > MAX_JSON: raise _Pendente('Metadados locais excedem o limite de preparação.')
        obj = _json_estrito(bruto)
        if not isinstance(obj, dict): raise _Pendente('Resposta local fora do formato esperado.')
        return obj
    except urllib.error.HTTPError as erro:
        codigo = erro.code; erro.close()
        if codigo in (401, 403): raise _Pendente('A API 9Router pede autenticação administrativa; conclua o login na interface local.', categoria='autenticacao') from None
        raise _Pendente('A API local não confirmou a operação. Nenhuma tentativa automática foi repetida.') from None
    except _Pendente: raise
    except Exception:
        raise _Pendente('A resposta da operação local não foi confirmada. Confira o dashboard antes de repetir.') from None


def _id_chave(valor):
    try:
        if not isinstance(valor, str) or str(uuid.UUID(valor)) != valor: raise ValueError()
        return valor
    except (ValueError, TypeError, AttributeError):
        raise _Pendente('O identificador da chave dedicada precisa ser conferido localmente.') from None


def _recibo(caminho):
    _seguro(caminho)
    if not caminho.exists():return None
    _seguro(caminho, existe=True, tamanho=4096)
    try:
        dados = _json_estrito(caminho.read_bytes())
        if dados.get('versao') != 1 or dados.get('nome') != NOME_CHAVE:raise ValueError()
        return _id_chave(dados.get('id'))
    except Exception:
        raise _Pendente('O comprovante local da chave dedicada precisa ser conferido.') from None


def _salvar_recibo(caminho, ident):
    # Somente UUID e nome público; permite reconhecer a chave criada pelo assistente.
    _seguro(caminho)
    fd, temporario = tempfile.mkstemp(prefix='.9router-recibo.', suffix='.tmp', dir=caminho.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as arq:
            json.dump({'versao': 1, 'nome': NOME_CHAVE, 'id': _id_chave(ident)}, arq)
            arq.flush();os.fsync(arq.fileno())
        os.replace(temporario, caminho)
    finally:Path(temporario).unlink(missing_ok=True)


def _chave_dedicada(keys, *, recibo=None, criacao_pendente=False):
    if not isinstance(keys, list) or len(keys) > 1000: raise _Pendente('Lista de chaves fora do formato esperado.')
    candidatas = [k for k in keys if isinstance(k, dict) and k.get('name') == NOME_CHAVE and k.get('isActive') is True]
    if len(candidatas) > 1: raise _Pendente('Há mais de uma chave dedicada; escolha a chave ativa pela interface local.')
    if not candidatas: return None
    ident = _id_chave(candidatas[0].get('id'))
    if recibo != ident and not (recibo is None and criacao_pendente):
        raise _Pendente('Já existe uma chave com o nome dedicado, mas sem comprovante desta preparação. Confira-a na interface local.')
    try:
        chave = _validar_chave(candidatas[0]['key'])
        return (ident, chave) if chave else None
    except Exception: raise _Pendente('A chave dedicada precisa ser conferida no dashboard local.') from None


def configurar_gateway(*, caminho_env=None, diretorio_gateway=None, modelo=None, autorizado=False, selecionar_recomendado=False):
    """Autorização local permite metadados e uma chave dedicada, nunca geração.

    Reutiliza somente a chave com nome fixo criada por esta preparação; as chaves
    Default Key/Assistente vistas em capturas nunca são reutilizadas. A API
    oficial cria a chave; o banco SQLite não recebe SQL de escrita.
    """
    if type(selecionar_recomendado) is not bool:raise ValueError('A seleção recomendada deve ser booleana.')
    if autorizado is not True: raise PermissionError('Autorize a preparação local de credenciais do 9Router.')
    if not _TRAVA.acquire(blocking=False): return _resultado(pendencias=['Uma preparação 9Router já está em andamento.'])
    publico = _resultado()
    fd_trava = None
    try:
        caminho = Path(caminho_env) if caminho_env is not None else arquivo_env(BASE)
        _seguro(caminho)
        opcoes = _opcoes(caminho); raiz = _diretorio(diretorio_gateway)
        meta = _metadados(raiz)
        selecionado = _selecionar(modelo if modelo is not None else opcoes.get('NINE_ROUTER_MODEL', ''), meta['combos'])
        publico.update(modelo=selecionado, combos=meta['combos'])
        if not meta['provedores_ativos']: raise _Pendente('Conecte um provedor de conversa no dashboard 9Router.')
        # Compartilhada também por instalações com arquivos .env distintos.
        fd_trava = _adquirir_trava(raiz / '.meucontrolepc_9router_configurando.lock')
        caminho.parent.mkdir(parents=True, exist_ok=True)
        url = validar_url(opcoes.get('NINE_ROUTER_URL', URL_PADRAO)); token = _token_cli(raiz)
        marcador = _seguro(caminho.parent / '.meucontrolepc_9router_chave_pendente.json')
        comprovante = _seguro(caminho.parent / '.meucontrolepc_9router_chave.json')
        dedicada = _chave_dedicada(_requisicao(url, token, '/api/keys').get('keys'),
                                  recibo=_recibo(comprovante), criacao_pendente=marcador.exists())
        if dedicada is None:
            if marcador.exists(): raise _Pendente('Uma criação anterior ficou sem confirmação; confira as chaves no dashboard antes de iniciar outra.')
            # Arquivo sem segredo, criado antes do POST para impedir repetição após timeout.
            caminho.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(marcador, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, 'w', encoding='utf-8') as arq:
                arq.write('{"versao":1,"estado":"criacao_sem_confirmacao"}'); arq.flush(); os.fsync(arq.fileno())
            try:
                criado = _requisicao(url, token, '/api/keys', corpo={'name': NOME_CHAVE})
            except _Pendente as erro:
                # O authguard recusou antes da criação; login pode ser retomado.
                if erro.categoria == 'autenticacao':marcador.unlink(missing_ok=True)
                raise
            if criado.get('name') != NOME_CHAVE: raise _Pendente('A API não confirmou a chave dedicada esperada.')
            try: chave = _validar_chave(criado.get('key'))
            except Exception: raise _Pendente('A API não devolveu uma chave dedicada válida.') from None
            if not chave: raise _Pendente('A API não devolveu uma chave dedicada válida.')
            ident = _id_chave(criado.get('id'))
        else:ident, chave = dedicada
        _salvar_recibo(comprovante, ident)
        # Só opções desta integração são gravadas; nenhuma chave é retornada.
        _atualizar_opcoes_env({'NINE_ROUTER_API_KEY': chave, 'NINE_ROUTER_URL': url}, caminho=caminho)
        os.environ.update({'NINE_ROUTER_API_KEY': chave, 'NINE_ROUTER_URL': url})
        publico.update(alterado=True, chave_configurada=True)
        if marcador.exists(): marcador.unlink()
        catalogo = _requisicao(url, token, '/v1/models', chave=chave).get('data')
        if not isinstance(catalogo, list) or len(catalogo) > MAX_MODELOS: raise _Pendente('Catálogo de conversa excede o limite esperado.')
        modelos = []
        for item in catalogo:
            if not isinstance(item, dict): raise _Pendente('Catálogo de conversa inválido.')
            if item.get('kind', 'llm') != 'llm': continue
            try: ident = _valor_persistivel(validar_modelo(item.get('id')), 'O modelo')
            except Exception: continue
            if ident not in modelos: modelos.append(ident)
        publico['modelos'] = modelos[:1000]
        if not selecionado and selecionar_recomendado:
            selecionado = _recomendado(modelos, meta['provedores_com_credencial'])
            if selecionado:publico.update(modelo=selecionado,modelo_origem='recomendado_compacto')
        if not selecionado: raise _Pendente('A chave dedicada foi preparada. Escolha um ID de conversa no catálogo; nenhuma opção paga foi escolhida ao acaso.')
        if selecionado not in modelos: raise _Pendente('O modelo configurado não está no catálogo disponível à chave. A escolha anterior foi preservada.')
        _atualizar_opcoes_env({'NINE_ROUTER_HABILITADO': '1', 'NINE_ROUTER_MODEL': selecionado}, caminho=caminho)
        os.environ.update({'NINE_ROUTER_HABILITADO': '1', 'NINE_ROUTER_MODEL': selecionado})
        publico.update(estado='configurado', configurado=True)
        return publico
    except _Pendente as erro:
        publico['pendencias'] = [str(erro)]
        return publico
    except Exception:
        publico['pendencias'] = ['Preparação 9Router não concluída; confira o serviço e as permissões locais. Nenhum segredo foi exibido.']
        return publico
    finally:
        if fd_trava is not None:os.close(fd_trava)
        _TRAVA.release()
