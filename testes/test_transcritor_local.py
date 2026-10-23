"""Whisper local com fixtures, sem instalar bibliotecas nem baixar pesos."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import transcritor_local as voz
import voz_assistente as despacho


class TranscritorLocalTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve();self.codigo=self.raiz/'codigo';self.codigo.mkdir()
        self.cache=self.raiz/'instalacao'/'modelos_voz'
        for alvo,valor in (('BASE',self.codigo),('_TRAVA',__import__('threading').Lock())):
            p=patch.object(voz,alvo,valor);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'MEUCONTROLEPC_ENV':str(self.cache.parent/'.env'),
                              'GEMINI_API_KEY':'fixture-segredo','HF_TOKEN':'fixture-segredo',
                              'PYTHONPATH':'fixture-segredo'},clear=True)
        p.start();self.addCleanup(p.stop)
        p=patch.object(voz,'_tem_dependencia',return_value=True);p.start();self.addCleanup(p.stop)

    def preparar_fixture(self):
        pasta=self.cache/'base';pasta.mkdir(parents=True,exist_ok=True)
        for nome in ('config.json','model.bin','tokenizer.json','vocabulary.json'):
            (pasta/nome).write_bytes(b'fixture')
        return pasta

    def test_padrao_e_base_e_cache_externo_sem_ler_env(self):
        with patch('builtins.open',side_effect=AssertionError('Sem leitura de configuração')):
            self.assertEqual(voz.nome_modelo(),'base')
            self.assertEqual(voz.diretorio_cache(),self.cache)
        self.assertFalse((self.cache.parent/'.env').exists())
        for nome in ('large','base.en','../privado',''):
            with patch.dict(os.environ,{'VOZ_MODELO_LOCAL':nome}),self.assertRaises(voz.FalhaTranscritorLocal):
                voz.nome_modelo()

    def test_cache_sem_redirecionamento_fica_fora_das_fontes(self):
        with patch.dict(os.environ,{},clear=True),patch.object(voz,'arquivo_env',return_value=self.codigo/'.env'), \
                patch.object(Path,'home',return_value=self.raiz/'usuario'):
            self.assertEqual(voz.diretorio_cache(),self.raiz/'usuario'/'.cache'/'MeuControlePC'/'modelos_voz')

    def test_prechecagem_sem_pesos_ou_dependencia_nao_abre_worker(self):
        with patch.object(voz.subprocess,'run') as run:
            with self.assertRaises(voz.FalhaTranscritorLocal):voz.verificar_disponibilidade()
            with patch.object(voz,'_tem_dependencia',return_value=False),self.assertRaises(voz.FalhaTranscritorLocal):
                voz.verificar_disponibilidade()
        run.assert_not_called()

    def test_preparacao_uma_vez_faz_somente_download_explicito(self):
        def preparar(*args):self.preparar_fixture()
        with patch.object(voz,'_executar_worker',side_effect=preparar) as worker:
            self.assertEqual(voz.preparar_modelo(),self.cache/'base')
            self.assertEqual(voz.preparar_modelo(),self.cache/'base')
        worker.assert_called_once_with('preparar','base',self.cache)

    def test_transcricao_usa_temporario_e_remove_apos_sucesso(self):
        self.preparar_fixture();vistos=[]
        def executar(op,modelo,cache,audio):
            vistos.append(audio)
            self.assertEqual((op,modelo,cache),('transcrever','base',self.cache))
            self.assertEqual(audio.read_bytes(),b'fixture-audio')
            self.assertEqual(audio.suffix,'.ogg')
            return 'Mostre minha rotina'
        with patch.object(voz,'_executar_worker',side_effect=executar):
            self.assertEqual(voz.transcrever_audio(b'fixture-audio','audio/ogg'),'Mostre minha rotina')
        self.assertTrue(vistos);self.assertFalse(vistos[0].exists());self.assertFalse(voz._TRAVA.locked())

    def test_timeout_remove_temporario_sem_retry_e_libera_trava(self):
        self.preparar_fixture()
        with patch.object(voz.subprocess,'run',side_effect=subprocess.TimeoutExpired('fixture',120)) as run:
            with self.assertRaisesRegex(voz.FalhaTranscritorLocal,'120 segundos'):
                voz.transcrever_audio(b'fixture-audio','audio/wav')
        run.assert_called_once();self.assertEqual(list(self.cache.glob('.voz-*')),[])
        self.assertFalse(voz._TRAVA.locked())

    def test_entrada_invalida_e_modelo_ausente_nao_iniciam_worker(self):
        with patch.object(voz.subprocess,'run') as run:
            for dados,mime in ((b'','audio/ogg'),(b'x'*8_000_001,'audio/ogg'),(b'x','video/mp4')):
                with self.assertRaises(ValueError):voz.transcrever_audio(dados,mime)
            with self.assertRaises(voz.FalhaTranscritorLocal):voz.transcrever_audio(b'x','audio/ogg')
        run.assert_not_called()

    def test_ocupado_nao_cria_segunda_transcricao(self):
        self.preparar_fixture();voz._TRAVA.acquire()
        try:
            with patch.object(voz.subprocess,'run') as run,self.assertRaisesRegex(voz.FalhaTranscritorLocal,'andamento'):
                voz.transcrever_audio(b'x','audio/ogg')
            run.assert_not_called()
        finally:voz._TRAVA.release()

    def test_worker_sem_chaves_offline_e_com_prazo_total(self):
        retorno=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,'texto':'Abra o VS Code'}))
        with patch.object(voz.subprocess,'run',return_value=retorno) as run:
            self.assertEqual(voz._executar_worker('transcrever','base',self.cache,self.cache/'a.ogg'),'Abra o VS Code')
        op=run.call_args.kwargs
        self.assertEqual(op['timeout'],120);self.assertIs(op['shell'],False)
        self.assertEqual(op['env']['HF_HUB_OFFLINE'],'1');self.assertNotIn('fixture-segredo',str(op))
        self.assertEqual(op['stderr'],subprocess.DEVNULL)
        with patch.object(voz.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='{"ok":true}')) as run:
            voz._executar_worker('preparar','base',self.cache)
        self.assertEqual(run.call_args.kwargs['timeout'],600)
        self.assertEqual(run.call_args.kwargs['env']['HF_HUB_OFFLINE'],'0')

    def test_resposta_invalida_nao_vira_pedido_parcial(self):
        for obj in ('privado',{'ok':True,'texto':'x'*8001},{'ok':True,'texto':'','chave':'privado'},{'ok':False,'erro':'motor'}):
            with patch.object(voz.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps(obj))), \
                    self.assertRaises(voz.FalhaTranscritorLocal) as erro:
                voz._executar_worker('transcrever','base',self.cache,self.cache/'a.ogg')
            self.assertNotIn('privado',str(erro.exception))

    def test_padrao_local_nao_consulta_gemini_mesmo_com_chave(self):
        roteador=MagicMock()
        with patch.object(voz,'verificar_disponibilidade') as verificar, \
                patch.object(voz,'transcrever_audio',return_value='Texto local') as transcrever:
            despacho.verificar_disponibilidade_voz(roteador)
            self.assertEqual(despacho.transcrever_audio(b'fixture','audio/ogg',roteador),'Texto local')
        verificar.assert_called_once();transcrever.assert_called_once_with(b'fixture','audio/ogg')
        roteador.estado_local.assert_not_called();roteador.responder.assert_not_called()

    def test_falha_local_nao_faz_fallback_pago(self):
        roteador=MagicMock()
        with patch.object(voz,'transcrever_audio',side_effect=voz.FalhaTranscritorLocal('Prazo local','timeout')):
            with self.assertRaises(despacho.FalhaAPI) as erro:despacho.transcrever_audio(b'fixture','audio/ogg',roteador)
        self.assertEqual(erro.exception.provedor,'Voz local');self.assertEqual(erro.exception.categoria,'timeout')
        roteador.registrar_falha.assert_not_called();roteador.responder.assert_not_called()

    def test_worker_cpu_int8_portugues_e_modelo_somente_local(self):
        self.preparar_fixture();motor=MagicMock()
        motor.transcribe.return_value=(iter([SimpleNamespace(text='Olá'),SimpleNamespace(text='mundo')]),None)
        modulo=SimpleNamespace(WhisperModel=MagicMock(return_value=motor))
        with patch.dict(sys.modules,{'faster_whisper':modulo}),patch.object(voz,'_decodificar_limitado',return_value='fixture-amostras'):
            self.assertEqual(voz._worker_transcrever('base',self.cache,self.cache/'a.ogg'),{'ok':True,'texto':'Olá mundo'})
        kwargs=modulo.WhisperModel.call_args.kwargs
        self.assertEqual(kwargs['device'],'cpu');self.assertEqual(kwargs['compute_type'],'int8')
        self.assertIs(kwargs['local_files_only'],True)
        self.assertEqual(motor.transcribe.call_args.kwargs['language'],'pt')

    def test_download_usa_api_publica_sem_argumentos_removidos_ou_token(self):
        chamadas=[]
        def snapshot(repo_id,*,local_dir,allow_patterns,local_files_only,token,max_workers):
            chamadas.append((repo_id,local_dir,allow_patterns,local_files_only,token,max_workers))
            self.preparar_fixture()
        with patch.dict(sys.modules,{'huggingface_hub':SimpleNamespace(snapshot_download=snapshot)}):
            retorno=voz._worker_preparar('base',self.cache)
        self.assertTrue(retorno['ok'])
        self.assertEqual(chamadas[0][0],'Systran/faster-whisper-base')
        self.assertIs(chamadas[0][3],False);self.assertIs(chamadas[0][4],False)
        self.assertEqual(chamadas[0][5],4)

    def test_proxy_so_e_herdado_na_preparacao_e_inferencia_continua_offline(self):
        with patch.dict(os.environ,{'HTTPS_PROXY':'http://fixture-proxy.invalid:8080'}):
            self.assertEqual(voz._ambiente_worker(self.cache,preparar=True)['HTTPS_PROXY'],'http://fixture-proxy.invalid:8080')
            self.assertNotIn('HTTPS_PROXY',voz._ambiente_worker(self.cache,preparar=False))


if __name__=='__main__':unittest.main()
