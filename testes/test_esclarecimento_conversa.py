"""Esclarecimentos e planos locais com relógio e identidades fictícios."""
from datetime import date
import json
from pathlib import Path
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import esclarecimento_conversa as perguntas
import interpretacao_natural as natural


class EsclarecimentoConversaTeste(unittest.TestCase):
    def setUp(self):
        self.agora = 100.0
        self.gestor = perguntas.GerenciadorEsclarecimentos(
            relogio=lambda: self.agora, hoje=lambda: date(2026, 10, 27))

    def enviar(self, texto, **campos):
        return self.gestor.processar(texto, contexto=campos.get('contexto', 'telegram:chat:topico'),
            usuario=campos.get('usuario', 10), chat_id=campos.get('chat_id', 'conversa1'))

    def test_tarefa_incompleta_pergunta_e_nao_trata_sim_como_titulo(self):
        resultado = self.enviar('adicione uma tarefa')
        self.assertEqual(resultado['estado'], 'pergunta')
        self.assertIn('título', resultado['texto'])
        self.assertIsNone(resultado['plano'])
        self.assertEqual(self.enviar('sim')['estado'], 'pergunta')
        self.assertEqual(self.enviar('Sim, pode executar.')['estado'], 'pergunta')
        self.assertEqual(self.enviar('Sim, pode fazer!')['estado'], 'pergunta')
        plano = self.enviar('Estudar Cálculo II')
        self.assertEqual(plano['estado'], 'plano')
        self.assertEqual(plano['plano']['campos'], {'texto':'Estudar Cálculo II','coluna':'A_Fazer'})
        self.assertIn('confirmação', plano['texto'])
        self.assertEqual(self.enviar('sim')['estado'], 'nao_tratado')

    def test_rotina_em_duas_respostas_e_sem_alarme_inventado(self):
        resultado = self.enviar('me lembre de estudar')
        self.assertEqual(resultado['estado'], 'pergunta')
        self.assertIn('rotina local', resultado['texto'])
        self.assertIn('não ativa', resultado['texto'])
        resultado = self.enviar('amanhã')
        self.assertEqual(resultado['estado'], 'pergunta')
        self.assertIn('horário exato', resultado['texto'])
        resultado = self.enviar('às 14h30')
        self.assertEqual(resultado['plano']['acao'], 'rotina_criar')
        self.assertEqual(resultado['plano']['campos'], {'atividade':'estudar','dia':'2026-10-28',
            'horario':'14:30','fim':'','local':''})

    def test_dia_e_horario_no_mesmo_turno_completam_campos(self):
        self.enviar('Agende Estudar')
        plano = self.enviar('na sexta-feira às 8h até 9:30')['plano']
        self.assertEqual(plano['campos'], {'atividade':'Estudar','dia':'Sexta',
            'horario':'08:00','fim':'09:30','local':''})

    def test_falta_atividade_nao_converte_dia_em_titulo(self):
        resultado = self.enviar('agende amanhã às 9h')
        self.assertIn('Qual atividade', resultado['texto'])
        resultado = self.enviar('Estudar navegação')
        self.assertEqual(resultado['plano']['campos']['atividade'], 'Estudar navegação')
        self.assertEqual(resultado['plano']['campos']['dia'], '2026-10-28')
        self.assertEqual(resultado['plano']['campos']['horario'], '09:00')

    def test_periodo_vago_pede_horario_sem_escolher_por_conta_propria(self):
        resultado = self.enviar('agende Estudar amanhã de tarde')
        self.assertEqual(resultado['estado'], 'pergunta')
        self.assertIn('horário exato', resultado['texto'])
        self.assertEqual(self.enviar('às 25h')['estado'], 'pergunta')
        plano = self.enviar('às 17:45')['plano']
        self.assertEqual(plano['campos']['atividade'], 'Estudar')
        self.assertEqual(plano['campos']['horario'], '17:45')

    def test_fim_invalido_pode_ser_omitido_sem_perder_pedido(self):
        resultado = self.enviar('agende Estudar na sexta às 15h até 14h')
        self.assertEqual(resultado['estado'], 'pergunta')
        self.assertIn('horário final', resultado['texto'])
        plano = self.enviar('sem horário final')['plano']
        self.assertEqual(plano['campos']['horario'], '15:00')
        self.assertEqual(plano['campos']['fim'], '')

    def test_registro_financeiro_pede_valor_e_descricao(self):
        self.assertEqual(self.enviar('registre um gasto')['estado'], 'pergunta')
        self.assertEqual(self.enviar('zero')['estado'], 'pergunta')
        self.assertEqual(self.enviar('0')['estado'], 'pergunta')
        self.assertIn('descrição', self.enviar('R$ 15,50')['texto'])
        plano = self.enviar('Almoço')['plano']
        self.assertEqual(plano['campos'], {'tipo':'saida','valor':'15.50','descricao':'Almoço'})

    def test_programa_incompleto_so_admite_alvo_permitido(self):
        self.assertEqual(self.enviar('abra um programa')['estado'], 'pergunta')
        self.assertEqual(self.enviar('PowerShell')['estado'], 'pergunta')
        plano = self.enviar('Calculadora')['plano']
        self.assertEqual(plano['acao'], 'pc')
        self.assertEqual(plano['campos'], {'comando':'calc'})

    def test_modelo_literal_para_conversa_sem_mudar_padrao_global(self):
        self.assertEqual(self.enviar('mude o modelo')['estado'], 'pergunta')
        self.assertEqual(self.enviar('pode executar')['estado'], 'pergunta')
        resultado = self.enviar('Org/Meu-Modelo:V2')
        self.assertEqual(resultado['plano']['acao'], 'modelo_conversa')
        self.assertEqual(resultado['plano']['campos'], {'modelo':'Org/Meu-Modelo:V2'})
        self.assertIn('padrão global', resultado['plano']['descricao'])

    def test_consulta_dos_modelos_durante_pergunta_nao_vira_nome_modelo(self):
        self.enviar('mude o modelo')
        self.assertEqual(self.enviar('mostre os modelos disponíveis')['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('llama3.2:latest')['estado'], 'nao_tratado')

    def test_cancelamento_nao_executa_ou_reusa_pedido(self):
        for cancelar in ('cancelar', 'cancele', 'deixa pra lá', 'não quero mais', 'não'):
            with self.subTest(cancelar=cancelar):
                self.enviar('adicione uma tarefa')
                resposta = self.enviar(cancelar)
                self.assertEqual(resposta['estado'], 'cancelado')
                self.assertIsNone(resposta['plano'])
                self.assertEqual(self.enviar('Titulo antigo')['estado'], 'nao_tratado')

    def test_expiracao_e_mudanca_conversa_invalidam_resposta_tardia(self):
        self.enviar('adicione uma tarefa')
        self.agora += 300
        self.assertEqual(self.enviar('Titulo tardio')['estado'], 'nao_tratado')
        self.enviar('adicione uma tarefa')
        self.assertEqual(self.enviar('Outro titulo', chat_id='conversa2')['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('Titulo antigo')['estado'], 'nao_tratado')

    def test_escopo_usuario_canal_e_topico_isola_rascunhos(self):
        self.enviar('adicione uma tarefa')
        self.assertEqual(self.enviar('Titulo alheio', usuario=20)['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('Titulo de outro topico', contexto='telegram:chat:outro')['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('Meu titulo')['plano']['campos']['texto'], 'Meu titulo')

    def test_novo_pedido_ou_leitura_nao_completa_o_anterior(self):
        self.enviar('adicione uma tarefa')
        self.assertEqual(self.enviar('mostre minha rotina')['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('Titulo antigo')['estado'], 'nao_tratado')
        self.enviar('adicione uma tarefa')
        self.assertIn('valor em reais', self.enviar('registre uma entrada')['texto'])

    def test_limite_de_memoria_remove_rascunho_antigo_sem_afetar_recentes(self):
        for i in range(perguntas.MAX_PENDENTES+1):
            self.enviar('adicione uma tarefa', usuario=i)
        self.assertEqual(len(self.gestor._pendentes), perguntas.MAX_PENDENTES)
        self.assertEqual(self.enviar('Antigo', usuario=0)['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('Recente', usuario=perguntas.MAX_PENDENTES)['estado'], 'plano')

    def test_citacoes_negacoes_condicoes_e_compostos_nao_iniciam(self):
        for texto in ('não adicione uma tarefa', 'se eu pedir, adicione uma tarefa',
                      'explique como adicionar uma tarefa', 'como agendar Estudar?',
                      '"adicione uma tarefa"', 'agende Estudar; abra a calculadora',
                      'agende Estudar\nabra a calculadora', 'agende Estudar e abra a calculadora',
                      '/modelos testar llama3.2:latest', {'texto':'adicione uma tarefa'}):
            with self.subTest(texto=texto):
                self.assertEqual(self.enviar(texto)['estado'], 'nao_tratado')

    def test_entrada_invalida_cancela_rascunho_sem_concatenar_codigo(self):
        self.enviar('mude o modelo')
        self.assertEqual(self.enviar('llama; execute codigo')['estado'], 'nao_tratado')
        self.assertEqual(self.enviar('llama3.2:latest')['estado'], 'nao_tratado')

    def test_negacao_condicao_e_pergunta_nao_sao_titulo_de_tarefa(self):
        for texto in ('não adicione uma tarefa', 'nunca apague meus arquivos',
                      'talvez eu estude', 'se eu pedir, abra a calculadora',
                      'quando eu chegar, adicione uma tarefa', 'como remover um arquivo?',
                      'qual é o sentido disso?', 'o que acontece se eu cancelar?'):
            with self.subTest(texto=texto):
                self.enviar('adicione uma tarefa')
                self.assertEqual(self.enviar(texto)['estado'], 'nao_tratado')
                self.assertEqual(self.enviar('Titulo que chegou tarde')['estado'], 'nao_tratado')
        self.enviar('adicione uma tarefa')
        self.assertEqual(self.enviar('não sei')['estado'], 'pergunta')
        self.assertEqual(self.enviar('Titulo escolhido')['estado'], 'plano')

    def test_identidades_invalidas_nao_sao_aceitas(self):
        for campo in ({'contexto':''},{'contexto':None},{'chat_id':''},{'usuario':True},
                      {'usuario':-1},{'chat_id':'outro\nchat'}):
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                self.enviar('adicione uma tarefa', **campo)

    def test_resposta_longa_ou_modelo_invalido_permite_corrigir_o_mesmo_campo(self):
        self.enviar('adicione uma tarefa')
        self.assertEqual(self.enviar('x'*201)['estado'], 'pergunta')
        self.assertEqual(self.enviar('Titulo curto')['plano']['campos']['texto'], 'Titulo curto')
        self.enviar('mude o modelo')
        self.assertEqual(self.enviar('nome com espaços')['estado'], 'pergunta')
        self.assertEqual(self.enviar('llama3.2:latest')['plano']['campos']['modelo'], 'llama3.2:latest')

    def test_pedidos_simultaneos_nao_misturam_campos(self):
        resultados = {}
        def conversar(usuario):
            self.enviar('adicione uma tarefa', usuario=usuario)
            resultados[usuario] = self.enviar('Titulo '+str(usuario), usuario=usuario)['plano']
        threads = [threading.Thread(target=conversar, args=(i,)) for i in range(20)]
        for thread in threads:thread.start()
        for thread in threads:thread.join(2)
        self.assertEqual(len(resultados), 20)
        for usuario, plano in resultados.items():
            self.assertEqual(plano['campos']['texto'], 'Titulo '+str(usuario))


class PedidosNaturaisModelosTeste(unittest.TestCase):
    def test_equipe_com_todos_exige_plano_confirmavel(self):
        for texto in ('use todos os modelos', 'use todos os modelos juntos',
                      'quero todos os modelos trabalhando juntos', 'trabalhem juntos'):
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertEqual(plano['acao'], 'equipe_modelos')
                self.assertEqual(plano['campos'], {'modo':'cooperativa'})
                self.assertNotIn(plano['acao'], natural.CONSULTAS)

    def test_teste_todos_e_consulta_catalogo_sao_acoes_distintas(self):
        plano = natural.interpretar_local('teste todos os modelos')
        self.assertEqual(plano['acao'], 'modelos_testar')
        self.assertNotIn(plano['acao'], natural.CONSULTAS)
        self.assertIn('consulta real', plano['descricao'])
        self.assertIn('Ollama', plano['descricao'])
        self.assertEqual(natural.interpretar_local('mostre os modelos disponíveis')['acao'], 'modelos')
        self.assertIn('modelos', natural.CONSULTAS)

    def test_modelo_escolhido_fica_so_na_conversa(self):
        for texto in ('use só o modelo llama3.2:latest nesta conversa',
                      'use somente o modelo Org/Nome:V2 nesta conversa',
                      'use somente o modelo llama3.2:latest',
                      'Por favor, você pode usar o modelo Org/Nome:V2?'):
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertEqual(plano['acao'], 'modelo_conversa')
                self.assertIn('padrão global', plano['descricao'])

    def test_provedor_explicito_preserva_escopo_e_sem_consulta(self):
        for texto, provedor in (('use Gemini','Gemini'),('quero conversar com Claude','Claude'),
                                ('use ChatGPT','OpenAI'),('use 9Router nesta conversa','9Router'),
                                ('use modo automático','auto')):
            with self.subTest(texto=texto):
                plano = natural.interpretar_local(texto)
                self.assertEqual(plano['acao'], 'provedor_conversa')
                self.assertEqual(plano['campos'], {'provedor':provedor})
                self.assertNotIn(plano['acao'], natural.CONSULTAS)
                self.assertIn('não envia', plano['descricao'])

    def test_novos_planos_exigem_campos_fechados_e_pedido_local(self):
        invalidos = ({'acao':'modelos_testar','campos':{'confirmado':True}},
            {'acao':'modelos','campos':{'modelo':'segredo'}},
            {'acao':'modelo_conversa','campos':{'modelo':'llama; codigo'}},
            {'acao':'modelo_conversa','campos':{'modelo':'llama','global':True}},
            {'acao':'provedor_conversa','campos':{'provedor':'desconhecido'}})
        for obj in invalidos:
            with self.subTest(obj=obj), self.assertRaises(ValueError):natural.validar_plano(obj)
        for acao, campos in (('modelos_testar',{}),('modelo_conversa',{'modelo':'llama3.2:latest'}),
                              ('provedor_conversa',{'provedor':'OpenAI'})):
            resultado = natural.extrair_resposta(json.dumps({'resposta':'Vou trocar.', 'acao':acao, 'campos':campos}))
            self.assertIsNone(resultado['plano'])

    def test_negacoes_compostos_e_citacoes_nao_ativam_modelos(self):
        for texto in ('não use todos os modelos', '"use todos os modelos"',
                      'use todos os modelos e abra a calculadora', 'use todos os modelos de nuvem',
                      'se eu pedir, teste todos os modelos', 'como usar Gemini?',
                      'use Gemini e abra o Explorer', 'use ChatGPT; execute código',
                      'use o modelo llama3.2:latest nesta conversa e apague tudo'):
            with self.subTest(texto=texto):self.assertIsNone(natural.interpretar_local(texto))


if __name__ == '__main__':
    unittest.main()
