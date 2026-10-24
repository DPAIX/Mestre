"""Exceção cloud do perfil CPU com catálogo/HTTP fictícios e opt-in explícito."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import multi_ia as ia

GEMMA='gemma4:31b-cloud'
LLAMA='llama3.2:latest'


class NuvemCpuTeste(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_PERFIL':'cpu',
            'OLLAMA_URL':'http://127.0.0.1:11434','OLLAMA_MODEL':LLAMA,
            'OPENAI_API_KEY':'fixture-nao-usar'},clear=True)
        env.start();self.addCleanup(env.stop)
        for alvo in ('ler_json','gravar_json','registrar'):
            p=patch.object(ia,alvo,return_value={} if alvo=='ler_json' else None)
            p.start();self.addCleanup(p.stop)
        self.catalogo=[{'nome':GEMMA,'nuvem':True,'tamanho_bytes':50*1024**3},
                       {'nome':LLAMA,'nuvem':False,'tamanho_bytes':2*1024**3}]
        p=patch.object(configurar,'listar_catalogo',side_effect=lambda *a:copy.deepcopy(self.catalogo))
        self.listar=p.start();self.addCleanup(p.stop)
        p=patch.object(ia,'postar',return_value={'message':{'content':'Contribuição da fixture.'}})
        self.enviar=p.start();self.addCleanup(p.stop)
        p=patch.object(configurar.subprocess,'run',side_effect=AssertionError('Não instalar nem baixar'))
        self.processo=p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def gerar(self,modelo=GEMMA,**opcoes):
        return self.roteador.responder('Compare opções.',provedor='Ollama',modelo_ollama=modelo,**opcoes)

    def test_flag_padrao_desligada_e_so_zero_ou_um_sao_aceitos(self):
        self.assertFalse(ia.nuvem_autorizada())
        for valor,esperado in (('0',False),('1',True)):
            os.environ['OLLAMA_NUVEM_HABILITADA']=valor
            self.assertIs(ia.nuvem_autorizada(),esperado)
        for valor in ('','true','false',' 1','1 ','2','nan','inf'):
            os.environ['OLLAMA_NUVEM_HABILITADA']=valor
            with self.subTest(valor=valor),self.assertRaises(ia.FalhaAPI) as erro:
                ia.nuvem_autorizada()
            self.assertEqual(erro.exception.categoria,'configuracao')
        self.listar.assert_not_called();self.enviar.assert_not_called()

    def test_sem_optin_cloud_nao_gera_e_orienta_botao(self):
        with self.assertRaises(ia.FalhaAPI) as erro:self.gerar()
        self.assertEqual(erro.exception.categoria,'configuracao')
        self.assertIn('botão',erro.exception.detalhe)
        self.assertIn('login e cota',erro.exception.detalhe)
        self.enviar.assert_not_called();self.processo.assert_not_called()

    def test_optin_envia_gemma_cloud_ao_loopback_sem_forcar_cpu_ou_ram(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        anterior=dict(os.environ)
        with patch.object(ia,'memoria_fisica_bytes',side_effect=AssertionError('Cloud não usa orçamento RAM local')):
            self.assertEqual(self.gerar(modo_cooperativo=True),('Contribuição da fixture.','Ollama'))
        args=self.enviar.call_args
        self.assertEqual(args.args[0],'http://127.0.0.1:11434/api/chat')
        payload=args.args[2]
        self.assertEqual(payload['model'],GEMMA)
        self.assertEqual(payload['options'],{'num_ctx':1024,'num_predict':128})
        self.assertFalse(payload['think']);self.assertFalse(payload['stream'])
        self.assertEqual(payload['keep_alive'],0)
        self.assertEqual(dict(os.environ),anterior)
        self.processo.assert_not_called()

    def test_cpu_individual_cloud_tambem_exige_optin_e_nao_forca_num_gpu(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        self.gerar()
        payload=self.enviar.call_args.args[2]
        self.assertNotIn('num_gpu',payload['options'])
        self.assertNotIn('think',payload)

    def test_alias_remoto_sem_sufixo_exige_optin_e_resolve_latest(self):
        self.catalogo=[{'nome':'alias-remoto:latest','nuvem':True}]
        with self.assertRaises(ia.FalhaAPI):self.gerar('alias-remoto')
        self.enviar.assert_not_called()
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        self.gerar('alias-remoto')
        payload=self.enviar.call_args.args[2]
        self.assertEqual(payload['model'],'alias-remoto:latest')
        self.assertNotIn('num_gpu',payload['options'])

    def test_indicacao_remota_prevalece_em_registro_duplicado_ou_tag_cloud(self):
        for catalogo,modelo in (([{'nome':'alias:latest','nuvem':False},
                                  {'nome':'alias:latest','nuvem':True}],'alias'),
                                ([{'nome':GEMMA,'nuvem':False}],GEMMA)):
            with self.subTest(modelo=modelo):
                self.catalogo=catalogo;self.roteador.invalidar_catalogo_ollama()
                with self.assertRaises(ia.FalhaAPI):self.gerar(modelo)
                self.enviar.assert_not_called()

    def test_no_cloud_um_prevalece_sobre_optin_sem_bloquear_local(self):
        os.environ.update({'OLLAMA_NUVEM_HABILITADA':'1','OLLAMA_NO_CLOUD':'1'})
        with self.assertRaises(ia.FalhaAPI) as erro:self.gerar()
        self.assertIn('OLLAMA_NO_CLOUD=1',erro.exception.detalhe)
        self.enviar.assert_not_called()
        self.gerar(LLAMA)
        self.assertEqual(self.enviar.call_args.args[2]['options'],
                         {'num_gpu':0,'num_ctx':1024,'num_predict':128})

    def test_tag_cloud_ausente_nao_registra_baixa_ou_gera(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='1';self.catalogo=[]
        with self.assertRaises(ia.FalhaAPI) as erro:self.gerar()
        self.assertEqual(erro.exception.categoria,'configuracao')
        self.enviar.assert_not_called();self.processo.assert_not_called()

    def test_flag_invalida_interrompe_cpu_antes_de_geracao(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='sim'
        with self.assertRaises(ia.FalhaAPI) as erro:self.gerar(LLAMA)
        self.assertEqual(erro.exception.categoria,'configuracao')
        self.listar.assert_not_called();self.enviar.assert_not_called()

    def test_falha_de_login_cota_ou_modelo_nao_chama_outro_provedor(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        for codigo,categoria in ((401,'autenticacao'),(429,'limite_temporario'),(404,'modelo_indisponivel')):
            self.enviar.reset_mock()
            with self.subTest(codigo=codigo),patch.object(self.roteador,'openai') as pago, \
                    patch.object(configurar,'listar_modelos',return_value=[GEMMA]), \
                    patch.object(ia,'postar',side_effect=ia.FalhaAPI('Ollama',codigo,'Fixture rejeitada.',categoria)) as enviar:
                with self.assertRaises(ia.FalhaAPI) as erro:self.gerar()
                self.assertEqual(erro.exception.categoria,categoria)
                pago.assert_not_called();enviar.assert_called_once()

    def test_cloud_nao_aceita_url_remota_mesmo_com_optin(self):
        os.environ.update({'OLLAMA_NUVEM_HABILITADA':'1','OLLAMA_URL':'https://remoto.example'})
        with self.assertRaises(ia.FalhaAPI) as erro:self.gerar()
        self.assertEqual(erro.exception.categoria,'configuracao')
        self.listar.assert_not_called();self.enviar.assert_not_called()

    def test_local_mantem_cpu_e_limites_com_optin_ligado(self):
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        self.gerar(LLAMA,modo_cooperativo=True)
        payload=self.enviar.call_args.args[2]
        self.assertEqual(payload['model'],LLAMA)
        self.assertEqual(payload['options'],{'num_gpu':0,'num_ctx':1024,'num_predict':128})
        self.assertFalse(payload['think'])
        self.assertEqual(os.environ['OLLAMA_MODEL'],LLAMA)

    def test_optin_altera_assinatura_e_libera_so_pausa_ollama(self):
        antes=ia.assinatura_configuracao_ollama()
        self.roteador.registrar_falha(ia.FalhaAPI('Ollama',0,'Fixture sem opt-in.','configuracao'))
        self.roteador.registrar_falha(ia.FalhaAPI('OpenAI',401,'Fixture.','autenticacao'))
        estado_pago=copy.deepcopy(self.roteador.estado_local()['OpenAI'])
        os.environ['OLLAMA_NUVEM_HABILITADA']='1'
        self.assertNotEqual(ia.assinatura_configuracao_ollama(),antes)
        self.assertTrue(self.roteador.atualizar_configuracao_ollama())
        self.assertNotIn('Ollama',self.roteador.bloqueados)
        self.assertEqual(self.roteador.estado_local()['OpenAI'],estado_pago)
        self.enviar.assert_not_called()


if __name__=='__main__':unittest.main()
