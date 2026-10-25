"""Prazos e respostas parciais com relógio/HTTP falsos; nenhuma inferência."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import conversa_equipe as equipe
import multi_ia as ia

MODELOS=['llama3.2:latest','qwen3.5:4b','mistral:latest','qwen3.8:27b']


class RoteadorComPrazo:
    def __init__(self, responder):self.chamadas=[];self.simular=responder
    def responder_equipe(self,mensagem,*,historico,modelo_ollama,limite_segundos):
        self.chamadas.append((mensagem,modelo_ollama,limite_segundos))
        return self.simular(mensagem,modelo_ollama,limite_segundos),'Ollama'


class PrazosEquipeTeste(unittest.TestCase):
    def setUp(self):
        self.agora=100.
        for p in (patch.dict(os.environ,{'OLLAMA_PERFIL':'cpu'},clear=True),
                  patch.object(equipe,'_TRAVA',threading.Lock()),
                  patch.object(equipe.time,'monotonic',side_effect=lambda:self.agora)):
            p.start();self.addCleanup(p.stop)

    def consultar(self, roteador, **opcoes):
        return equipe.consultar_modelos('Compare as opções.',[],MODELOS,roteador,
                                       modo='cooperativa',**opcoes)

    def test_primeiro_sucesso_e_entregue_antes_do_timeout_sem_plano(self):
        eventos=[]
        def responder(mensagem,modelo,segundos):
            if modelo==MODELOS[0]:
                self.agora+=10
                return json.dumps({'resposta':'Contribuição provisória.',
                                   'acao':'pc','campos':{'comando':'calc'}})
            self.assertEqual(eventos[0]['texto'],'Contribuição provisória.')
            self.agora+=segundos
            raise ia.FalhaAPI('Ollama',0,'Prazo fictício encerrado.','tempo_esgotado')
        roteador=RoteadorComPrazo(responder)
        resultado=self.consultar(roteador,interpretar=True,parcial=eventos.append)
        self.assertEqual(len(eventos),1)
        self.assertEqual(set(eventos[0]),{'modelo','texto','respondidos','total','provisoria'})
        self.assertTrue(eventos[0]['provisoria'])
        self.assertEqual(eventos[0]['respondidos'],1)
        self.assertEqual(eventos[0]['total'],4)
        self.assertEqual([m for _,m,_ in roteador.chamadas],MODELOS[:2])
        self.assertEqual([s for _,_,s in roteador.chamadas],[30,30])
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[True,False,False,False])
        self.assertEqual([r['categoria'] for r in resultado['resultados'][2:]],['adiado','adiado'])
        self.assertIsNone(resultado['plano'])
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertIn('pode continuar',resultado['texto'])
        self.assertIn('continua selecionado',resultado['texto'])

    def test_timeout_depois_de_dois_sucessos_nao_envia_sintese(self):
        def responder(mensagem,modelo,segundos):
            self.agora+=5
            if modelo==MODELOS[2]:raise TimeoutError('Fixture timed out')
            return 'Contribuição válida.'
        roteador=RoteadorComPrazo(responder)
        resultado=self.consultar(roteador)
        self.assertEqual(len(roteador.chamadas),3)
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertTrue(resultado['sintese']['adiada'])
        self.assertIn('síntese adicional não foi enviada',resultado['texto'])

    def test_timeout_nao_anuncia_consulta_dos_participantes_adiados(self):
        eventos=[]
        def responder(mensagem,modelo,segundos):
            raise ia.FalhaAPI('Ollama',0,'Prazo fictício encerrado.','tempo_esgotado')
        roteador=RoteadorComPrazo(responder)
        with self.assertRaisesRegex(RuntimeError,'Nenhum modelo'):
            self.consultar(roteador,progresso=eventos.append)
        self.assertEqual([modelo for _,modelo,_ in roteador.chamadas],MODELOS[:1])
        self.assertEqual([e['modelo'] for e in eventos if e['estado']=='inicio'],MODELOS[:1])
        self.assertEqual([e['modelo'] for e in eventos if e['estado']=='adiado'],MODELOS[1:])
        self.assertEqual([e['estado'] for e in eventos],['inicio','falha','adiado','adiado','adiado'])

    def test_callback_lento_de_sintese_nao_permite_envio_apos_prazo(self):
        eventos=[]
        def progresso(evento):
            eventos.append(evento)
            if evento['etapa']=='sintese' and evento['estado']=='inicio':self.agora+=100
        roteador=RoteadorComPrazo(lambda *a:'Contribuição curta.')
        resultado=self.consultar(roteador,progresso=progresso)
        self.assertEqual(len(roteador.chamadas),4)
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertTrue(resultado['sintese']['adiada'])
        self.assertEqual(eventos[-1]['estado'],'adiado')

    def test_callback_parcial_lento_consumiu_prazo_sem_novos_pedidos(self):
        def parcial(evento):self.agora+=100
        roteador=RoteadorComPrazo(lambda *a:'Contribuição curta.')
        resultado=self.consultar(roteador,parcial=parcial)
        self.assertEqual(len(roteador.chamadas),1)
        self.assertTrue(all(r.get('categoria')=='adiado' for r in resultado['resultados'][1:]))

    def test_orcamento_compartilhado_reduz_ultima_consulta_e_nao_renova_prazo(self):
        os.environ['OLLAMA_EQUIPE_TIMEOUT']='50'
        os.environ['OLLAMA_EQUIPE_TIMEOUT_MODELO']='45'
        def responder(mensagem,modelo,segundos):
            self.agora+=segundos
            return 'Resposta da fixture.'
        roteador=RoteadorComPrazo(responder)
        resultado=self.consultar(roteador)
        self.assertEqual([s for _,_,s in roteador.chamadas],[45,5])
        self.assertEqual([r.get('categoria') for r in resultado['resultados'][2:]],['adiado','adiado'])
        self.assertFalse(resultado['sintese']['tentada'])

    def test_sem_saldo_404_e_rede_sem_timeout_nao_interrompem_outros(self):
        for categoria in ('sem_creditos','modelo_indisponivel','rede','recursos'):
            with self.subTest(categoria=categoria):
                def responder(mensagem,modelo,segundos):
                    if modelo==MODELOS[0]:raise ia.FalhaAPI('Ollama',0,'Fixture falhou.',categoria)
                    return 'Contribuição disponível.'
                roteador=RoteadorComPrazo(responder)
                resultado=self.consultar(roteador)
                self.assertEqual([m for _,m,_ in roteador.chamadas[:4]],MODELOS)
                self.assertEqual(len(roteador.chamadas),5)
                self.assertTrue(resultado['sintese']['ok'])

    def test_timeout_classificado_por_adaptador_legado_tambem_para_rodada(self):
        roteador=MagicMock()
        roteador.responder.side_effect=ia.FalhaAPI('Ollama',0,'Modelo: timed out','rede')
        with self.assertRaisesRegex(RuntimeError,'Nenhum modelo') as erro:
            self.consultar(roteador)
        roteador.responder.assert_called_once()
        for modelo in MODELOS:self.assertIn(modelo,str(erro.exception))

    def test_callback_falho_nao_repete_consulta_e_texto_e_redigido_antes_do_corte(self):
        eventos=[]
        segredo='fixture-segredo-parcial-102'
        def parcial(evento):
            eventos.append(evento)
            raise RuntimeError('Fixture de interface indisponível.')
        roteador=RoteadorComPrazo(lambda *a:'EXA_API_KEY='+segredo+'\n'+'x'*5000)
        self.consultar(roteador,parcial=parcial)
        self.assertEqual(len(roteador.chamadas),5)
        self.assertEqual(len(eventos),1)
        self.assertLessEqual(len(eventos[0]['texto']),2000)
        self.assertNotIn(segredo,eventos[0]['texto'])

    def test_parametro_parcial_invalido_e_rejeitado_antes_da_consulta(self):
        roteador=MagicMock()
        with self.assertRaises(ValueError):self.consultar(roteador,parcial='fixture')
        roteador.responder.assert_not_called()

    def test_variaveis_invalidas_usam_limites_finitos_e_preservam_tentativa(self):
        for valor,esperado in (('nan',30),('inf',30),('erro',30),('0',5),('-1',5),('1000',90)):
            with self.subTest(valor=valor):
                os.environ['OLLAMA_EQUIPE_TIMEOUT_MODELO']=valor
                roteador=RoteadorComPrazo(lambda *a:'Resposta curta.')
                self.consultar(roteador)
                self.assertEqual(roteador.chamadas[0][2],esperado)


class PrazoAdaptadorTeste(unittest.TestCase):
    def setUp(self):
        for p in (patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_PERFIL':'cpu',
                       'OLLAMA_URL':'http://127.0.0.1:11434','OLLAMA_MODEL':MODELOS[0],
                       'OLLAMA_TIMEOUT':'90'},clear=True),
                  patch.object(ia,'ler_json',return_value={}),patch.object(ia,'gravar_json'),
                  patch.object(ia,'registrar'),patch.object(configurar,'listar_catalogo',
                       return_value=[{'nome':MODELOS[0],'nuvem':False}])):
            p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def test_adaptador_repassa_menor_timeout_sem_afetar_individual(self):
        with patch.object(ia,'postar',return_value={'message':{'content':'Resposta.'}}) as enviar:
            self.assertEqual(self.roteador.responder_equipe('Pedido.',modelo_ollama=MODELOS[0],
                limite_segundos=17),('Resposta.','Ollama'))
            self.assertGreater(enviar.call_args.kwargs['timeout'],0)
            self.assertLessEqual(enviar.call_args.kwargs['timeout'],17)
            self.roteador.ollama('Pedido individual.')
            self.assertEqual(enviar.call_args.kwargs['timeout'],90)
        self.assertEqual(os.environ['OLLAMA_TIMEOUT'],'90')

    def test_prazo_consumido_pelo_catalogo_nao_inicia_geracao(self):
        agora=[100.]
        def catalogo(*a):
            agora[0]+=20
            return [{'nome':MODELOS[0],'nuvem':False}]
        with patch.object(ia.time,'monotonic',side_effect=lambda:agora[0]), \
                patch.object(configurar,'listar_catalogo',side_effect=catalogo),patch.object(ia,'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.responder_equipe('Pedido.',modelo_ollama=MODELOS[0],limite_segundos=10)
        self.assertEqual(erro.exception.categoria,'tempo_esgotado')
        self.assertIn('Nenhuma geração enviada',erro.exception.detalhe)
        enviar.assert_not_called()

    def test_limites_invalidos_nao_fazem_http(self):
        for valor in (None,0,-1,True,'30',float('nan'),float('inf'),121,10**1000):
            with self.subTest(valor=valor),patch.object(ia,'postar') as enviar:
                with self.assertRaises(ValueError):
                    self.roteador.responder_equipe('Pedido.',modelo_ollama=MODELOS[0],limite_segundos=valor)
                enviar.assert_not_called()

    def test_timeout_real_difere_de_rede_e_nao_afirma_cancelamento(self):
        for erro in (TimeoutError('timed out'),URLError(TimeoutError('timed out'))):
            with self.subTest(erro=erro),patch.object(ia.urllib.request,'build_opener') as criar:
                criar.return_value.open.side_effect=erro
                with self.assertRaises(ia.FalhaAPI) as exc:
                    self.roteador.responder_equipe('Pedido.',modelo_ollama=MODELOS[0],limite_segundos=5)
                self.assertEqual(exc.exception.categoria,'tempo_esgotado')
                self.assertIn('não comprova falha de rede',exc.exception.detalhe)
                self.assertIn('cancelamento',exc.exception.detalhe)
                criar.return_value.open.assert_called_once()

    def test_categoria_timeout_e_preservada_no_estado_sem_rede_ficticia(self):
        self.roteador.registrar_falha(ia.FalhaAPI('Ollama',0,'Fixture expirou.','tempo_esgotado'))
        self.assertEqual(self.roteador.estado_local()['Ollama']['categoria'],'tempo_esgotado')
        self.assertIn('prazo de resposta esgotado',self.roteador.status()['Ollama'])


if __name__=='__main__':unittest.main()
