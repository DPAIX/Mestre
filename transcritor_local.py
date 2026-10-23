"""Whisper local em CPU; áudio e credenciais não são enviados à rede.

Somente preparar_modelo pode baixar os pesos públicos. Cada transcrição usa
um processo com prazo total, cache já preparado e rede do hub desativada.
"""
from __future__ import annotations

import argparse
import contextlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading

from caminhos_instalacao import arquivo_env

BASE = Path(__file__).resolve().parent
MODELOS = frozenset({'tiny', 'base', 'small'})
LIMITE_AUDIO = 8_000_000
LIMITE_TEXTO = 8000
LIMITE_SEGMENTOS = 600
LIMITE_DURACAO = 180
TIMEOUT_TRANSCRICAO = 120
TIMEOUT_PREPARACAO = 600
EXTENSOES = {
    'audio/ogg': '.ogg', 'audio/mpeg': '.mp3', 'audio/mp3': '.mp3',
    'audio/mp4': '.m4a', 'audio/wav': '.wav', 'audio/x-wav': '.wav',
    'audio/flac': '.flac', 'audio/webm': '.webm', 'audio/aac': '.aac',
}
_TRAVA = threading.Lock()
_ERROS = {
    'dependencia': ('Instalação do transcritor local incompleta. Prepare os componentes pela ativação automática do assistente.', 'configuracao'),
    'modelo_ausente': ('O modelo de voz local ainda não foi preparado. Conclua a ativação automática do assistente.', 'configuracao'),
    'audio_longo': ('O áudio excede três minutos. Envie uma gravação menor.', 'entrada'),
    'sem_fala': ('Não foi reconhecida fala no áudio. Grave novamente ou envie texto.', 'resposta_invalida'),
    'transcricao_longa': ('A transcrição excedeu o limite. Envie um áudio menor; nenhum pedido parcial foi encaminhado.', 'entrada'),
    'audio_invalido': ('Não foi possível decodificar o áudio localmente. Envie uma gravação de voz válida ou texto.', 'entrada'),
    'download': ('Não foi possível preparar o modelo de voz local. Confira conexão e espaço na instalação externa e tente a ativação novamente.', 'configuracao'),
    'motor': ('O transcritor local não concluiu a leitura. Envie uma gravação menor ou texto.', 'temporario'),
}


class FalhaTranscritorLocal(RuntimeError):
    def __init__(self, mensagem, categoria='temporario'):
        super().__init__(mensagem)
        self.categoria = categoria


def nome_modelo():
    modelo = os.getenv('VOZ_MODELO_LOCAL', 'base').strip().casefold()
    if modelo not in MODELOS:
        raise FalhaTranscritorLocal('VOZ_MODELO_LOCAL deve ser tiny, base ou small.', 'configuracao')
    return modelo


def diretorio_cache():
    """Calcula caminhos públicos; nunca abre o arquivo .env."""
    try:
        configuracao = arquivo_env(BASE).resolve().parent
    except (OSError, ValueError):
        raise FalhaTranscritorLocal('O caminho da configuração externa de voz é inválido.', 'configuracao') from None
    if configuracao == BASE or configuracao.is_relative_to(BASE):
        publico = os.getenv('LOCALAPPDATA')
        configuracao = Path(publico) / 'MeuControlePC' if publico else Path.home() / '.cache' / 'MeuControlePC'
    cache = (configuracao / 'modelos_voz').resolve()
    if cache == BASE or cache.is_relative_to(BASE):
        raise FalhaTranscritorLocal('O cache de voz precisa ficar fora da pasta do código.', 'configuracao')
    return cache


def _tem_dependencia():
    try:
        return importlib.util.find_spec('faster_whisper') is not None
    except (ImportError, ValueError):
        return False


def _modelo_preparado(pasta):
    essenciais = ('config.json', 'model.bin', 'tokenizer.json')
    try:
        return (all((pasta / nome).is_file() and (pasta / nome).stat().st_size > 0 for nome in essenciais)
                and any((pasta / nome).is_file() and (pasta / nome).stat().st_size > 0
                        for nome in ('vocabulary.json', 'vocabulary.txt')))
    except OSError:
        return False


def verificar_disponibilidade():
    """Pré-checagem sem importação do motor, inferência ou download."""
    if _TRAVA.locked():
        raise FalhaTranscritorLocal('Já há uma preparação ou transcrição local em andamento. Aguarde a conclusão.', 'ocupado')
    if not _tem_dependencia():
        raise FalhaTranscritorLocal(*_ERROS['dependencia'])
    if not _modelo_preparado(diretorio_cache() / nome_modelo()):
        raise FalhaTranscritorLocal(*_ERROS['modelo_ausente'])


