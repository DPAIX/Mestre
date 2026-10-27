"""Formato de conversa e respostas locais; sem inferência, rede ou dados de uso."""
import json
import copy
from unittest.mock import patch
from unittest.mock import Mock
import unittest

import assistente_pc as app
import interpretacao_natural as natural
import servicos_chat as servicos
from multi_ia import FalhaAPI


class FormatoConversa2121(unittest.TestCase):
    def conversar_individual(self, retorno, registrar):
        chat={'id':'fixture','titulo':'Conversa fictícia','equipe_politica':'manual',
              'provedor':'Ollama','modelo_ollama':'llama3.2:latest','equipe_paralela':False}
        roteador=Mock()
        roteador.responder.return_value=(retorno,'Ollama')
        with patch.object(servicos, '_TRAVAS', {}), \
                patch.object(servicos.central, 'obter_chat_ativo', return_value=chat), \
                patch.object(servicos.central, 'historico_chat', return_value=[]), \
                patch.object(servicos.central, 'registrar_troca', registrar), \
                patch('memoria_assistente.contexto_seguro', return_value={'texto':'','aviso':''}):
            resultado=servicos.conversar('Explique uma ideia.', 'fixture-contexto', roteador,
                retornar_plano=True)
        roteador.responder.assert_called_once()
        return resultado

    def test_pergunta_real_de_capacidades_e_variantes_sao_locais(self):
        for texto in ('me diga do que você é capaz', 'Do que você é capaz?',
                'de que você é capaz', 'O que você é capaz de fazer?',
                'Me diga do que você é capaz de fazer.',
                'Por favor, me diga do que você é capaz!',
                'Você pode me dizer do que você é capaz?',
                'Vc consegue me dizer de que você é capaz?'):
            with self.subTest(texto=texto):
                self.assertEqual(natural.resposta_rapida_local(texto), natural.texto_capacidades())

    def test_qualificadores_e_outros_pedidos_nao_sao_descartados(self):
        for texto in ('me diga do que você é capaz em programação',
                'do que você é capaz com esse arquivo?',
                'não me diga do que você é capaz',
                'se eu pedir, me diga do que você é capaz',
                'me diga do que você é capaz e abra a calculadora',
                'me diga do que você é capaz; registre um gasto',
                '"me diga do que você é capaz"',
                'me diga do que você é capaz\nabra o VS Code',
                'O que você é capaz de fazer para controlar outro PC?'):
            with self.subTest(texto=texto):
                self.assertIsNone(natural.resposta_rapida_local(texto))

    def test_frase_real_na_interface_nao_mobiliza_equipe_nem_fabrica_estado(self):
        texto = 'me diga do que você é capaz'
        with patch.object(app.CENTRAL, 'obter_chat_ativo', return_value={'id': 'fixture'}), \
                patch.object(app.CENTRAL, 'registrar_troca') as registrar, \
                patch.object(app.SERVICOS, 'conversar') as conversar, \
                patch.object(app.ROTEADOR, 'catalogo_ollama') as catalogo:
            resultado = app.preparar_pedido_natural(texto, 'fixture-contexto')
        self.assertEqual(resultado['mensagem'], natural.texto_capacidades())
        self.assertIsNone(resultado['plano'])
        conversar.assert_not_called()
        catalogo.assert_not_called()
        registrar.assert_called_once_with('fixture-contexto', texto, natural.texto_capacidades(),
            'auto', chat_id='fixture')

    def test_instrucoes_separam_conversa_textual_e_proposta_json(self):
        for compacto in (False, True):
            with self.subTest(compacto=compacto):
                texto = natural.instrucoes_ia(compacto=compacto)
                self.assertIn('texto comum', texto)
                self.assertIn('sem JSON', texto)
                self.assertIn('proposta de ação' if compacto else 'propor uma ação', texto)
                self.assertIn('confirmação', texto)
                self.assertIn('campos', texto)
                self.assertNotIn('Retorne só JSON', texto)
        self.assertLess(len(natural.instrucoes_ia(compacto=True)), 1100)

    def test_texto_simples_continua_conversa_valida_sem_plano(self):
        for texto in ('Posso ajudar a organizar seus estudos.', 'Como prefere dividir o trabalho?',
                'Exemplo de dados: {"nome":"Estudar"}', '```python\nprint("exemplo")\n```'):
            with self.subTest(texto=texto):
                self.assertEqual(natural.extrair_resposta(texto, estrito=True),
                    {'texto': texto, 'plano': None})

    def test_json_inerte_valido_e_plano_valido_mantem_contratos(self):
        conversa = {'resposta': 'Posso ajudar.', 'acao': None, 'campos': {}}
        self.assertEqual(natural.extrair_resposta(json.dumps(conversa), estrito=True),
            {'texto': 'Posso ajudar.', 'plano': None})
        proposta = {'resposta': 'Proponho abrir a calculadora.', 'acao': 'pc', 'campos': {'comando': 'calc'}}
        resultado = natural.extrair_resposta(json.dumps(proposta), estrito=True)
        self.assertEqual(resultado['plano']['campos'], {'comando': 'calc'})
        self.assertIn('abrir a Calculadora', resultado['plano']['descricao'])

    def test_json_de_exemplo_sem_envelope_nunca_vira_acao(self):
        for texto in ('{"nome":"Reunião","horario":"14:00"}',
                '```json\n{"nome":"Reunião","horario":"14:00"}\n```',
                '```json\n[{"nome":"Reunião"}]\n```'):
            with self.subTest(texto=texto):
                self.assertEqual(natural.extrair_resposta(texto, estrito=True),
                    {'texto': texto, 'plano': None})

    def test_json_truncado_nao_gera_aviso_local_como_resposta_do_modelo(self):
        casos = ('{"resposta":"Contribuição", "acao":',
                 '```json\n{"resposta":"Contribuição", "acao":',
                 '```\n{"resposta":"Contribuição", "acao":',
                 '```json', '```json{', '```json\ntexto inválido\n```')
        for texto in casos:
            with self.subTest(texto=texto), self.assertRaises(natural.RespostaModeloInvalida) as recebido:
                natural.extrair_resposta(texto, estrito=True)
            self.assertEqual(recebido.exception.categoria, 'resposta_invalida')

    def test_envelope_incompleto_campos_extras_e_acoes_invalidas_falham(self):
        casos = ({'resposta': 'Proponho abrir.', 'acao': 'pc'},
                 {'resposta': 'Proponho abrir.', 'campos': {'comando': 'calc'}},
                 {'resposta': 'Proponho abrir.', 'acao': 'shell', 'campos': {}},
                 {'resposta': 'Proponho abrir.', 'acao': 'pc', 'campos': {'comando': 'calc'}, 'execute': True},
                 {'resposta': '', 'acao': None, 'campos': {}},
                 {'resposta': 'Oi', 'acao': None, 'campos': {'comando': 'calc'}},
                 {'resposta': 'Oi', 'acao': 'modelo_conversa', 'campos': {'modelo': 'llama3.2:latest'}})
        for objeto in casos:
            with self.subTest(objeto=objeto), self.assertRaises(natural.RespostaModeloInvalida):
                natural.extrair_resposta(json.dumps(objeto), estrito=True)

    def test_chaves_duplicadas_e_constantes_invalidas_falham_estritamente(self):
        for texto in ('{"resposta":"Oi","acao":null,"acao":"pc","campos":{}}',
                '{"resposta":"Oi","acao":null,"campos":{},"x":NaN}'):
            with self.subTest(texto=texto), self.assertRaises(natural.RespostaModeloInvalida):
                natural.extrair_resposta(texto, estrito=True)

    def test_erro_estrito_nao_revela_corpo_ou_sugestao_do_modelo(self):
        secreto = 'fixture-privada-resposta-2121'
        texto = '{"resposta":"' + secreto + '","acao":'
        with self.assertRaises(natural.RespostaModeloInvalida) as recebido:
            natural.extrair_resposta(texto, estrito=True)
        self.assertNotIn(secreto, str(recebido.exception))
        self.assertNotIn('"acao"', str(recebido.exception))

    def test_vazio_excesso_e_parametro_invalido_nao_sao_sucesso_estrito(self):
        for texto in ('', '   ', 'x' * (natural.LIMITE_RESPOSTA + 1)):
            with self.subTest(tamanho=len(texto)), self.assertRaises(natural.RespostaModeloInvalida):
                natural.extrair_resposta(texto, estrito=True)
        with self.assertRaises(ValueError):
            natural.extrair_resposta('Oi', estrito='sim')

    def test_chamadas_legadas_preservam_aviso_local_sem_excecao(self):
        malformado = natural.extrair_resposta('{"resposta":"Oi","acao":')
        self.assertIn('formato incompleto ou inválido', malformado['texto'])
        self.assertIsNone(malformado['plano'])
        invalido = natural.extrair_resposta('{"resposta":"Oi","acao":"shell","campos":{}}')
        self.assertIn('Não preparei uma ação válida', invalido['texto'])
        self.assertEqual(natural.extrair_resposta(''), {'texto': '', 'plano': None})

    def test_modelo_individual_invalido_nao_vira_historico_ou_repeticao(self):
        registrar=Mock()
        with self.assertRaises(FalhaAPI) as recebido:
            self.conversar_individual('{"resposta":"fixture-privada","acao":', registrar)
        self.assertEqual(recebido.exception.categoria, 'resposta_invalida')
        self.assertNotIn('fixture-privada', str(recebido.exception))
        registrar.assert_not_called()

    def test_modelo_individual_redige_conteudo_depois_de_decodificar_json(self):
        registrar=Mock()
        segredo='fixture-privada-2121'
        bruto=json.dumps({'resposta':'api_key="'+segredo+'". Mensagem recebida.',
            'acao':None,'campos':{}})
        resultado=self.conversar_individual(bruto, registrar)
        self.assertIn('Mensagem recebida.', resultado['texto'])
        self.assertNotIn(segredo, resultado['texto'])
        self.assertNotIn('formato incompleto', resultado['texto'])
        registrar.assert_called_once()
        self.assertNotIn(segredo, str(registrar.call_args))

    def test_historico_exclui_so_aviso_local_gerado_sem_modificar_registros(self):
        aviso=servicos._AVISOS_FORMATO_LOCAIS[0]
        relatorio=('👥 Equipe cooperativa Ollama: 2/4 modelos responderam.\n'
            'Resposta de llama3.2:latest:\n'+aviso+'\n'
            'A síntese adicional não foi enviada: consulta encerrada.\n\nParticipação: ✅ llama3.2:latest')
        individuo='🤖 Ollama / llama3.2:latest · Conversa:\n'+aviso
        explicacao='A mensagem "'+aviso+'" indica um problema de formato.'
        paralelo='👥 Equipe Ollama: 2/2 modelos responderam.\n✅ Llama\n'+aviso+'\n✅ Qwen\nContribuição real.'
        historico=[{'role':'user','content':aviso},
            {'role':'assistant','content':aviso},
            {'role':'assistant','content':relatorio},
            {'role':'assistant','content':individuo},
            {'role':'assistant','content':explicacao},
            {'role':'assistant','content':paralelo},
            {'role':'assistant','content':'Uma contribuição real de planejamento.'}]
        antes=copy.deepcopy(historico)
        filtrado=servicos._historico_sem_avisos_locais(historico)
        self.assertEqual(filtrado,[historico[i] for i in (0,4,5,6)])
        self.assertEqual(historico,antes)

    def test_consulta_preserva_pedido_do_dono_e_nao_reenvia_aviso_local_antigo(self):
        aviso=servicos._AVISOS_FORMATO_LOCAIS[0]
        historico=[{'role':'user','content':'Explique minha dúvida anterior.'},
            {'role':'assistant','content':aviso},
            {'role':'assistant','content':'Contribuição real anterior.'}]
        antes=copy.deepcopy(historico)
        chat={'id':'fixture','titulo':'Conversa fictícia','equipe_politica':'manual',
              'provedor':'Ollama','modelo_ollama':'llama3.2:latest','equipe_paralela':False}
        roteador=Mock()
        roteador.responder.return_value=('Resposta normal.','Ollama')
        with patch.object(servicos,'_TRAVAS',{}), \
                patch.object(servicos.central,'obter_chat_ativo',return_value=chat), \
                patch.object(servicos.central,'historico_chat',return_value=historico), \
                patch.object(servicos.central,'registrar_troca'), \
                patch('memoria_assistente.contexto_seguro',return_value={'texto':'','aviso':''}):
            resultado=servicos.conversar('Continue a explicação.', 'fixture-contexto',roteador,
                retornar_plano=True)
        enviado=roteador.responder.call_args.kwargs['historico']
        self.assertEqual(enviado,[historico[0],historico[2]])
        self.assertEqual(historico,antes)
        self.assertIn('Resposta normal.',resultado['texto'])


if __name__ == '__main__':
    unittest.main()
