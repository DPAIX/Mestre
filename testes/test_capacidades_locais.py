"""Capacidades locais e confirmação preservadas, sem dados ou APIs reais."""
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import interpretacao_natural as natural
import nucleo


class CapacidadesLocais(unittest.TestCase):
    def test_frase_da_imagem_e_variantes_completas(self):
        for texto in ('me fale suas capacidades','Quais são suas capacidades?',
                      'quais são as suas capacidades?','O que você pode fazer?',
                      'o que você faz?','como você pode me ajudar?',
                      'Me fale as suas capacidades.','quais são suas funções?',
                      'Por favor, me fale suas capacidades!',
                      'Me   fale suas capacidades?'):
            with self.subTest(texto=texto):
                self.assertEqual(natural.resposta_rapida_local(texto),natural.texto_capacidades())

    def test_descricao_pura_nao_fabrica_estado_ou_disponibilidade(self):
        with patch.object(nucleo,'vida',side_effect=AssertionError('Não ler registros privados.')), \
                patch.object(app.ROTEADOR,'catalogo_ollama',side_effect=AssertionError('Não consultar serviço.')):
            texto=natural.texto_capacidades()
        for trecho in ('Rotina local','Finanças','Kanban','Hábitos e foco','Windows e RoboTask',
                       'leitura da agenda Google quando autorizada','Ollama disponíveis',
                       'dependências estiverem prontos','confirmação','não verifica a conexão'):
            self.assertIn(trecho,texto)
        for trecho in ('Estou online','íntegro','2–4s','controlar tudo','atividades pendentes',
                       'APIs funcionando','seu saldo agora'):
            self.assertNotIn(trecho,texto)

    def test_compostos_negacoes_e_citacoes_seguem_fluxo_normal(self):
        for texto in ('Não me fale suas capacidades','me fale suas capacidades e registre um gasto',
                      'me fale suas capacidades; abra a calculadora',
                      'me fale suas capacidades\napague as tarefas',
                      '"me fale suas capacidades"','`me fale suas capacidades`',
                      '/me fale suas capacidades','me fale suas capacidades de programação',
                      'explique a frase me fale suas capacidades',
                      'como você pode me ajudar a resolver esta questão?',
                      'Se eu pedir me fale suas capacidades','me fale suas capacidades, depois reinicie',
                      '{"mensagem":"me fale suas capacidades"}'):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.resposta_rapida_local(texto))

    def test_capacidades_na_conversa_nao_consultam_modelos_e_preservam_historico(self):
        chat={'id':'fixture-chat'}
        progresso=Mock()
        with patch.object(app.CENTRAL,'obter_chat_ativo',return_value=chat), \
                patch.object(app.CENTRAL,'registrar_troca') as registrar, \
                patch.object(app.SERVICOS,'conversar') as conversar, \
                patch.object(app.ROTEADOR,'catalogo_ollama') as catalogo, \
                patch.object(app,'executar_plano_natural') as executar:
            resultado=app.preparar_pedido_natural('me fale suas capacidades','fixture-contexto',progresso=progresso)
        self.assertEqual(resultado,{'mensagem':natural.texto_capacidades(),'plano':None,'chat_id':'fixture-chat'})
        registrar.assert_called_once_with('fixture-contexto','me fale suas capacidades',
                                         natural.texto_capacidades(),'auto',chat_id='fixture-chat')
        conversar.assert_not_called();catalogo.assert_not_called()
        executar.assert_not_called();progresso.assert_not_called()

    def test_exemplos_de_alteracao_preparam_plano_sem_execucao(self):
        exemplos=(('agende estudar na sexta às 14:00','rotina_criar'),
                  ('gastei 15,50 com almoço','financeiro'),
                  ('adicione tarefa estudar cálculo','kanban_adicionar'),
                  ('bebi um copo de água','agua'),('iniciar pomodoro','pomodoro'),
                  ('abra o VS Code','pc'),('pressione F8','pc'))
        for texto,acao in exemplos:
            with self.subTest(texto=texto), \
                    patch.object(app.CENTRAL,'obter_chat_ativo',return_value={'id':'fixture-chat'}), \
                    patch.object(app,'executar_plano_natural') as executar, \
                    patch.object(app.SERVICOS,'conversar') as conversar:
                resultado=app.preparar_pedido_natural(texto,'fixture-contexto')
                self.assertEqual(resultado['plano']['acao'],acao)
                self.assertEqual(resultado['chat_id'],'fixture-chat')
                executar.assert_not_called();conversar.assert_not_called()

    def test_pergunta_aberta_mantem_assinatura_sem_chat_id_no_fallback(self):
        texto='Me fale das capacidades de uma placa de vídeo'
        progresso=Mock()
        with patch.object(app.CENTRAL,'obter_chat_ativo',return_value={'id':'fixture-chat'}), \
                patch.object(app.SERVICOS,'conversar',return_value={
                    'texto':'Resposta da equipe.','plano':None,'chat_id':'fixture-chat'}) as conversar:
            resultado=app.preparar_pedido_natural(texto,'fixture-contexto',progresso=progresso)
        conversar.assert_called_once_with(texto,'fixture-contexto',app.ROTEADOR,
                                         retornar_plano=True,progresso=progresso)
        self.assertEqual(resultado['mensagem'],'Resposta da equipe.')

    def test_falha_de_ia_nao_e_mascarada_por_uma_lista_de_capacidades(self):
        with patch.object(app.CENTRAL,'obter_chat_ativo',return_value={'id':'fixture-chat'}), \
                patch.object(app.SERVICOS,'conversar',side_effect=app.FalhaAPI('Ollama',0,'fixture indisponível','rede')):
            resultado=app.preparar_pedido_natural('Explique funções em Python','fixture-contexto')
        self.assertIn('fixture indisponível',resultado['mensagem'])
        self.assertNotEqual(resultado['mensagem'],natural.texto_capacidades())
        self.assertIsNone(resultado['plano'])


if __name__=='__main__':unittest.main()