def _ambiente_worker(cache, *, preparar):
    publicas = {'PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
                'LANG', 'LC_ALL', 'USERPROFILE', 'HOME', 'HOMEDRIVE', 'HOMEPATH',
                'LOCALAPPDATA', 'APPDATA', 'SYSTEMDRIVE'}
    ambiente = {k: v for k, v in os.environ.items() if k.upper() in publicas}
    if preparar:
        rede={'HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE'}
        ambiente.update({k:v for k,v in os.environ.items() if k.upper() in rede})
    ambiente.update({
        'PYTHONIOENCODING': 'utf-8', 'HF_HOME': str(cache / '.hub_runtime'),
        'HF_HUB_DISABLE_TELEMETRY': '1', 'HF_HUB_DISABLE_IMPLICIT_TOKEN': '1',
        'HF_HUB_DISABLE_PROGRESS_BARS': '1', 'HF_HUB_ETAG_TIMEOUT': '15',
        'HF_HUB_DOWNLOAD_TIMEOUT': '20', 'HF_HUB_OFFLINE': '0' if preparar else '1',
    })
    return ambiente


def _executar_worker(operacao, modelo, cache, audio=None):
    comando = [sys.executable, str(Path(__file__).resolve()), '--worker', operacao,
               '--modelo', modelo, '--cache', str(cache)]
    if audio is not None:
        comando.extend(['--audio', str(audio)])
    preparar = operacao == 'preparar'
    try:
        retorno = subprocess.run(
            comando, env=_ambiente_worker(cache, preparar=preparar), shell=False,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding='utf-8', errors='replace', check=False,
            timeout=TIMEOUT_PREPARACAO if preparar else TIMEOUT_TRANSCRICAO,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
    except subprocess.TimeoutExpired:
        limite = TIMEOUT_PREPARACAO if preparar else TIMEOUT_TRANSCRICAO
        raise FalhaTranscritorLocal(f'O transcritor local excedeu o prazo total de {limite} segundos. Nenhuma tentativa foi repetida.', 'timeout') from None
    except OSError:
        raise FalhaTranscritorLocal('Não foi possível iniciar o transcritor local. Confira a instalação Python.', 'configuracao') from None
    try:
        if not isinstance(retorno.stdout, str) or len(retorno.stdout) > 40000:
            raise ValueError
        resultado = json.loads(retorno.stdout)
        if not isinstance(resultado, dict) or not isinstance(resultado.get('ok'), bool):
            raise ValueError
        if set(resultado) - {'ok', 'texto', 'erro'}:
            raise ValueError
        if not resultado['ok']:
            mensagem, categoria = _ERROS.get(resultado.get('erro'), _ERROS['motor'])
            raise FalhaTranscritorLocal(mensagem, categoria)
        if retorno.returncode != 0:
            raise ValueError
        if preparar:
            return None
        texto = resultado.get('texto')
        if not isinstance(texto, str) or not texto.strip() or len(texto) > LIMITE_TEXTO:
            raise ValueError
        return texto.strip()
    except (ValueError, TypeError, UnicodeError):
        raise FalhaTranscritorLocal('O transcritor local retornou uma resposta inválida; nenhum pedido foi encaminhado.', 'resposta_invalida') from None


def preparar_modelo():
    """Prepara uma vez os pesos públicos; só o instalador chama este helper."""
    modelo = nome_modelo()
    cache = diretorio_cache()
    if not _tem_dependencia():
        raise FalhaTranscritorLocal(*_ERROS['dependencia'])
    if not _TRAVA.acquire(blocking=False):
        raise FalhaTranscritorLocal('Já há uma preparação ou transcrição local em andamento. Aguarde a conclusão.', 'ocupado')
    try:
        pasta = cache / modelo
        if _modelo_preparado(pasta):
            return pasta
        cache.mkdir(parents=True, exist_ok=True)
        _executar_worker('preparar', modelo, cache)
        if not _modelo_preparado(pasta):
            raise FalhaTranscritorLocal(*_ERROS['download'])
        return pasta
    except OSError:
        raise FalhaTranscritorLocal('Não foi possível gravar o modelo de voz na instalação externa. Confira permissões e espaço livre.', 'configuracao') from None
    finally:
        _TRAVA.release()


def transcrever_audio(dados, mime_type):
    """Uma transcrição em CPU de modelo já preparado, com prazo total de 120 s."""
    if not isinstance(dados, bytes) or not dados or len(dados) > LIMITE_AUDIO:
        raise ValueError('O áudio deve ter conteúdo e no máximo 8 MB.')
    if mime_type not in EXTENSOES:
        raise ValueError('Formato de áudio não suportado.')
    modelo = nome_modelo()
    cache = diretorio_cache()
    if not _tem_dependencia():
        raise FalhaTranscritorLocal(*_ERROS['dependencia'])
    if not _TRAVA.acquire(blocking=False):
        raise FalhaTranscritorLocal('Já há uma transcrição local em andamento. Aguarde a conclusão.', 'ocupado')
    temporario = None
    try:
        if not _modelo_preparado(cache / modelo):
            raise FalhaTranscritorLocal(*_ERROS['modelo_ausente'])
        with tempfile.NamedTemporaryFile(prefix='.voz-', suffix=EXTENSOES[mime_type],
                                         dir=cache, delete=False) as arquivo:
            temporario = Path(arquivo.name)
            arquivo.write(dados)
        return _executar_worker('transcrever', modelo, cache, temporario)
    except OSError:
        raise FalhaTranscritorLocal('Não foi possível preparar o áudio temporário na instalação externa.', 'configuracao') from None
    finally:
        try:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
        except OSError:
            raise FalhaTranscritorLocal('Não foi possível remover o áudio temporário local. Confira as permissões da pasta de modelos de voz.', 'configuracao') from None
        finally:
            _TRAVA.release()


def _decodificar_limitado(caminho):
    import av
    import numpy as np
    blocos = []
    amostras = 0
    with av.open(str(caminho),options={'protocol_whitelist':'file,pipe'}) as recipiente:
        reamostrar = av.AudioResampler(format='s16', layout='mono', rate=16000)
        for quadro in recipiente.decode(audio=0):
            for convertido in reamostrar.resample(quadro):
                amostras += convertido.samples
                if amostras > 16000 * LIMITE_DURACAO:
                    raise FalhaTranscritorLocal('audio_longo')
                blocos.append(convertido.to_ndarray().flatten().astype(np.float32) / 32768.0)
        for convertido in reamostrar.resample(None):
            amostras += convertido.samples
            if amostras > 16000 * LIMITE_DURACAO:
                raise FalhaTranscritorLocal('audio_longo')
            blocos.append(convertido.to_ndarray().flatten().astype(np.float32) / 32768.0)
    if not blocos or not amostras:
        raise FalhaTranscritorLocal('sem_fala')
    return np.concatenate(blocos)


def _worker_preparar(modelo, cache):
    try:
        from huggingface_hub import snapshot_download
        # O helper antigo de faster-whisper envia local_dir_use_symlinks,
        # argumento removido no Hub 1+. Use a API pública compatível.
        snapshot_download('Systran/faster-whisper-'+modelo,local_dir=str(cache/modelo),
                          allow_patterns=['config.json','preprocessor_config.json','model.bin','tokenizer.json','vocabulary.*'],
                          local_files_only=False,token=False,max_workers=4)
        return {'ok': _modelo_preparado(cache / modelo), 'erro': 'download'}
    except ImportError:
        return {'ok': False, 'erro': 'dependencia'}
    except Exception:
        return {'ok': False, 'erro': 'download'}


def _worker_transcrever(modelo, cache, audio):
    if not _modelo_preparado(cache / modelo):
        return {'ok': False, 'erro': 'modelo_ausente'}
    try:
        from faster_whisper import WhisperModel
        try:
            amostras = _decodificar_limitado(audio)
        except FalhaTranscritorLocal as erro:
            return {'ok': False, 'erro': str(erro)}
        except Exception:
            return {'ok': False, 'erro': 'audio_invalido'}
        motor = WhisperModel(str(cache / modelo), device='cpu', compute_type='int8',
                             cpu_threads=min(4, os.cpu_count() or 1), num_workers=1,
                             local_files_only=True)
        segmentos, _ = motor.transcribe(amostras, language='pt', beam_size=1, best_of=1,
                                        temperature=0, condition_on_previous_text=False,
                                        vad_filter=True, vad_parameters={'min_silence_duration_ms': 500})
        partes = []
        tamanho = 0
        for indice, segmento in enumerate(segmentos):
            if indice >= LIMITE_SEGMENTOS:
                return {'ok': False, 'erro': 'transcricao_longa'}
            texto = getattr(segmento, 'text', None)
            if not isinstance(texto, str):
                return {'ok': False, 'erro': 'motor'}
            texto = texto.strip()
            tamanho += len(texto) + 1
            if tamanho > LIMITE_TEXTO:
                return {'ok': False, 'erro': 'transcricao_longa'}
            if texto:
                partes.append(texto)
        texto = ' '.join(partes)
        return {'ok': True, 'texto': texto} if texto else {'ok': False, 'erro': 'sem_fala'}
    except ImportError:
        return {'ok': False, 'erro': 'dependencia'}
    except Exception:
        return {'ok': False, 'erro': 'motor'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker', choices=('preparar', 'transcrever'), required=True)
    parser.add_argument('--modelo', choices=sorted(MODELOS), required=True)
    parser.add_argument('--cache', required=True)
    parser.add_argument('--audio')
    args = parser.parse_args(argv)
    cache = Path(args.cache)
    if not cache.is_absolute() or cache.resolve().is_relative_to(BASE):
        resultado = {'ok': False, 'erro': 'motor'}
    elif args.worker == 'transcrever' and (not args.audio or not Path(args.audio).is_absolute()):
        resultado = {'ok': False, 'erro': 'audio_invalido'}
    else:
        # Bibliotecas não devem misturar diagnóstico com o protocolo JSON.
        with contextlib.redirect_stdout(sys.stderr):
            resultado = (_worker_preparar(args.modelo, cache) if args.worker == 'preparar'
                         else _worker_transcrever(args.modelo, cache, Path(args.audio)))
    print(json.dumps(resultado, ensure_ascii=True, allow_nan=False))
    return 0 if resultado.get('ok') else 2


if __name__ == '__main__':
    raise SystemExit(main())
