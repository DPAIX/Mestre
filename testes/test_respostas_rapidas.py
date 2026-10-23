"""Respostas sociais completas não aguardam modelos nem descartam tarefas."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import interpretacao_natural as natural


class RespostasRapidas(unittest.TestCase):
    def test_cumprimentos_testes_e_agradecimentos_completos(self):
        for texto in ('Olá!','oi','Bom dia.','Boa tarde','boa noite','teste123?',
                      'TESTE 123','Teste','Test1','Você me entende?','Está aí?',
                      'Obrigada!','muito obrigado','valeu'):
            with self.subTest(texto=texto):
                resposta=natural.resposta_rapida_local(texto)
                self.assertIsInstance(resposta,str)
                self.assertTrue(resposta)

    def test_teste_de_recebimento_nao_anuncia_modelo_validado(self):
        resposta=natural.resposta_rapida_local('Teste123?')
        self.assertIn('mensagem chegou',resposta)
        self.assertNotIn('modelos responderam',resposta)
        self.assertNotIn('APIs funcionando',resposta)

    def test_tarefas_e_pedidos_compostos_nao_sao_confundidos_com_social(self):
        for texto in ('Olá, abra o VS Code','teste a conexão Ollama','teste os modelos',
                      'obrigado e registre um gasto','oi; abra a calculadora',
                      'oi\nmostre minha rotina','"teste123?"','/teste','Como testar?',
                      'Não faça um teste','Teste este código','teste123456789',
                      '{"resposta":"oi"}',None,[],100,' '):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.resposta_rapida_local(texto))

    def test_recebimento_local_preserva_conversa_sem_catalogo_ou_geracao(self):
        chat={'id':'fixture-chat'}
        with patch.object(app.CENTRAL,'obter_chat_ativo',return_value=chat), \
                patch.object(app.CENTRAL,'registrar_troca') as registrar, \
                patch.object(app.SERVICOS,'conversar') as conversar, \
                patch.object(app.ROTEADOR,'catalogo_ollama') as catalogo:
            resultado=app.preparar_pedido_natural('teste123?','fixture-contexto')
        conversar.assert_not_called()
        catalogo.assert_not_called()
        self.assertIsNone(resultado['plano'])
        self.assertEqual(resultado['chat_id'],'fixture-chat')
        registrar.assert_called_once_with('fixture-contexto','teste123?',resultado['mensagem'],'auto',chat_id='fixture-chat')

    def test_saudacao_com_pedido_segue_interpretacao_normal(self):
        chat={'id':'fixture-chat'}
        texto='Olá, explique uma maneira de estudar melhor'
        with patch.object(app.CENTRAL,'obter_chat_ativo',return_value=chat), \
                patch.object(app.SERVICOS,'conversar',return_value={
                    'texto':'Resposta da equipe.','plano':None,'chat_id':'fixture-chat'}) as conversar:
            resultado=app.preparar_pedido_natural(texto,'fixture-contexto')
        conversar.assert_called_once_with(texto,'fixture-contexto',app.ROTEADOR,retornar_plano=True)
        self.assertEqual(resultado['mensagem'],'Resposta da equipe.')


if __name__=='__main__':unittest.main()
