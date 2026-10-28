"""Armazenamento conferido com arquivos e processos fictícios, sem Ollama."""
from contextlib import ExitStack
import hashlib
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import armazenamento_ollama_f as modulo


class ArmazenamentoOllamaFTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.origem=self.base/'origem_c'/'models';self.origem.mkdir(parents=True)
        self.raiz=self.base/'destino_f';self.raiz.mkdir()
        self.destino=self.raiz/'modelos_ollama'
        self.exe=self.base/'ollama.exe';self.exe.write_bytes(b'fixture-executavel')
        self.patches=ExitStack();self.addCleanup(self.patches.close)
        self.patches.enter_context(patch.dict(os.environ,{'OPENAI_API_KEY':'segredo-fixture',
            'HOME':'nao-repassar','TEMP':'nao-repassar','OLLAMA_MODELS':'nao-confiar'},clear=True))
        self.patches.enter_context(patch.object(modulo.shutil,'disk_usage',return_value=SimpleNamespace(free=100*1024**3)))
        self.patches.enter_context(patch.object(modulo.time,'sleep'))
        self.patches.enter_context(patch('sys.stdout',new_callable=io.StringIO))
        self.modelo=self.criar_modelo()

    def criar_modelo(self,corpo=b'pesos-ficticios'):
        digest=hashlib.sha256(corpo).hexdigest()
        blob=self.origem/'blobs'/('sha256-'+digest);blob.parent.mkdir(exist_ok=True);blob.write_bytes(corpo)
        doc={'schemaVersion':2,'config':{'digest':'sha256:'+digest,'size':len(corpo)},
            'layers':[{'digest':'sha256:'+digest,'size':len(corpo)}]}
        bruto=json.dumps(doc,separators=(',',':')).encode()
        manifesto=self.origem/'manifests'/'registry.ollama.ai'/'library'/'fixture'/'latest'
        manifesto.parent.mkdir(parents=True);manifesto.write_bytes(bruto)
        return {'digest':hashlib.sha256(bruto).hexdigest(),'blob':blob,'manifesto':manifesto}

    def catalogo(self):return {'fixture:latest':self.modelo['digest']}

    def validar_f(self,path):
        path=Path(path)
        if path==self.origem or self.origem in path.parents:
            raise ValueError('fora de F')
        return path

    def instalar_mocks(self,inspecoes):
        self.patches.enter_context(patch.object(modulo,'_em_f',side_effect=self.validar_f))
        inspecionar=self.patches.enter_context(patch.object(modulo,'_inspecionar',side_effect=inspecoes))
        catalogo=self.patches.enter_context(patch.object(modulo,'_catalogo',return_value=self.catalogo()))
        self.patches.enter_context(patch.object(modulo,'_ocupado',return_value=False))
        iniciar=self.patches.enter_context(patch.object(modulo.subprocess,'Popen'))
        iniciar.return_value.pid=77;iniciar.return_value.poll.return_value=None
        return inspecionar,catalogo,iniciar

    def processo_c(self):return {'pid':5,'executavel':self.exe,'modelos':self.origem,'perfil_f':False}
    def processo_f(self):return {'pid':77,'executavel':self.exe,'modelos':self.destino,'perfil_f':True}

    def test_copia_so_manifests_e_blobs_preserva_origem_e_nao_copia_conta(self):
        (self.origem.parent/'id_ed25519').write_text('chave-que-nao-deve-ser-copiada')
        self.assertEqual(modulo.copiar_modelos(self.origem,self.destino,self.catalogo()),1)
        for parte in ('blobs','manifests'):
            for arq in (self.origem/parte).rglob('*'):
                if arq.is_file():self.assertEqual(arq.read_bytes(),(self.destino/arq.relative_to(self.origem)).read_bytes())
        self.assertTrue((self.origem.parent/'id_ed25519').is_file())
        self.assertFalse((self.raiz/'id_ed25519').exists())
        self.assertFalse(list(self.destino.rglob('*.tmp')))

    def test_pesos_corrompidos_nao_publicam_manifesto(self):
        self.modelo['blob'].write_bytes(b'x'*len(b'pesos-ficticios'))
        with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        self.assertFalse((self.destino/'manifests').exists())
        self.assertFalse(list(self.destino.rglob('*.tmp')))

    def test_manifesto_divergente_no_destino_nao_e_sobrescrito(self):
        alvo=self.destino/self.modelo['manifesto'].relative_to(self.origem)
        alvo.parent.mkdir(parents=True);alvo.write_bytes(b'posterior')
        with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        self.assertEqual(alvo.read_bytes(),b'posterior')

    def test_falta_espaco_recusa_antes_de_copiar(self):
        with patch.object(modulo.shutil,'disk_usage',return_value=SimpleNamespace(free=5)):
            with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        self.assertFalse(self.destino.exists())

    def test_digest_ausente_do_store_recusa(self):
        with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,{'outro:latest':'e'*64})
        self.assertFalse(self.destino.exists())

    def test_blob_ausente_ou_com_tamanho_diferente_recusa(self):
        self.modelo['blob'].unlink()
        with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,self.catalogo())

    def test_link_de_peso_nao_e_seguido(self):
        alvo=self.modelo['blob'];alvo.unlink()
        outro=self.base/'nao-modelo';outro.write_text('fixture')
        try:alvo.symlink_to(outro)
        except OSError:self.skipTest('Criação de symlink indisponível neste Windows.')
        with self.assertRaises(modulo.FalhaArmazenamento):modulo.copiar_modelos(self.origem,self.destino,self.catalogo())

    def test_reusa_endpoint_com_store_f_provado_sem_novo_processo(self):
        modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        _,_,iniciar=self.instalar_mocks([self.processo_f()])
        resultado=modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)
        self.assertEqual(resultado['url'],'http://127.0.0.1:11434');self.assertFalse(resultado['iniciado'])
        iniciar.assert_not_called()

    def test_importa_c_inicia_f_e_nao_passa_segredos_ou_home(self):
        _,_,iniciar=self.instalar_mocks([self.processo_c(),None,self.processo_f()])
        resultado=modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)
        self.assertEqual(resultado['url'],modulo.URL_DEDICADA);self.assertTrue(resultado['importado'])
        self.assertTrue(self.modelo['blob'].exists())
        ambiente=iniciar.call_args.kwargs['env']
        self.assertNotIn('OPENAI_API_KEY',ambiente);self.assertNotIn('HOME',ambiente)
        for chave in ('TEMP','TMP','APPDATA','LOCALAPPDATA','USERPROFILE','OLLAMA_MODELS'):
            self.assertTrue(Path(ambiente[chave]).is_relative_to(self.raiz),chave)
        self.assertEqual(ambiente['OLLAMA_HOST'],modulo.URL_DEDICADA)
        self.assertEqual(iniciar.call_args.args[0],[str(self.exe),'serve'])
        self.assertIs(iniciar.call_args.kwargs['shell'],False)

    def test_store_ja_f_com_perfil_c_nao_e_reusado_para_escritas_no_c(self):
        modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        antigo={**self.processo_f(),'perfil_f':False}
        _,_,iniciar=self.instalar_mocks([antigo,None,self.processo_f()])
        resultado=modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)
        self.assertEqual(resultado['url'],modulo.URL_DEDICADA)
        self.assertEqual(resultado['modelos'],str(self.destino))
        self.assertFalse(resultado['importado'])
        self.assertEqual(iniciar.call_args.kwargs['env']['USERPROFILE'],str(self.raiz/'perfil_ollama'))

    def test_reinicio_sem_daemon_reusa_store_f_configurado_fora_da_raiz_padrao(self):
        externo=self.raiz/'Models_existentes';externo.mkdir()
        prova={**self.processo_f(),'modelos':externo}
        _,_,iniciar=self.instalar_mocks([None,None,prova])
        with patch.dict(os.environ,{'OLLAMA_MODELS':str(externo)}):
            resultado=modulo.garantir_armazenamento_f(modulo.URL_DEDICADA,self.raiz,executavel=self.exe)
        self.assertEqual(resultado['modelos'],str(externo))
        self.assertEqual(iniciar.call_args.kwargs['env']['OLLAMA_MODELS'],str(externo))

    def test_sem_daemon_e_configuracao_fora_f_nao_inventa_catalogo_vazio(self):
        _,_,iniciar=self.instalar_mocks([None])
        with patch.dict(os.environ,{'OLLAMA_MODELS':str(self.origem)}):
            with self.assertRaises(modulo.FalhaArmazenamento):
                modulo.garantir_armazenamento_f(modulo.URL_DEDICADA,self.raiz,executavel=self.exe)
        iniciar.assert_not_called()

    def test_importacao_recusada_preserva_modelos_sem_iniciar(self):
        _,_,iniciar=self.instalar_mocks([self.processo_c(),None])
        with self.assertRaises(modulo.FalhaArmazenamento):
            modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz,permitir_importacao=False)
        iniciar.assert_not_called();self.assertFalse(self.destino.exists())

    def test_porta_dedicada_ocupada_indeterminada_nao_inicia(self):
        _,_,iniciar=self.instalar_mocks([self.processo_c(),None])
        with patch.object(modulo,'_ocupado',return_value=True):
            with self.assertRaises(modulo.FalhaArmazenamento):
                modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)
        iniciar.assert_not_called();self.assertFalse(self.destino.exists())

    def test_reuso_da_dedicada_confere_catalogo_original(self):
        modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        _,catalogo,iniciar=self.instalar_mocks([self.processo_c(),self.processo_f()])
        catalogo.side_effect=[self.catalogo(),self.catalogo(),{}]
        with self.assertRaises(modulo.FalhaArmazenamento):
            modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)
        iniciar.assert_not_called()

    def test_pid_divergente_depois_do_inicio_nao_confirma_daemon(self):
        self.instalar_mocks([self.processo_c(),None]+[{**self.processo_f(),'pid':88}]*30)
        with self.assertRaises(modulo.FalhaArmazenamento):
            modulo.garantir_armazenamento_f('http://127.0.0.1:11434',self.raiz)

    def test_inspecao_so_projeta_pasta_sem_ambiente_bruto(self):
        processo=MagicMock();processo.create_time.return_value=1;processo.is_running.return_value=True
        processo.exe.return_value=str(self.exe);processo.cmdline.return_value=[str(self.exe),'serve']
        processo.environ.return_value={'OLLAMA_MODELS':str(self.origem),'USERPROFILE':str(self.base),
            'OPENAI_API_KEY':'segredo-fixture'}
        conexao=SimpleNamespace(status='LISTEN',laddr=('127.0.0.1',11434),pid=123)
        psutil=SimpleNamespace(CONN_LISTEN='LISTEN',net_connections=MagicMock(return_value=[conexao]),
            Process=MagicMock(return_value=processo))
        with patch.dict('sys.modules',{'psutil':psutil}):
            resultado=modulo._inspecionar('http://127.0.0.1:11434')
        self.assertEqual(set(resultado),{'pid','executavel','modelos','perfil_f'})
        self.assertNotIn('segredo-fixture',str(resultado))

    def test_inspecao_sem_dono_ou_args_diferentes_recusa(self):
        conexao=SimpleNamespace(status='LISTEN',laddr=('127.0.0.1',11434),pid=None)
        psutil=SimpleNamespace(CONN_LISTEN='LISTEN',net_connections=MagicMock(return_value=[conexao]))
        with patch.dict('sys.modules',{'psutil':psutil}):
            with self.assertRaises(modulo.FalhaArmazenamento):modulo._inspecionar('http://127.0.0.1:11434')

    def test_cli_stdout_contem_um_json_e_nao_repete_erro_bruto(self):
        with patch.object(modulo.sys,'platform','win32'), \
                patch.object(modulo,'garantir_armazenamento_f',side_effect=ValueError('segredo-fixture')), \
                patch('sys.stdout',new_callable=io.StringIO) as saida:
            codigo=modulo.main(['--garantir','--url','http://127.0.0.1:11434','--raiz',str(self.raiz)])
        self.assertEqual(codigo,2)
        self.assertFalse(json.loads(saida.getvalue())['ok'])
        self.assertNotIn('segredo-fixture',saida.getvalue())
        self.assertEqual(len(saida.getvalue().splitlines()),1)

    def test_cli_sucesso_devolve_somente_projecao_publica(self):
        esperado={'url':modulo.URL_DEDICADA,'modelos':str(self.destino),'iniciado':True,'importado':True}
        with patch.object(modulo.sys,'platform','win32'), \
                patch.object(modulo,'garantir_armazenamento_f',return_value=esperado), \
                patch('sys.stdout',new_callable=io.StringIO) as saida:
            codigo=modulo.main(['--garantir','--url','http://127.0.0.1:11434','--raiz',str(self.raiz)])
        self.assertEqual(codigo,0)
        self.assertEqual(json.loads(saida.getvalue()),{'ok':True,**esperado})

    def test_copia_progresso_nao_contamina_stdout_json(self):
        with patch('sys.stdout',new_callable=io.StringIO) as saida, \
                patch('sys.stderr',new_callable=io.StringIO) as progresso:
            modulo.copiar_modelos(self.origem,self.destino,self.catalogo())
        self.assertEqual(saida.getvalue(),'')
        self.assertIn('peso 1/1',progresso.getvalue())


if __name__=='__main__':unittest.main()
