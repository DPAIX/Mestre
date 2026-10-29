"""Prazos e conclusão das consultas com catálogo/HTTP fictícios, sem inferência."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import multi_ia as ia
import configurar_ia_local as configurar


class InferenciaEquipeV212(unittest.TestCase):
    def setUp(self):
        for contexto in (
            patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_URL':'http://127.0.0.1:11434',
                'OLLAMA_MODEL':'llama3.2:latest','OLLAMA_PERFIL':'cpu'},clear=True),
            patch.object(ia,'ler_json',return_value={}),
            patch.object(ia,'gravar_json'),patch.object(ia,'registrar'),
            patch.object(configurar,'listar_catalogo',return_value=[
                {'nome':'llama3.2:latest','nuvem':False},
                {'nome':'qwen3.5:4b','nuvem':False},
                {'nome':'mistral:latest','nuvem':False},
                {'nome':'qwen3.8:27b','nuvem':False}]),
        ):
            contexto.start();self.addCleanup(contexto.stop)
        self.roteador=ia.Roteador()

    def test_padrao_nativo_reserva_o_prazo_individual_para_cada_participante(self):
        antes=dict(os.environ)
        with patch.object(ia,'postar') as enviar:
            limites=self.roteador.limites_equipe(4)
        self.assertEqual(limites,{'por_modelo':90.,'rodada':450.,'origem':'adaptativo'})
        self.assertEqual(dict(os.environ),antes)
        enviar.assert_not_called()

    def test_par_gerenciado_90_30_nao_continua_reduzindo_primeiro_modelo(self):
        os.environ.update({'OLLAMA_EQUIPE_TIMEOUT':'90','OLLAMA_EQUIPE_TIMEOUT_MODELO':'30'})
        limites=self.roteador.limites_equipe(4)
        with patch.object(ia,'postar',return_value={'message':{'content':'OK'},'done':True}) as enviar:
            self.assertEqual(self.roteador.responder_equipe('Pedido curto.',
                modelo_ollama='llama3.2:latest',limite_segundos=limites['por_modelo']),('OK','Ollama'))
        self.assertGreater(enviar.call_args.kwargs['timeout'],30)
        self.assertLessEqual(enviar.call_args.kwargs['timeout'],90)
        self.assertEqual(os.environ['OLLAMA_EQUIPE_TIMEOUT_MODELO'],'30')
        enviar.assert_called_once()

    def test_prazo_individual_personalizado_e_preservado_nos_dois_fluxos(self):
        os.environ['OLLAMA_TIMEOUT']='25'
        limites=self.roteador.limites_equipe(4)
        self.assertEqual(limites,{'por_modelo':25.,'rodada':125.,'origem':'adaptativo'})
        with patch.object(ia,'postar',return_value={'message':{'content':'Resposta.'},'done':True}) as enviar:
            self.roteador.ollama('Pedido individual.')
            self.assertEqual(enviar.call_args.kwargs['timeout'],25)
            self.roteador.responder_equipe('Pedido da equipe.',modelo_ollama='llama3.2:latest',
                limite_segundos=limites['por_modelo'])
            self.assertLessEqual(enviar.call_args.kwargs['timeout'],25)

    def test_limites_de_equipe_personalizados_nao_sao_alargados(self):
        for por_modelo,rodada in (('45','50'),('10','90'),('30','60')):
            with self.subTest(por_modelo=por_modelo,rodada=rodada):
                os.environ.update({'OLLAMA_EQUIPE_TIMEOUT_MODELO':por_modelo,'OLLAMA_EQUIPE_TIMEOUT':rodada})
                self.assertEqual(self.roteador.limites_equipe(4),{'por_modelo':float(por_modelo),
                    'rodada':float(rodada),'origem':'personalizado'})

    def test_politica_legada_preserva_inclusive_padrao_gerenciado(self):
        os.environ['OLLAMA_EQUIPE_ORCAMENTO']='legado'
        self.assertEqual(self.roteador.limites_equipe(4),
            {'por_modelo':30.,'rodada':90.,'origem':'legado'})
        os.environ.update({'OLLAMA_EQUIPE_TIMEOUT_MODELO':'999','OLLAMA_EQUIPE_TIMEOUT':'999'})
        self.assertEqual(self.roteador.limites_equipe(4),
            {'por_modelo':90.,'rodada':180.,'origem':'legado'})

    def test_todos_os_orcamentos_sao_finitos_e_limitados(self):
        for total,esperado in ((1,180),(4,450),(32,900)):
            with self.subTest(total=total):
                self.assertEqual(self.roteador.limites_equipe(total)['rodada'],esperado)
        for valor,esperado in (('nan',90),('inf',90),('erro',90),('-4',5),('999',120)):
            with self.subTest(individual=valor):
                os.environ['OLLAMA_TIMEOUT']=valor
                self.assertEqual(self.roteador.limites_equipe(4)['por_modelo'],esperado)

    def test_contagem_e_politica_invalidas_nao_iniciam_geracao(self):
        with patch.object(ia,'postar') as enviar:
            for total in (0,33,True,'4',None,4.5):
                with self.subTest(total=total),self.assertRaises(ValueError):
                    self.roteador.limites_equipe(total)
            os.environ['OLLAMA_EQUIPE_ORCAMENTO']='sem-limite'
            with self.assertRaises(ia.FalhaAPI) as recebido:self.roteador.limites_equipe(4)
            self.assertEqual(recebido.exception.categoria,'configuracao')
            self.assertIn('Nenhuma geração',recebido.exception.detalhe)
            enviar.assert_not_called()

    def test_texto_parcial_sem_done_true_nao_e_entregue_como_sucesso(self):
        for done in (False,None,0,1,'true',{},[]):
            with self.subTest(done=done),patch.object(ia,'postar',return_value={
                    'message':{'content':'Trecho de uma resposta incompleta.'},'done':done}) as enviar, \
                    patch.object(self.roteador,'openai') as fallback:
                with self.assertRaises(ia.FalhaAPI) as recebido:
                    self.roteador.responder_equipe('Pedido curto.',modelo_ollama='llama3.2:latest',limite_segundos=30)
                self.assertEqual(recebido.exception.categoria,'geracao_incompleta')
                self.assertIn('pode continuar',recebido.exception.detalhe)
                self.assertNotIn('Trecho de uma resposta',str(recebido.exception))
                enviar.assert_called_once()
                fallback.assert_not_called()

    def test_done_true_e_servidor_legado_sem_campo_mantem_compatibilidade(self):
        for meta in ({'done':True},{}):
            with self.subTest(meta=meta),patch.object(ia,'postar',return_value={
                    'message':{'content':'Resposta completa.'},**meta}) as enviar:
                self.assertEqual(self.roteador.responder_equipe('Pedido curto.',
                    modelo_ollama='llama3.2:latest',limite_segundos=30),('Resposta completa.','Ollama'))
                enviar.assert_called_once()

    def test_cada_modelo_recebe_opcoes_compactas_sem_mudar_padrao(self):
        antes=dict(os.environ)
        modelos=['llama3.2:latest','qwen3.5:4b','mistral:latest','qwen3.8:27b']
        for modelo in modelos:
            with self.subTest(modelo=modelo),patch.object(ia,'postar',return_value={
                    'message':{'content':'Contribuição.'},'done':True}) as enviar:
                self.roteador.responder_equipe('Compare as opções.',modelo_ollama=modelo,limite_segundos=90)
                payload=enviar.call_args.args[2]
                self.assertEqual(payload['model'],modelo)
                self.assertEqual(payload['options'],{'num_ctx':1024,'num_predict':128,'num_gpu':0})
                self.assertIs(payload['think'],False)
                self.assertEqual(payload['keep_alive'],0)
                self.assertLessEqual(sum(len(m['content']) for m in payload['messages']),2400)
        self.assertEqual(dict(os.environ),antes)


if __name__=='__main__':unittest.main()
