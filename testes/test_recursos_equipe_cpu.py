"""Limites CPU da equipe; catálogo e geração são somente fixtures em memória."""
from __future__ import annotations

import copy
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import multi_ia as ia


MODELOS = ('qwen3.8:27b', 'mistral:latest', 'llama3.2:latest', 'qwen3.5:4b')


class RecursosEquipeCpu(unittest.TestCase):
    def setUp(self):
        ambiente = patch.dict(os.environ, {
            'OLLAMA_HABILITADO': '1', 'OLLAMA_MODEL': 'llama3.2:latest',
            'OLLAMA_URL': 'http://127.0.0.1:11434', 'OLLAMA_PERFIL': 'cpu',
        }, clear=True)
        ambiente.start(); self.addCleanup(ambiente.stop)
        for alvo, valor in (('ler_json', {}), ('gravar_json', None), ('registrar', None)):
            p = patch.object(ia, alvo, return_value=valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.object(configurar, 'listar_catalogo', return_value=[
            {'nome': nome, 'nuvem': False} for nome in MODELOS])
        self.catalogo = p.start(); self.addCleanup(p.stop)
        self.roteador = ia.Roteador()

    def gerar(self, modelo='llama3.2:latest', **opcoes):
        with patch.object(ia, 'postar', return_value={'message': {'content': 'Resposta local.'}}) as enviar:
            resposta = self.roteador.responder('Uma pergunta curta', provedor='Ollama',
                modelo_ollama=modelo, **opcoes)
        self.assertEqual(resposta, ('Resposta local.', 'Ollama'))
        enviar.assert_called_once()
        return enviar.call_args

    def test_cooperativa_cpu_preserva_mesmos_limites_do_individual(self):
        individual = copy.deepcopy(self.gerar().args[2])
        cooperativo = self.gerar(modo_cooperativo=True).args[2]
        self.assertEqual(cooperativo['options'], individual['options'])
        self.assertEqual(cooperativo['options'], {'num_gpu': 0, 'num_ctx': 1024, 'num_predict': 128})
        self.assertEqual(cooperativo['keep_alive'], 0)
        self.assertIs(cooperativo['think'], False)
        self.assertNotIn('think', individual)

    def test_cada_tag_da_equipe_usa_cpu_compacto_sem_mudar_padrao(self):
        antes = os.environ.copy()
        for modelo in MODELOS:
            with self.subTest(modelo=modelo):
                payload = self.gerar(modelo, modo_cooperativo=True).args[2]
                self.assertEqual(payload['model'], modelo)
                self.assertEqual(payload['options'], {'num_gpu': 0, 'num_ctx': 1024, 'num_predict': 128})
                self.assertIs(payload['stream'], False)
                self.assertEqual(payload['keep_alive'], 0)
                self.assertIs(payload['think'], False)
        self.assertEqual(os.environ.copy(), antes)

    def test_cooperativa_padrao_mantem_orcamento_proprio_sem_forcar_gpu(self):
        os.environ['OLLAMA_PERFIL'] = 'padrao'
        payload = self.gerar(modo_cooperativo=True).args[2]
        self.assertEqual(payload['options'], {'num_ctx': 4096, 'num_predict': 384})
        self.assertEqual(payload['keep_alive'], 0)
        self.assertNotIn('num_gpu', payload['options'])
        self.assertIs(payload['think'], False)

    def test_perfil_invalido_nao_tenta_geracao_ou_fallback(self):
        os.environ['OLLAMA_PERFIL'] = 'perfil-desconhecido'
        with patch.object(ia, 'postar') as enviar, \
                patch.object(self.roteador, 'openai') as pago:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.responder('Pergunta', provedor='Ollama',
                    modelo_ollama=MODELOS[0], modo_cooperativo=True)
        self.assertEqual(erro.exception.categoria, 'configuracao')
        enviar.assert_not_called()
        pago.assert_not_called()

    def test_tag_cloud_no_perfil_cpu_nao_dispara_geracao(self):
        self.catalogo.return_value = [{'nome': MODELOS[0], 'nuvem': True}]
        with patch.object(ia, 'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.responder('Pergunta', provedor='Ollama',
                    modelo_ollama=MODELOS[0], modo_cooperativo=True)
        self.assertEqual(erro.exception.categoria, 'configuracao')
        enviar.assert_not_called()

    def test_timeout_de_geracao_nao_repete_chamada_nem_chama_provedor_pago(self):
        with patch.object(ia, 'postar', side_effect=ia.FalhaAPI('Ollama', 0,
                'Tempo da fixture expirou.', 'rede')) as enviar, \
                patch.object(self.roteador, 'openai') as pago:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.responder('Pergunta', provedor='Ollama',
                    modelo_ollama='llama3.2:latest', modo_cooperativo=True)
        self.assertEqual(erro.exception.categoria, 'rede')
        enviar.assert_called_once()
        pago.assert_not_called()

    def test_historico_extenso_nao_expulsa_pedido_atual_no_cpu_cooperativo(self):
        pergunta='Regras do assistente. '+('contexto '*200)+' ÚLTIMO PEDIDO: compare as opções.'
        historico=[{'role':'user','content':'Mensagem antiga. '*1000},
                   {'role':'assistant','content':'Resposta antiga. '*1000}]
        antes=copy.deepcopy(historico)
        with patch.object(ia,'postar',return_value={'message':{'content':'Contribuição curta.'}}) as enviar:
            self.roteador.ollama(pergunta,historico=historico,modo_cooperativo=True)
        mensagens=enviar.call_args.args[2]['messages']
        self.assertEqual(mensagens[-1],{'role':'user','content':pergunta})
        self.assertLessEqual(sum(len(m['content']) for m in mensagens),2400)
        self.assertLessEqual(sum(len(m['content']) for m in mensagens[1:-1]),600)
        self.assertEqual(historico,antes)

    def test_pedido_grande_no_cpu_nao_vira_um_pedido_parcial_por_corte_adicional(self):
        pergunta='Regras do assistente. '+('x'*5000)+' ÚLTIMO PEDIDO INTEIRO.'
        historico=[{'role':'assistant','content':'Contexto antigo.'}]
        with patch.object(ia,'postar',return_value={'message':{'content':'Contribuição.'}}) as enviar:
            self.roteador.ollama(pergunta,historico=historico,modo_cooperativo=True)
        mensagens=enviar.call_args.args[2]['messages']
        self.assertEqual(len(mensagens),2)
        self.assertEqual(mensagens[-1]['content'],pergunta)

    def test_cpu_individual_preserva_historico_anterior(self):
        historico=[{'role':'user','content':'Pergunta anterior. '*200}]
        with patch.object(ia,'postar',return_value={'message':{'content':'Resposta.'}}) as enviar:
            self.roteador.ollama('Pedido atual.',historico=historico)
        self.assertEqual(enviar.call_args.args[2]['messages'][1:-1],historico)

    def test_timeout_nao_afirma_que_servico_ou_rede_parou(self):
        with patch.object(ia,'postar',side_effect=ia.FalhaAPI('Ollama',0,'timed out','rede')) as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.ollama('Pedido.',modo_cooperativo=True)
        self.assertIn('prazo de resposta',erro.exception.detalhe)
        self.assertIn('não comprova falha de rede',erro.exception.detalhe)
        self.assertIn('Nenhuma nova tentativa',erro.exception.detalhe)
        enviar.assert_called_once()


if __name__ == '__main__':
    unittest.main()
