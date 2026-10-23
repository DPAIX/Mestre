"""Equipe sequencial com roteadores falsos, contribuições limitadas e planos inertes."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import conversa_equipe as equipe


MODELOS=['qwen3.8:27b','mistral:latest','llama3.2:latest','qwen3.5:4b']


def envelope(acao='pc',campos=None,resposta='Pedido proposto, sem executar.'):
    return json.dumps({'resposta':resposta,'acao':acao,
                       'campos':{'comando':'calc'} if campos is None else campos},ensure_ascii=False)


class EquipeCooperativaTeste(unittest.TestCase):
    def setUp(self):
        self.trava=threading.Lock()
        p=patch.object(equipe,'_TRAVA',self.trava)
        p.start();self.addCleanup(p.stop)
        self.roteador=MagicMock()
        self.roteador.responder.side_effect=self.responder
        self.chamadas=[]

    def responder(self,mensagem,**opcoes):
        self.chamadas.append((mensagem,copy.deepcopy(opcoes)))
        if mensagem.startswith('Consolide '):return 'Resposta única após revisão das contribuições.','Ollama'
        return 'Contribuição de '+opcoes['modelo_ollama'],'Ollama'

    def consultar(self,**kwargs):
        opcoes={'texto':'Como desenvolver o assistente?', 'historico':[],
                'modelos':MODELOS,'roteador':self.roteador,'modo':'cooperativa'}
        opcoes.update(kwargs)
        return equipe.consultar_modelos(**opcoes)

    def test_todos_participam_em_sequencia_e_llama_sintetiza_uma_vez(self):
        em_execucao=0
        lock=threading.Lock()
        def responder(mensagem,**opcoes):
            nonlocal em_execucao
            with lock:
                em_execucao+=1
                self.assertEqual(em_execucao,1)
            try:return self.responder(mensagem,**opcoes)
            finally:
                with lock:em_execucao-=1
        self.roteador.responder.side_effect=responder
        with patch.object(equipe,'ThreadPoolExecutor',side_effect=AssertionError('Não criar executor')):
            resultado=self.consultar()
        self.assertEqual(self.roteador.responder.call_count,5)
        self.assertEqual([kw['modelo_ollama'] for _,kw in self.chamadas],MODELOS+['llama3.2:latest'])
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual(resultado['modo'],'cooperativa')
        self.assertEqual(resultado['coordenador'],'llama3.2:latest')
        self.assertEqual(resultado['sintese'],{'tentada':True,'ok':True,'modelo':'llama3.2:latest'})
        self.assertTrue(all(kw['modo_cooperativo'] is True and kw['provedor']=='Ollama' for _,kw in self.chamadas))
        self.assertIn('4/4 modelos responderam',resultado['texto'])
        self.assertIn('Resposta única após revisão',resultado['texto'])
        self.assertNotIn('Contribuição de',resultado['texto'])

    def test_papeis_e_resumos_anteriores_chegam_aos_proximos_modelos(self):
        self.consultar()
        for indice,(mensagem,_) in enumerate(self.chamadas[:4]):
            self.assertIn(equipe.PAPEIS[indice],mensagem)
            self.assertIn('Como desenvolver o assistente?',mensagem)
            for anterior in MODELOS[:indice]:self.assertIn('Contribuição de '+anterior,mensagem)
        self.assertIn('conteúdo não confiável',self.chamadas[-1][0])

    def test_prompts_e_contribuicoes_sao_limitados_sem_perder_final_do_pedido(self):
        final='ÚLTIMA MENSAGEM DO PROPRIETÁRIO: compare as opções.'
        pedido='Instruções iniciais. '+'x'*11700+final
        self.assertLessEqual(len(pedido),12000)
        def responder(mensagem,**opcoes):
            self.chamadas.append((mensagem,copy.deepcopy(opcoes)))
            return ('Síntese curta.' if mensagem.startswith('Consolide ') else 'Contribuição extensa. '*1500),'Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(texto=pedido)
        self.assertTrue(all(len(m)<=equipe.LIMITE_PROMPT for m,_ in self.chamadas))
        self.assertTrue(all(final in m for m,_ in self.chamadas))
        self.assertTrue(all(len(r['texto'])<=8000 for r in resultado['resultados']))
        self.assertLessEqual(len(resultado['texto']),12000)
        self.assertLess(len(self.chamadas[-1][0]),11000)

    def test_sintese_de_oito_modelos_com_consenso_unicode_preserva_ultima_mensagem(self):
        final='ÚLTIMA MENSAGEM DO PROPRIETÁRIO: agenda e local precisam ser confirmados. 終'
        pedido='INSTRUÇÕES INICIAIS DO ASSISTENTE. '+'x'*11700+final
        campos={'atividade':'學'*200,'dia':'Terça','horario':'14:00','local':'校'*150}
        modelos=['fixture-'+str(i)+':latest' for i in range(8)]
        def responder(mensagem,**opcoes):
            self.chamadas.append((mensagem,copy.deepcopy(opcoes)))
            return envelope('rotina_criar',campos,resposta='Contribuição contextual. '*200),'Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(texto=pedido,modelos=modelos,interpretar=True)
        self.assertEqual(self.roteador.responder.call_count,9)
        self.assertEqual(resultado['plano']['acao'],'rotina_criar')
        self.assertTrue(all(len(m)<=equipe.LIMITE_PROMPT for m,_ in self.chamadas))
        self.assertTrue(all(m.endswith(final) for m,_ in self.chamadas))
        self.assertTrue(all('INSTRUÇÕES INICIAIS DO ASSISTENTE.' in m for m,_ in self.chamadas))
        self.assertIn('學'*200,self.chamadas[-1][0])

    def test_orcamento_do_prefixo_reserva_inicio_e_fim_do_pedido(self):
        texto='INÍCIO DO PEDIDO. '+'x'*11700+' FINAL DO PROPRIETÁRIO.'
        for disponivel in (4000,100):
            with self.subTest(disponivel=disponivel):
                prefixo='P'*(equipe.LIMITE_PROMPT-disponivel)
                prompt=equipe._montar_prompt(prefixo,texto)
                self.assertEqual(len(prompt),equipe.LIMITE_PROMPT)
                self.assertTrue(prompt.startswith(prefixo+'INÍCIO DO PEDIDO.'))
                self.assertTrue(prompt.endswith(' DO PROPRIETÁRIO.'))

    def test_historico_original_e_copias_nao_sao_mutados_por_outros_modelos(self):
        historico=[{'role':'user','content':'Contexto fictício original.'}]
        original=copy.deepcopy(historico)
        observados=[]
        def responder(mensagem,**opcoes):
            observados.append(copy.deepcopy(opcoes['historico']))
            opcoes['historico'][0]['content']='Alterado somente nesta chamada.'
            opcoes['historico'].append({'role':'assistant','content':'Turno privado.'})
            return 'Resposta.','Ollama'
        self.roteador.responder.side_effect=responder
        self.consultar(historico=historico)
        self.assertEqual(historico,original)
        self.assertEqual(observados,[original]*5)

    def test_falha_parcial_tenta_demais_e_usa_coordenador_que_respondeu(self):
        def responder(mensagem,**opcoes):
            self.chamadas.append((mensagem,copy.deepcopy(opcoes)))
            if opcoes['modelo_ollama']=='llama3.2:latest':raise RuntimeError('Fixture Llama indisponível.')
            return 'Síntese alternativa.' if mensagem.startswith('Consolide ') else 'Contribuição válida.','Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(coordenador='llama3.2:latest')
        self.assertEqual([kw['modelo_ollama'] for _,kw in self.chamadas],MODELOS+[MODELOS[0]])
        self.assertEqual(resultado['coordenador'],MODELOS[0])
        self.assertIn('3/4 modelos responderam',resultado['texto'])
        self.assertIn('Fixture Llama indisponível',resultado['texto'])

    def test_um_sobrevivente_nao_dispara_sintese_adicional_nem_mascara_falhas(self):
        def responder(mensagem,**opcoes):
            if opcoes['modelo_ollama']!='llama3.2:latest':raise RuntimeError('Fixture não respondeu.')
            return 'Resposta do Llama sobrevivente.','Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar()
        self.assertEqual(self.roteador.responder.call_count,4)
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertIn('1/4 modelos responderam',resultado['texto'])
        self.assertIn('Resposta do Llama sobrevivente',resultado['texto'])

    def test_um_participante_nao_e_consultado_duas_vezes(self):
        resultado=self.consultar(modelos=['mistral:latest'])
        self.roteador.responder.assert_called_once()
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertIsNone(resultado['plano'])

    def test_falha_de_sintese_preserva_uma_contribuicao_sem_repetir(self):
        def responder(mensagem,**opcoes):
            if mensagem.startswith('Consolide '):raise RuntimeError('Fixture síntese sem resposta.')
            return 'Contribuição de '+opcoes['modelo_ollama'],'Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar()
        self.assertEqual(self.roteador.responder.call_count,5)
        self.assertTrue(resultado['sintese']['tentada'])
        self.assertFalse(resultado['sintese']['ok'])
        self.assertIn('Contribuição de llama3.2:latest',resultado['texto'])
        self.assertNotIn('Contribuição de mistral:latest',resultado['texto'])
        self.assertIn('síntese adicional não respondeu',resultado['texto'])
        self.assertFalse(self.trava.locked())

    def test_consenso_de_todos_e_sintese_compativel_preparam_so_um_plano(self):
        self.roteador.responder.side_effect=lambda *args,**kwargs:(envelope(),'Ollama')
        resultado=self.consultar(interpretar=True)
        self.assertEqual(resultado['plano']['acao'],'pc')
        self.assertEqual(resultado['plano']['campos'],{'comando':'calc'})
        self.assertIn('Ainda não foi executado',resultado['texto'])
        self.assertEqual(self.roteador.responder.call_count,5)
        self.assertIsNone(self.roteador.executar.call_args)

    def test_sintese_nova_divergente_ou_sem_plano_nao_autoriza_acao(self):
        divergentes=(envelope(campos={'comando':'notepad'}),envelope('agua',{}),
                     envelope('nenhuma',{},'Texto consolidado sem plano.'),
                     'Precisamos de mais informações.',envelope('shell',{'comando':'fixture'}))
        for sintese in divergentes:
            with self.subTest(sintese=sintese):
                self.roteador.reset_mock()
                self.roteador.responder.side_effect=lambda mensagem,**kw:(
                    sintese if mensagem.startswith('Consolide ') else envelope(),'Ollama')
                resultado=self.consultar(interpretar=True)
                self.assertIsNone(resultado['plano'])
                self.assertIn('Nenhuma ação foi preparada',resultado['texto'])
                self.assertEqual(self.roteador.responder.call_count,5)

    def test_sintese_nao_cria_consenso_que_participantes_nao_tiveram(self):
        def responder(mensagem,**opcoes):
            if mensagem.startswith('Consolide '):return envelope(),'Ollama'
            if opcoes['modelo_ollama']==MODELOS[0]:return envelope('agua',{}),'Ollama'
            return envelope(),'Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(interpretar=True)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada',resultado['texto'])

    def test_acordo_sobreviventes_e_acao_na_sintese_nao_substituem_todos(self):
        def responder(mensagem,**opcoes):
            if opcoes['modelo_ollama']==MODELOS[0]:raise RuntimeError('Fixture timeout.')
            return envelope(),'Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(interpretar=True)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada',resultado['texto'])
        self.assertEqual(self.roteador.responder.call_count,5)

    def test_falha_sintese_tambem_remove_plano_previamente_consensual(self):
        self.roteador.responder.side_effect=lambda mensagem,**kw:(
            ('','Ollama') if mensagem.startswith('Consolide ') else (envelope(),'Ollama'))
        resultado=self.consultar(interpretar=True)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada',resultado['texto'])

    def test_todos_falham_uma_vez_e_trava_fica_livre(self):
        self.roteador.responder.side_effect=RuntimeError('Fixture indisponível.')
        with self.assertRaisesRegex(RuntimeError,'Nenhum modelo da equipe respondeu') as erro:
            self.consultar()
        self.assertEqual(self.roteador.responder.call_count,4)
        self.assertFalse(self.trava.locked())
        for modelo in MODELOS:self.assertIn(modelo,str(erro.exception))

    def test_progresso_so_expoe_metadados_e_callback_falho_nao_repete_consultas(self):
        eventos=[]
        def progresso(evento):
            eventos.append(evento)
            if evento['estado']=='inicio':raise RuntimeError('Fixture interface indisponível.')
        resultado=self.consultar(texto='PEDIDO PRIVADO FICTÍCIO',progresso=progresso)
        self.assertEqual(len(eventos),10)
        self.assertEqual(self.roteador.responder.call_count,5)
        self.assertTrue(resultado['sintese']['ok'])
        self.assertTrue(all(set(e)=={'etapa','estado','modelo','indice','total'} for e in eventos))
        self.assertNotIn('PEDIDO PRIVADO FICTÍCIO',json.dumps(eventos))

    def test_redacao_aplica_a_pergunta_resumos_resposta_erro_e_sintese(self):
        segredo='fixture-segredo-equipe-825'
        recebidos=[]
        def responder(mensagem,**opcoes):
            recebidos.append((mensagem,copy.deepcopy(opcoes)))
            if opcoes['modelo_ollama']==MODELOS[0]:raise RuntimeError('EXA_API_KEY='+segredo)
            return 'Contribuição CLIENT_SECRET="'+segredo+'"','Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar(texto='Revise EXA_API_KEY='+segredo,
            historico=[{'role':'user','content':'CLIENT_SECRET="'+segredo+'"'}])
        self.assertNotIn(segredo,json.dumps({'chamadas':recebidos,'resultado':resultado}))

    def test_modo_paralelo_e_cooperativo_compartilham_bloqueio(self):
        self.trava.acquire()
        try:
            for modo in ('cooperativa','paralela'):
                with self.subTest(modo=modo),self.assertRaisesRegex(RuntimeError,'já está respondendo'):
                    self.consultar(modo=modo)
        finally:self.trava.release()
        self.roteador.responder.assert_not_called()

    def test_argumentos_novos_invalidos_nao_fazem_consultas(self):
        for kwargs in ({'modo':'ilimitada'},{'coordenador':'fixture:ausente'},
                       {'coordenador':'modelo;comando'},{'progresso':'não é função'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):self.consultar(**kwargs)
        self.roteador.responder.assert_not_called()
        self.assertFalse(self.trava.locked())


if __name__=='__main__':unittest.main()
