"""Limite de saída observado em respostas HTTP fictícias, sem inferência real."""
import os
import unittest
from unittest.mock import patch

import configurar_ia_local as configurar
import multi_ia as ia


class OllamaTruncamento2121(unittest.TestCase):
    def setUp(self):
        for contexto in (
            patch.dict(os.environ, {'OLLAMA_HABILITADO':'1', 'OLLAMA_PERFIL':'cpu',
                'OLLAMA_URL':'http://127.0.0.1:11434', 'OLLAMA_MODEL':'llama3.2:latest'}, clear=True),
            patch.object(ia, 'ler_json', return_value={}),
            patch.object(ia, 'gravar_json'), patch.object(ia, 'registrar'),
            patch.object(configurar, 'listar_catalogo', return_value=[
                {'nome':'llama3.2:latest', 'nuvem':False}]),
        ):
            contexto.start()
            self.addCleanup(contexto.stop)
        self.roteador=ia.Roteador()

    def test_limite_length_nao_entrega_trecho_como_resposta_completa(self):
        for cooperativo in (False, True):
            with self.subTest(cooperativo=cooperativo), patch.object(ia, 'postar', return_value={
                    'done':True, 'done_reason':'length', 'message':{'content':'trecho privado da resposta'}}) as enviar:
                with self.assertRaises(ia.FalhaAPI) as erro:
                    self.roteador.responder('Pedido', provedor='Ollama',
                        modelo_ollama='llama3.2:latest', modo_cooperativo=cooperativo)
                self.assertEqual(erro.exception.categoria,'resposta_truncada')
                self.assertNotIn('trecho privado',str(erro.exception))
                self.assertIn('Nenhuma ação',str(erro.exception))
                enviar.assert_called_once()

    def test_done_false_prevalece_sobre_length_sem_afirmar_conclusao(self):
        with patch.object(ia,'postar',return_value={
                'done':False,'done_reason':'length','message':{'content':'Trecho'}}) as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.responder_equipe('Pedido',modelo_ollama='llama3.2:latest',limite_segundos=90)
        self.assertEqual(erro.exception.categoria,'geracao_incompleta')
        self.assertIn('pode continuar',str(erro.exception))
        enviar.assert_called_once()

    def test_parada_normal_e_resposta_legada_continuam_validas(self):
        for meta in ({'done':True,'done_reason':'stop'}, {'done':True}, {}):
            with self.subTest(meta=meta), patch.object(ia,'postar',return_value={
                    'message':{'content':'Texto completo.'},**meta}) as enviar:
                self.assertEqual(self.roteador.responder_equipe('Pedido',
                    modelo_ollama='llama3.2:latest',limite_segundos=90),('Texto completo.','Ollama'))
                enviar.assert_called_once()


if __name__=='__main__':
    unittest.main()
