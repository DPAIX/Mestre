"""Rodadas nativas com relógio e inferência fictícios, sem APIs ou dados reais."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import conversa_equipe as equipe
import multi_ia as ia


MODELOS=['llama3.2:latest','qwen3.5:4b','mistral:latest','qwen3.8:27b']
GIB=1024**3


class EquipeContinuacaoTeste(unittest.TestCase):
    def setUp(self):
        self.agora=100.0
        self.postagens=[]
        self.catalogo=[{'nome':nome,'nuvem':False,'tamanho_bytes':(indice+1)*GIB}
                       for indice,nome in enumerate(MODELOS)]
        for contexto in (
            patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_PERFIL':'cpu',
                'OLLAMA_URL':'http://127.0.0.1:11434','OLLAMA_TIMEOUT':'90',
                'OLLAMA_EQUIPE_TIMEOUT':'90','OLLAMA_EQUIPE_TIMEOUT_MODELO':'30'},clear=True),
            patch.object(equipe,'_TRAVA',threading.Lock()),
            patch.object(equipe.time,'monotonic',side_effect=lambda:self.agora),
            patch.object(ia,'ler_json',return_value={}),
            patch.object(ia,'gravar_json'),
            patch.object(ia,'registrar'),
            patch.object(ia,'memoria_fisica_bytes',return_value=64*GIB),
            patch.object(configurar,'listar_catalogo',side_effect=lambda *a:copy.deepcopy(self.catalogo)),
        ):
            contexto.start();self.addCleanup(contexto.stop)
        self.roteador=ia.Roteador()

    def responder(self,endpoint,chave,payload,provedor,**opcoes):
        self.postagens.append((copy.deepcopy(payload),opcoes))
        self.agora+=45
        return {'done':True,'message':{'content':'Contribuição curta de '+payload['model']}}

    def consultar(self,**opcoes):
        return equipe.consultar_modelos('Compare as alternativas.',[],MODELOS,self.roteador,
                                       modo='cooperativa',**opcoes)

    def test_quatro_modelos_temos_mesmo_prazo_individual_sem_cortar_rodada_em_90s(self):
        anteriores=list(MODELOS)
        ambiente=os.environ.copy()
        with patch.object(ia,'postar',side_effect=self.responder):
            resultado=self.consultar()
        self.assertEqual(len(self.postagens),5)
        self.assertEqual([p['model'] for p,_ in self.postagens[:4]],MODELOS)
        self.assertEqual([op['timeout'] for _,op in self.postagens],[90]*5)
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))
        self.assertEqual(resultado['orcamento'],{'por_modelo':90,'rodada':450,'origem':'adaptativo'})
        self.assertIn('4/4 modelos responderam',resultado['texto'])
        self.assertEqual(MODELOS,anteriores)
        self.assertEqual(os.environ.copy(),ambiente)

    def test_limites_personalizados_mantem_prazo_total_sem_renovar_a_cada_modelo(self):
        os.environ.update(OLLAMA_EQUIPE_TIMEOUT='50',OLLAMA_EQUIPE_TIMEOUT_MODELO='45')
        def responder(endpoint,chave,payload,provedor,**opcoes):
            self.postagens.append((copy.deepcopy(payload),opcoes))
            self.agora+=opcoes['timeout']
            return {'done':True,'message':{'content':'Resposta dentro do prazo.'}}
        with patch.object(ia,'postar',side_effect=responder):
            resultado=self.consultar()
        self.assertEqual([op['timeout'] for _,op in self.postagens],[45,5])
        self.assertEqual(resultado['orcamento'],{'por_modelo':45,'rodada':50,'origem':'personalizado'})
        self.assertEqual([r.get('categoria') for r in resultado['resultados'][2:]],['adiado','adiado'])

    def test_timeout_ambiguo_ainda_interrompe_sem_reenvio_ou_modelo_omitido(self):
        eventos=[]
        with patch.object(ia,'postar',side_effect=ia.FalhaAPI('Ollama',0,'Prazo da fixture.','tempo_esgotado')) as enviar:
            with self.assertRaisesRegex(RuntimeError,'Nenhum modelo') as recebido:
                self.consultar(progresso=eventos.append)
        enviar.assert_called_once()
        for nome in MODELOS:self.assertIn(nome,str(recebido.exception))
        self.assertEqual([e['modelo'] for e in eventos if e['estado']=='inicio'],MODELOS[:1])
        self.assertEqual([e['modelo'] for e in eventos if e['estado']=='adiado'],MODELOS[1:])

    def test_resposta_explicitamente_incompleta_nao_libera_outra_geracao(self):
        eventos=[]
        with patch.object(ia,'postar',return_value={'done':False,'message':{'content':'Texto parcial.'}}) as enviar:
            with self.assertRaisesRegex(RuntimeError,'Nenhum modelo') as recebido:
                self.consultar(progresso=eventos.append)
        enviar.assert_called_once()
        self.assertNotIn('Texto parcial.',str(recebido.exception))
        self.assertIn('término da geração',str(recebido.exception))
        self.assertEqual([e['estado'] for e in eventos],['inicio','falha','adiado','adiado','adiado'])

    def test_modelo_sem_recursos_permanece_no_relatorio_e_outros_participam(self):
        self.catalogo[-1]['tamanho_bytes']=80*GIB
        with patch.object(ia,'postar',side_effect=self.responder):
            resultado=self.consultar(interpretar=True)
        self.assertEqual([item['modelo'] for item in resultado['resultados']],MODELOS)
        self.assertEqual([item['ok'] for item in resultado['resultados']],[True,True,True,False])
        self.assertEqual(resultado['resultados'][-1]['categoria'],'recursos')
        self.assertIsNone(resultado['plano'])
        self.assertIn(MODELOS[-1],resultado['texto'])
        self.assertIn('3/4 modelos responderam',resultado['texto'])
        self.assertNotIn(MODELOS[-1],[p['model'] for p,_ in self.postagens])

    def test_orcamento_invalido_de_adaptador_falha_antes_de_qualquer_geracao(self):
        class RoteadorInvalido:
            def __init__(self,limites):self.limites=limites;self.responder=Mock()
            def limites_equipe(self,total):return self.limites
        validos={'por_modelo':90,'rodada':450,'origem':'adaptativo'}
        invalidos=[None,[],{},dict(validos,origem='inventada'),dict(validos,por_modelo=True),
                   dict(validos,rodada=float('inf')),dict(validos,por_modelo=121),
                   dict(validos,rodada=901),dict(validos,rodada=10**1000),
                   dict(validos,segredo='privado')]
        for limites in invalidos:
            with self.subTest(limites=limites):
                roteador=RoteadorInvalido(limites)
                with self.assertRaises(ValueError):
                    equipe.consultar_modelos('Pedido.',[],MODELOS,roteador,modo='cooperativa')
                roteador.responder.assert_not_called()

    def test_paralela_cpu_usa_mesmos_pedidos_sem_sintese_nem_sobreposicao(self):
        inicio=threading.Event();liberar=threading.Event();mutex=threading.Lock()
        ativos=0;maior=0;resultados=[];erros=[]
        def responder(endpoint,chave,payload,provedor,**opcoes):
            nonlocal ativos,maior
            with mutex:
                ativos+=1;maior=max(maior,ativos)
                self.postagens.append((copy.deepcopy(payload),opcoes))
                primeira=len(self.postagens)==1
            try:
                if primeira:
                    inicio.set()
                    if not liberar.wait(2):raise AssertionError('Primeira consulta não liberada.')
                return {'done':True,'message':{'content':'Resposta de '+payload['model']}}
            finally:
                with mutex:ativos-=1
        def executar():
            try:
                resultados.append(equipe.consultar_modelos('Pedido idêntico.',[],MODELOS,
                    self.roteador,modo='paralela'))
            except BaseException as erro:erros.append(erro)
        with patch.object(ia,'postar',side_effect=responder),patch.object(equipe,'ThreadPoolExecutor',side_effect=AssertionError('CPU não cria fila paralela.')):
            thread=threading.Thread(target=executar);thread.start()
            try:
                self.assertTrue(inicio.wait(1))
                self.assertEqual(len(self.postagens),1)
            finally:
                liberar.set();thread.join(3)
            self.assertFalse(thread.is_alive())
        if erros:raise erros[0]
        self.assertEqual(maior,1)
        self.assertEqual(len(self.postagens),4)
        self.assertTrue(all(p['messages'][-1]['content']=='Pedido idêntico.' for p,_ in self.postagens))
        resultado=resultados[0]
        self.assertEqual(resultado['modo'],'paralela')
        self.assertEqual(resultado['execucao'],'sequencial_cpu')
        self.assertIn('Execução sequencial no perfil CPU',resultado['texto'])
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertNotIn('sintese',resultado)

    def test_paralela_cpu_consenso_usa_todos_sem_acao_quando_ha_falha(self):
        texto=json.dumps({'resposta':'Proponho abrir.','acao':'pc','campos':{'comando':'calc'}})
        def responder(endpoint,chave,payload,provedor,**opcoes):
            if payload['model']==MODELOS[-1]:raise ia.FalhaAPI('Ollama',404,'Modelo não disponível.','modelo_indisponivel')
            return {'done':True,'message':{'content':texto}}
        with patch.object(ia,'postar',side_effect=responder):
            resultado=equipe.consultar_modelos('Abra a calculadora.',[],MODELOS,self.roteador,
                                               modo='paralela',interpretar=True)
        self.assertIsNone(resultado['plano'])
        self.assertEqual(len(resultado['resultados']),4)
        self.assertEqual(sum(r['ok'] for r in resultado['resultados']),3)


if __name__=='__main__':unittest.main()
