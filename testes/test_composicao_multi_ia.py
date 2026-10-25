"""Composição do gateway e cooperação CPU/nuvem, sem serviços reais."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import conversa_equipe as equipe
import multi_ia as ia
import roteador_9router as nine

GIB=1024**3
LLAMA='llama3.2:latest'
CLOUD='gemma4:31b-cloud'
QWEN='qwen3.5:4b'
MISTRAL='mistral:latest'
GRANDE='qwen3.8:27b'
MODELOS=[GRANDE,MISTRAL,LLAMA,QWEN,CLOUD]
CATALOGO=[{'nome':n,'nuvem':n==CLOUD,'tamanho_bytes':t}
          for n,t in zip(MODELOS,(17*GIB,4*GIB,2*GIB,3*GIB,50*GIB))]


class ComposicaoMultiIa(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{},clear=True);env.start();self.addCleanup(env.stop)
        for alvo,valor in (('ler_json',{}),('gravar_json',None),('registrar',None)):
            p=patch.object(ia,alvo,return_value=valor)
            p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def habilitar_router(self):
        os.environ.update({'NINE_ROUTER_HABILITADO':'1','NINE_ROUTER_MODEL':'combo-ficticio',
                           'NINE_ROUTER_API_KEY':'fixture-chave-nao-publicar'})

    def test_desabilitado_preserva_snapshot_legado_sem_carregar_conector(self):
        with patch.object(nine,'configurado',side_effect=AssertionError('Não consultar conector desligado')):
            self.assertEqual(set(self.roteador.estado_local()),{'Gemini','OpenAI','Claude','Exa'})
            os.environ['OLLAMA_HABILITADO']='1'
            self.assertEqual(set(self.roteador.estado_local()),{'Gemini','OpenAI','Claude','Exa','Ollama'})

    def test_habilitado_adiciona_estado_sem_consultar_servico(self):
        self.habilitar_router()
        with patch.object(nine,'responder',side_effect=AssertionError('Não inferir.')), \
                patch.object(nine,'listar_modelos',side_effect=AssertionError('Não consultar.')):
            estado=self.roteador.estado_local()['9Router']
            self.assertTrue(estado['configurado']);self.assertIsNone(estado['sucesso_em'])
            self.assertIn('não testado',self.roteador.status()['9Router'])

    def test_explicit_router_encaminha_historico_uma_vez_sem_outro_provedor(self):
        self.habilitar_router();os.environ['OPENAI_API_KEY']='fixture-paga'
        historico=[{'role':'user','content':'Turno fictício'}]
        with patch.object(nine,'responder',return_value='Resposta do gateway.') as enviar, \
                patch.object(self.roteador,'openai') as pago:
            resultado=self.roteador.responder('Compare alternativas',historico=historico,provedor='9router')
        self.assertEqual(resultado,('Resposta do gateway.','9Router'))
        enviar.assert_called_once_with('Compare alternativas',historico=historico)
        pago.assert_not_called();self.assertEqual(self.roteador.ultimo_provedor,'9Router')

    def test_router_automatico_e_prioritario_quando_habilitado(self):
        self.habilitar_router();os.environ['OPENAI_API_KEY']='fixture-paga'
        with patch.object(nine,'responder',return_value='Resposta do gateway.') as enviar, \
                patch.object(self.roteador,'openai') as pago:
            resultado=self.roteador.responder('Compare alternativas')
        self.assertEqual(resultado[1],'9Router');enviar.assert_called_once();pago.assert_not_called()

    def test_router_preserva_ultimo_pedido_de_12000_em_explicito_e_auto(self):
        self.habilitar_router()
        pergunta='x'*11970+' ULTIMO PEDIDO INTEIRO.'
        for provedor in ('9Router','auto'):
            with self.subTest(provedor=provedor),patch.object(nine,'responder',return_value='Resposta.') as enviar:
                self.roteador.responder(pergunta,provedor=provedor)
                enviar.assert_called_once_with(pergunta,historico=None)

    def test_falha_router_explicito_preserva_codigo_categoria_sem_fallback(self):
        self.habilitar_router();os.environ['OPENAI_API_KEY']='fixture-paga'
        for codigo,categoria in ((401,'autenticacao'),(429,'limite_temporario'),(404,'modelo_indisponivel')):
            self.roteador.reativar()
            with self.subTest(codigo=codigo), \
                    patch.object(nine,'responder',side_effect=ia.FalhaAPI('9Router',codigo,'Fixture rejeitada',categoria)) as enviar, \
                    patch.object(self.roteador,'openai') as pago:
                with self.assertRaises(ia.FalhaAPI) as erro:
                    self.roteador.responder('Pergunta',provedor='9Router')
                self.assertEqual((erro.exception.provedor,erro.exception.codigo,erro.exception.categoria),
                                 ('9Router',codigo,categoria))
                enviar.assert_called_once();pago.assert_not_called()

    def test_router_desligado_ou_incompleto_nao_consulta(self):
        for ambiente in ({},{'NINE_ROUTER_HABILITADO':'1'},
                         {'NINE_ROUTER_HABILITADO':'1','NINE_ROUTER_MODEL':'combo','NINE_ROUTER_URL':'https://example.invalid'}):
            with self.subTest(ambiente=ambiente),patch.dict(os.environ,ambiente,clear=True), \
                    patch.object(nine,'responder') as enviar:
                with self.assertRaises(ia.FalhaAPI) as erro:self.roteador.responder('Pergunta',provedor='9Router')
                self.assertEqual(erro.exception.categoria,'configuracao');enviar.assert_not_called()

    def test_modelo_ollama_nao_pode_ser_injetado_na_selecao_router(self):
        self.habilitar_router()
        with patch.object(nine,'responder') as enviar:
            with self.assertRaises(ValueError):self.roteador.responder('Pergunta',provedor='9Router',modelo_ollama='llama3.2')
            enviar.assert_not_called()

    def test_teste_conexao_explicito_uma_vez_e_com_estado_nao_disponibilidade_futura(self):
        self.habilitar_router()
        with patch.object(nine,'responder',return_value='OK') as enviar:
            resultado=self.roteador.verificar_conexoes('9Router')
        self.assertTrue(resultado['9Router']['ok']);enviar.assert_called_once_with('Responda somente OK.',historico=None)
        self.assertIsNotNone(self.roteador.estado_local()['9Router']['sucesso_em'])

    def test_troca_de_modelo_ou_chave_limpa_so_pausa_router_e_persiste_so_hash(self):
        self.habilitar_router()
        self.roteador.registrar_falha(ia.FalhaAPI('9Router',401,'Fixture','autenticacao'))
        self.roteador.registrar_falha(ia.FalhaAPI('OpenAI',401,'Fixture','autenticacao'))
        pago=copy.deepcopy(self.roteador.estado_local()['OpenAI'])
        os.environ['NINE_ROUTER_MODEL']='outra-combinacao'
        self.assertTrue(self.roteador.atualizar_configuracao_9router())
        self.assertNotIn('9Router',self.roteador.bloqueados)
        self.assertEqual(self.roteador.estado_local()['OpenAI'],pago)
        self.roteador.registrar_falha(ia.FalhaAPI('9Router',401,'Fixture','autenticacao'))
        os.environ['NINE_ROUTER_API_KEY']='outra-chave-ficticia'
        self.assertTrue(self.roteador.atualizar_configuracao_9router())
        persistido=repr(ia.gravar_json.call_args_list)
        self.assertNotIn('fixture-chave-nao-publicar',persistido)
        self.assertNotIn('outra-chave-ficticia',persistido)
        self.assertNotIn('outra-combinacao',persistido)
        self.assertEqual(ia.assinatura_configuracao_9router(),nine.assinatura_configuracao())

    def test_falha_de_chamada_antiga_nao_pausa_nova_configuracao(self):
        self.habilitar_router()
        antiga=ia.assinatura_configuracao_9router()
        os.environ['NINE_ROUTER_MODEL']='novo-modelo'
        self.roteador.registrar_falha(ia.FalhaAPI('9Router',401,'Fixture','autenticacao'),assinatura_9router=antiga)
        self.assertNotIn('9Router',self.roteador.bloqueados)
        self.roteador._registrar_sucesso('9Router',assinatura_9router=antiga)
        self.assertNotIn('9Router',self.roteador.sucessos)

    def test_pausa_persistida_so_restaura_se_configuracao_corresponde(self):
        self.habilitar_router()
        pausa={'ate':time.time()+600,'categoria':'autenticacao','codigo':401,
               'configuracao':ia.assinatura_configuracao_9router()}
        with patch.object(ia,'ler_json',return_value={'9Router':pausa}):
            roteador=ia.Roteador();self.assertFalse(roteador.disponivel('9Router'))
            os.environ['NINE_ROUTER_MODEL']='mudou'
            outro=ia.Roteador();self.assertTrue(outro.disponivel('9Router'))


class ComposicaoCpuNuvem(unittest.TestCase):
    def setUp(self):
        ambiente=patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_PERFIL':'cpu',
            'OLLAMA_MODEL':LLAMA,'OLLAMA_NUVEM_HABILITADA':'1'},clear=True)
        ambiente.start();self.addCleanup(ambiente.stop)
        for alvo,valor in (('ler_json',{}),('gravar_json',None),('registrar',None)):
            p=patch.object(ia,alvo,return_value=valor);p.start();self.addCleanup(p.stop)
        p=patch.object(configurar,'listar_catalogo',side_effect=lambda *a:copy.deepcopy(CATALOGO))
        self.catalogo=p.start();self.addCleanup(p.stop)
        p=patch.object(equipe,'_TRAVA',threading.Lock());p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def test_local_menor_primeiro_cloud_segundo_e_demais_pesos_em_ordem(self):
        self.assertEqual(self.roteador.ordenar_equipe_cpu(MODELOS),[LLAMA,CLOUD,QWEN,MISTRAL,GRANDE])
        self.assertEqual(MODELOS,[GRANDE,MISTRAL,LLAMA,QWEN,CLOUD])
        self.assertEqual(self.roteador.modelos_nuvem_equipe_cpu(),(CLOUD,))

    def test_sem_optin_ou_no_cloud_preserva_ordenacao_legada(self):
        for opcoes in ({'OLLAMA_NUVEM_HABILITADA':'0'},
                       {'OLLAMA_NUVEM_HABILITADA':'1','OLLAMA_NO_CLOUD':'1'}):
            with self.subTest(opcoes=opcoes),patch.dict(os.environ,opcoes):
                self.assertEqual(self.roteador.ordenar_equipe_cpu(MODELOS),[LLAMA,QWEN,MISTRAL,GRANDE,CLOUD])
                self.assertEqual(self.roteador.modelos_nuvem_equipe_cpu(),())

    def test_snapshot_puro_nao_reconsulta_catalogo_e_alias_remoto_e_identificado(self):
        self.catalogo.side_effect=lambda *a:[{'nome':'alias-remoto:latest','nuvem':True},
                                            {'nome':LLAMA,'nuvem':False,'tamanho_bytes':2*GIB}]
        self.assertEqual(self.roteador.ordenar_equipe_cpu(['alias-remoto:latest',LLAMA]),[LLAMA,'alias-remoto:latest'])
        with patch.object(self.roteador,'_obter_catalogo_ollama',side_effect=AssertionError('Não fazer I/O no snapshot')):
            self.assertEqual(self.roteador.modelos_nuvem_equipe_cpu(),('alias-remoto:latest',))

    def executar_com_timeout(self,coordenador=None):
        chamadas=[]
        parcial=[]
        def responder(pergunta,*,historico,modelo_ollama,limite_segundos):
            chamadas.append(modelo_ollama)
            if modelo_ollama==QWEN:raise ia.FalhaAPI('Ollama',0,'Fixture timeout','tempo_esgotado')
            return ('Contribuição '+modelo_ollama,'Ollama')
        # O adaptador consulta apenas métodos declarados, nunca atributos
        # fabricados por um mock de instância.
        with patch.object(type(self.roteador),'responder_equipe',side_effect=lambda obj,*a,**kw:responder(*a,**kw)):
            resultado=equipe.consultar_modelos('Compare alternativas',[],MODELOS,self.roteador,
                modo='cooperativa',coordenador=coordenador,parcial=parcial.append)
        return resultado,chamadas,parcial

    def test_cloud_responde_antes_timeout_local_e_e_aproveitado_sem_sintese(self):
        resultado,chamadas,parcial=self.executar_com_timeout()
        self.assertEqual(chamadas,[LLAMA,CLOUD,QWEN])
        self.assertEqual(parcial[0]['modelo'],LLAMA);self.assertEqual(len(parcial),1)
        self.assertEqual(resultado['coordenador'],CLOUD)
        self.assertIn('Contribuição '+CLOUD,resultado['texto'])
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual(sum(r['ok'] for r in resultado['resultados']),2)
        self.assertEqual(self.catalogo.call_count,1)
        self.assertIsNone(resultado['plano'])

    def test_coordenador_explicito_prevalece_sobre_preferencia_nuvem(self):
        resultado,_,_=self.executar_com_timeout(coordenador=LLAMA)
        self.assertEqual(resultado['coordenador'],LLAMA)


if __name__=='__main__':unittest.main()
