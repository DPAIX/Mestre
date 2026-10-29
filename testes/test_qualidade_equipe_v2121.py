"""Qualidade da equipe com respostas fictícias; nenhuma consulta ou ação real."""
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import conversa_equipe as equipe
from multi_ia import FalhaAPI

MODELOS=['llama3.2:latest','qwen3.5:4b']


def envelope(acao='nenhuma',campos=None,texto='Contribuição válida.'):
    return json.dumps({'resposta':texto,'acao':acao,'campos':{} if campos is None else campos})


class RoteadorNativoFicticio:
    def __init__(self,respostas):
        self.respostas=respostas
        self.chamadas=[]

    def limites_equipe(self,total):
        return {'por_modelo':90.,'rodada':90.*(total+1),'origem':'adaptativo'}

    def responder_equipe(self,mensagem,*,historico,modelo_ollama,limite_segundos):
        self.chamadas.append(modelo_ollama)
        return self.respostas[modelo_ollama],'Ollama'


class QualidadeEquipeTeste(unittest.TestCase):
    def setUp(self):
        for contexto in (patch.dict(os.environ,{'OLLAMA_PERFIL':'padrao'},clear=True),
                         patch.object(equipe,'_TRAVA',threading.Lock())):
            contexto.start();self.addCleanup(contexto.stop)
        self.roteador=MagicMock()

    def consultar(self,*,modo='cooperativa',parcial=None,roteador=None):
        return equipe.consultar_modelos('Ajude com o pedido.',[],MODELOS,
            self.roteador if roteador is None else roteador,
            interpretar=True,modo=modo,parcial=parcial)

    def respostas(self,respostas,sintese='Síntese útil.'):
        def responder(mensagem,**opcoes):
            if mensagem.startswith('Consolide '):return sintese,'Ollama'
            return respostas[opcoes['modelo_ollama']],'Ollama'
        self.roteador.responder.side_effect=responder

    def test_json_incompleto_nao_conta_como_sucesso_ou_parcial(self):
        self.respostas({MODELOS[0]:'{"resposta":"rascunho',MODELOS[1]:'Contribuição útil.'})
        parciais=[]
        resultado=self.consultar(parcial=parciais.append)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[False,True])
        self.assertEqual(resultado['resultados'][0]['categoria'],'resposta_invalida')
        self.assertEqual(resultado['resultados'][0]['texto'],'')
        self.assertEqual(resultado['coordenador'],MODELOS[1])
        self.assertEqual([r['modelo'] for r in parciais],[MODELOS[1]])
        self.assertEqual(parciais[0]['texto'],'Contribuição útil.')
        self.assertIn('1/2 modelos responderam',resultado['texto'])
        self.assertFalse(resultado['sintese']['tentada'])
        self.assertIsNone(resultado['plano'])
        self.assertEqual(self.roteador.responder.call_count,2)

    def test_todos_invalidos_explicam_conteudo_sem_contagem_positiva(self):
        self.respostas({MODELOS[0]:'{"resposta":"cortada',MODELOS[1]:'```json\n{"resposta":'})
        parciais=[]
        with self.assertRaisesRegex(RuntimeError,'Nenhum modelo da equipe respondeu com conteúdo válido') as recebido:
            self.consultar(parcial=parciais.append)
        self.assertEqual(parciais,[])
        self.assertEqual(self.roteador.responder.call_count,2)
        for modelo in MODELOS:self.assertIn(modelo,str(recebido.exception))
        self.assertFalse(equipe._TRAVA.locked())

    def test_acao_invalida_nao_e_voto_nem_consenso(self):
        self.respostas({MODELOS[0]:envelope('shell',{'comando':'fixture'}),
                        MODELOS[1]:envelope('pc',{'comando':'calc'})})
        resultado=self.consultar()
        self.assertFalse(resultado['resultados'][0]['ok'])
        self.assertEqual(resultado['resultados'][0]['categoria'],'resposta_invalida')
        self.assertTrue(resultado['resultados'][1]['ok'])
        self.assertIsNone(resultado['plano'])
        self.assertFalse(resultado['sintese']['tentada'])
        self.roteador.executar.assert_not_called()

    def test_paralela_rejeita_formato_invalido_e_preserva_categoria(self):
        self.respostas({MODELOS[0]:'{"resposta":"cortada',MODELOS[1]:'Resposta válida.'})
        parciais=[]
        resultado=self.consultar(modo='paralela',parcial=parciais.append)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[False,True])
        self.assertEqual(resultado['resultados'][0]['categoria'],'resposta_invalida')
        self.assertEqual([p['modelo'] for p in parciais],[MODELOS[1]])
        self.assertIn('1/2 modelos responderam',resultado['texto'])
        self.assertEqual(self.roteador.responder.call_count,2)

    def test_paralela_cpu_sequencial_rejeita_invalido_sem_remover_tag(self):
        roteador=RoteadorNativoFicticio({MODELOS[0]:'{"resposta":"cortada',MODELOS[1]:'Resposta válida.'})
        with patch.dict(os.environ,{'OLLAMA_PERFIL':'cpu'},clear=True):
            resultado=self.consultar(modo='paralela',roteador=roteador)
        self.assertEqual(resultado['execucao'],'sequencial_cpu')
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[False,True])
        self.assertEqual(resultado['resultados'][0]['categoria'],'resposta_invalida')
        self.assertEqual(roteador.chamadas,MODELOS)

    def test_sintese_invalida_preserva_contribuicao_real_sem_retry(self):
        self.respostas({MODELOS[0]:'Contribuição original útil.',MODELOS[1]:'Segunda contribuição.'},
                       sintese='{"resposta":"síntese incompleta')
        resultado=self.consultar()
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertTrue(resultado['sintese']['tentada'])
        self.assertFalse(resultado['sintese']['ok'])
        self.assertEqual(resultado['sintese']['categoria'],'resposta_invalida')
        self.assertIn('Contribuição original útil.',resultado['texto'])
        self.assertNotIn('síntese incompleta',resultado['texto'])
        self.assertEqual(self.roteador.responder.call_count,3)
        self.assertIsNone(resultado['plano'])

    def test_sintese_invalida_remove_plano_mesmo_com_consenso_anterior(self):
        resposta=envelope('pc',{'comando':'calc'})
        self.respostas(dict.fromkeys(MODELOS,resposta),sintese=envelope('shell',{'comando':'fixture'}))
        resultado=self.consultar()
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertFalse(resultado['sintese']['ok'])
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada',resultado['texto'])

    def test_conversa_textual_permanece_valida_sem_plano(self):
        self.respostas({MODELOS[0]:'Podemos organizar os estudos.',MODELOS[1]:'Precisamos definir um horário.'},
                       sintese='Qual é o seu horário disponível?')
        resultado=self.consultar()
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertTrue(resultado['sintese']['ok'])
        self.assertIn('Qual é o seu horário disponível?',resultado['texto'])
        self.assertIsNone(resultado['plano'])

    def test_envelope_valido_ainda_exige_consenso_de_todos_e_sintese(self):
        resposta=envelope('pc',{'comando':'calc'},'Posso preparar a calculadora.')
        self.respostas(dict.fromkeys(MODELOS,resposta),sintese=resposta)
        resultado=self.consultar()
        self.assertEqual(resultado['plano']['acao'],'pc')
        self.assertEqual(resultado['plano']['campos'],{'comando':'calc'})
        self.assertTrue(resultado['sintese']['ok'])
        self.roteador.executar.assert_not_called()

    def test_geracao_concluida_por_limite_nao_conta_e_permite_proximo_modelo(self):
        def responder(mensagem,**opcoes):
            if opcoes['modelo_ollama']==MODELOS[0]:
                raise FalhaAPI('Ollama',0,'Resposta cortada pelo limite de saída.','resposta_truncada')
            return 'Contribuição completa.','Ollama'
        self.roteador.responder.side_effect=responder
        resultado=self.consultar()
        self.assertEqual(self.roteador.responder.call_count,2)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[False,True])
        self.assertEqual(resultado['resultados'][0]['categoria'],'resposta_truncada')
        self.assertIn('1/2 modelos responderam com conteúdo válido',resultado['texto'])
        self.assertFalse(resultado['sintese']['tentada'])

    def test_redacao_de_json_com_aspas_escapadas_preserva_resposta_valida(self):
        segredo='fixture-segredo-contribuicao-803'
        resposta=envelope('kanban_adicionar',{'texto':'Revisar EXA_API_KEY='+segredo,'coluna':'A_Fazer'},
            texto='Diagnóstico CLIENT_SECRET="'+segredo+'"')
        self.respostas(dict.fromkeys(MODELOS,resposta),sintese=resposta)
        parciais=[]
        resultado=self.consultar(parcial=parciais.append)
        self.assertTrue(all(r['ok'] for r in resultado['resultados']))
        self.assertTrue(resultado['sintese']['ok'])
        self.assertIsNotNone(resultado['plano'])
        self.assertEqual(resultado['plano']['acao'],'kanban_adicionar')
        self.assertNotIn(segredo,json.dumps({'resultado':resultado,'parciais':parciais}))


if __name__=='__main__':unittest.main()
