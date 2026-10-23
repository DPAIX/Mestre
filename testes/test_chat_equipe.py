"""Equipe persistente por conversa; catálogo e respostas simulados, sem rede."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as central
import nucleo
import servicos_chat as servicos


class ChatEquipe(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.base = self.raiz / 'codigo'
        self.base.mkdir()
        self.dados = self.raiz / 'dados'
        for nome, valor in (('BASE', self.base), ('DADOS', self.dados)):
            p = patch.object(nucleo, nome, valor)
            p.start(); self.addCleanup(p.stop)
        p = patch.dict(os.environ, {}, clear=True)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(servicos, '_TRAVAS', {})
        p.start(); self.addCleanup(p.stop)
        self.contexto = 'telegram:1:10:4'
        self.outro = 'telegram:1:10:5'
        self.modelos = ['qwen3.8:27b', 'mistral:latest',
                        'llama3.2:latest', 'gemma4:31b-cloud']
        self.catalogo = {
            'habilitado': True, 'padrao': 'mistral:latest',
            'modelos': [{'nome': m, 'nuvem': m.endswith('-cloud')}
                        for m in self.modelos],
        }
        self.roteador = MagicMock()
        self.roteador.catalogo_ollama.side_effect = lambda: copy.deepcopy(self.catalogo)
        self.roteador.responder.side_effect = lambda texto, **kw: (
            'Resposta de ' + kw.get('modelo_ollama', kw['provedor']), kw['provedor'])
        self.chat = central.criar_chat(self.contexto, 'Projeto do assistente', 'Ollama')
        central.configurar_chat(self.contexto, self.chat['id'], modelo_ollama='mistral:latest')

    def ativar(self, contexto=None, **campos):
        return servicos.executar_acao(
            'chat_equipe', {'ativo': True, 'modo': 'paralela', **campos},
            contexto or self.contexto, self.roteador)

    def ativo(self, contexto=None):
        return central.obter_chat_ativo(contexto or self.contexto)

    def arquivo(self):
        return (self.dados / central.ARQUIVO).read_bytes()

    def test_ativacao_captura_quatro_tags_e_persiste_sem_gerar_resposta(self):
        mensagem = self.ativar()
        self.roteador.catalogo_ollama.assert_called_once_with()
        self.roteador.responder.assert_not_called()
        self.roteador.reativar.assert_not_called()
        atual = self.ativo()
        self.assertIs(atual['equipe_paralela'], True)
        self.assertEqual(atual['equipe_modelos'], self.modelos)
        self.assertEqual(atual['provedor'], 'Ollama')
        self.assertIs(atual['modo_conversa'], True)
        self.assertEqual(atual['modelo_ollama'], 'mistral:latest')
        for modelo in self.modelos:
            self.assertIn(modelo, mensagem)
        self.assertIn('cloud', mensagem)
        persistido = json.loads(self.arquivo())
        self.assertEqual(persistido['versao'], 1)
        chat_disco = next(iter(persistido['contextos'].values()))['chats'][0]
        self.assertEqual(chat_disco['equipe_modelos'], self.modelos)
        self.assertIs(chat_disco['equipe_paralela'], True)

    def test_ativacao_deduplica_tags_e_somente_reativar_atualiza_lista(self):
        self.catalogo['modelos'].append(copy.deepcopy(self.catalogo['modelos'][0]))
        self.ativar()
        self.assertEqual(self.ativo()['equipe_modelos'], self.modelos)
        self.catalogo['modelos'] = [{'nome': 'qwen3.5:4b', 'nuvem': False}]
        self.roteador.catalogo_ollama.reset_mock()
        servicos.conversar('Compare as alternativas', self.contexto, self.roteador)
        self.roteador.catalogo_ollama.assert_not_called()
        self.assertEqual({c.kwargs['modelo_ollama'] for c in
                          self.roteador.responder.call_args_list}, set(self.modelos))
        self.ativar()
        self.assertEqual(self.ativo()['equipe_modelos'], ['qwen3.5:4b'])

    def test_desativar_preserva_historico_e_volta_ao_modelo_individual(self):
        central.registrar_troca(self.contexto, 'Plano anterior', 'Plano preservado', 'Ollama')
        anterior = central.historico_chat(self.contexto)
        self.ativar()
        self.roteador.catalogo_ollama.reset_mock()
        mensagem = servicos.executar_acao(
            'chat_equipe', {'ativo': False}, self.contexto, self.roteador)
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_not_called()
        atual = self.ativo()
        self.assertIs(atual['equipe_paralela'], False)
        self.assertEqual(atual['equipe_modelos'], [])
        self.assertEqual(central.historico_chat(self.contexto), anterior)
        self.assertIn('desativada', mensagem)
        servicos.conversar('Continue o plano', self.contexto, self.roteador)
        self.roteador.responder.assert_called_once_with(
            'Continue o plano', historico=anterior,
            provedor='Ollama', modelo_ollama='mistral:latest')

    def test_selecionar_modelo_individual_limpa_equipe(self):
        self.ativar()
        servicos.executar_acao('chat_modelo', {'modelo': 'llama3.2:latest'},
                              self.contexto, self.roteador)
        atual = self.ativo()
        self.assertIs(atual['equipe_paralela'], False)
        self.assertEqual(atual['equipe_modelos'], [])
        servicos.conversar('Olá', self.contexto, self.roteador)
        self.roteador.responder.assert_called_once_with(
            'Olá', historico=[], provedor='Ollama', modelo_ollama='llama3.2:latest')

    def test_mudar_provedor_desativa_equipe_sem_consultar_catalogo(self):
        self.ativar()
        self.roteador.catalogo_ollama.reset_mock()
        servicos.executar_acao('chat_provedor', {'provedor': 'Gemini'},
                              self.contexto, self.roteador)
        self.roteador.catalogo_ollama.assert_not_called()
        atual = self.ativo()
        self.assertIs(atual['equipe_paralela'], False)
        self.assertEqual(atual['equipe_modelos'], [])
        servicos.conversar('Pergunta individual', self.contexto, self.roteador)
        self.roteador.responder.assert_called_once_with(
            'Pergunta individual', historico=[], provedor='Gemini')

    def test_equipes_e_historicos_ficam_isolados_por_chat_e_contexto(self):
        self.ativar()
        central.registrar_troca(self.contexto, 'Contexto reservado', 'Resposta reservada', 'Ollama')
        segundo = central.criar_chat(self.contexto, 'Outra conversa', 'Ollama')
        self.assertIs(self.ativo()['equipe_paralela'], False)
        self.assertEqual(self.ativo()['equipe_modelos'], [])
        servicos.conversar('Pergunta nova', self.contexto, self.roteador)
        self.roteador.responder.assert_called_once_with('Pergunta nova', historico=[], provedor='Ollama')
        self.assertIs(self.ativo(self.outro)['equipe_paralela'], False)
        self.assertEqual(central.historico_chat(self.outro), [])
        central.selecionar_chat(self.contexto, self.chat['id'])
        self.assertEqual(self.ativo()['equipe_modelos'], self.modelos)
        self.assertEqual(central.historico_chat(self.contexto)[0]['content'], 'Contexto reservado')
        self.assertEqual(central.historico_chat(self.contexto, segundo['id'])[0]['content'], 'Pergunta nova')

    def test_id_alheio_ou_nao_selecionado_nao_consulta_catalogo_nem_altera_estado(self):
        alheio = central.criar_chat(self.outro, 'Outro contexto', 'Ollama')
        segundo = central.criar_chat(self.contexto, 'Segunda conversa', 'Ollama')
        antes = self.arquivo()
        for chat_id in (alheio['id'], self.chat['id']):
            with self.subTest(chat=chat_id), self.assertRaises(ValueError):
                self.ativar(id=chat_id)
        self.assertEqual(self.arquivo(), antes)
        self.assertEqual(self.ativo()['id'], segundo['id'])
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_not_called()

    def test_flag_de_ativacao_exige_bool_sem_alterar_estado(self):
        antes = self.arquivo()
        for valor in (None, 1, 0, 'on', [], {}):
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                servicos.executar_acao('chat_equipe', {'ativo': valor},
                                      self.contexto, self.roteador)
            self.assertEqual(self.arquivo(), antes)
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.responder.assert_not_called()

    def test_catalogo_desabilitado_vazio_ou_excessivo_preserva_equipe_anterior(self):
        self.ativar()
        antes = self.arquivo()
        casos = [
            {**self.catalogo, 'habilitado': False},
            {**self.catalogo, 'modelos': []},
            {**self.catalogo, 'modelos': [{'nome': f'modelo:{n}b'} for n in range(9)]},
        ]
        for catalogo in casos:
            self.catalogo = catalogo
            with self.subTest(catalogo=catalogo), self.assertRaises(ValueError):
                self.ativar()
            self.assertEqual(self.arquivo(), antes)
        self.roteador.responder.assert_not_called()

    def test_conversa_consulta_todos_explicitamente_e_preserva_historico_multiturno(self):
        central.registrar_troca(self.contexto, 'Objetivo anterior', 'Sugestão anterior', 'Ollama')
        anterior = central.historico_chat(self.contexto)
        self.ativar()
        self.roteador.catalogo_ollama.reset_mock()
        resposta = servicos.conversar('Continue o projeto', self.contexto, self.roteador)
        chamadas = self.roteador.responder.call_args_list
        self.assertEqual(len(chamadas), 4)
        self.assertEqual({c.kwargs['modelo_ollama'] for c in chamadas}, set(self.modelos))
        self.assertEqual(len({id(c.kwargs['historico']) for c in chamadas}), 4)
        for chamada in chamadas:
            self.assertEqual(chamada.args, ('Continue o projeto',))
            self.assertEqual(chamada.kwargs['provedor'], 'Ollama')
            self.assertEqual(chamada.kwargs['historico'], anterior)
            self.assertEqual(set(chamada.kwargs), {'historico', 'provedor', 'modelo_ollama'})
        self.roteador.catalogo_ollama.assert_not_called()
        self.roteador.reativar.assert_not_called()
        for modelo in self.modelos:
            self.assertIn(modelo, resposta)
        historico = central.historico_chat(self.contexto)
        self.assertEqual(historico[:2], anterior)
        self.assertEqual(len(historico), 4)
        self.assertEqual(historico[2]['content'], 'Continue o projeto')
        self.assertEqual(self.ativo()['mensagens'][-1]['provedor'], 'Ollama')
        self.roteador.responder.reset_mock()
        servicos.conversar('Revise esse plano', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertTrue(all(c.kwargs['historico'] == historico
                            for c in self.roteador.responder.call_args_list))
        self.assertEqual(len(central.historico_chat(self.contexto)), 6)

    def test_interpretacao_de_equipe_devolve_plano_sem_executar_acao(self):
        self.ativar()
        self.roteador.responder.side_effect = lambda *a, **kw: (json.dumps({
            'resposta': 'Posso abrir após sua confirmação.',
            'acao': 'pc', 'campos': {'comando': 'calc'}}), 'Ollama')
        with patch.object(servicos, 'executar_acao') as executar:
            resultado = servicos.conversar(
                'Preciso que abra uma calculadora', self.contexto,
                self.roteador, retornar_plano=True)
        executar.assert_not_called()
        self.assertEqual(resultado['plano']['acao'], 'pc')
        self.assertEqual(resultado['plano']['campos'], {'comando': 'calc'})
        self.assertEqual(resultado['chat_id'], self.chat['id'])
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertTrue(all('ÚLTIMA MENSAGEM DO PROPRIETÁRIO' in c.args[0]
                            for c in self.roteador.responder.call_args_list))
        self.assertEqual(len(central.historico_chat(self.contexto)), 2)
        self.assertEqual(central.historico_chat(self.contexto)[0]['content'],
                         'Preciso que abra uma calculadora')

    def test_falha_parcial_registra_resultado_sem_repetir_ou_reativar_modelos(self):
        self.ativar()
        def responder(texto, **kw):
            if kw['modelo_ollama'] == 'gemma4:31b-cloud':
                raise RuntimeError('Conta cloud indisponível')
            return 'Sugestão ' + kw['modelo_ollama'], 'Ollama'
        self.roteador.responder.side_effect = responder
        resposta = servicos.conversar('Sugira melhorias', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertIn('3/4', resposta)
        self.assertIn('gemma4:31b-cloud', resposta)
        self.assertEqual(len(central.historico_chat(self.contexto)), 2)
        self.assertIn('3/4', central.historico_chat(self.contexto)[-1]['content'])
        self.assertIs(self.ativo()['equipe_paralela'], True)
        self.roteador.reativar.assert_not_called()

    def test_falha_total_preserva_historico_e_libera_conversa_para_nova_tentativa(self):
        central.registrar_troca(self.contexto, 'Plano conhecido', 'Resposta conhecida', 'Ollama')
        self.ativar()
        antes = self.arquivo()
        historico = central.historico_chat(self.contexto)
        self.roteador.responder.side_effect = RuntimeError('Modelo indisponível')
        with self.assertRaises(RuntimeError):
            servicos.conversar('Tente responder', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertEqual(self.arquivo(), antes)
        self.roteador.responder.reset_mock()
        self.roteador.responder.side_effect = lambda *a, **kw: ('Disponível agora', 'Ollama')
        servicos.conversar('Nova tentativa explícita', self.contexto, self.roteador)
        self.assertEqual(self.roteador.responder.call_count, 4)
        self.assertTrue(all(c.kwargs['historico'] == historico
                            for c in self.roteador.responder.call_args_list))
        self.assertEqual(len(central.historico_chat(self.contexto)), 4)

    def test_metadados_preservam_equipe_sem_expor_historico_e_sem_alias_mutavel(self):
        self.ativar()
        central.registrar_troca(self.contexto, 'MARCADOR_PRIVADO', 'Resposta privada', 'Ollama')
        metadados = central.listar_chats(self.contexto)[0]
        self.assertEqual(metadados['equipe_modelos'], self.modelos)
        self.assertIs(metadados['equipe_paralela'], True)
        self.assertEqual(metadados['total_mensagens'], 2)
        self.assertNotIn('mensagens', metadados)
        self.assertNotIn('MARCADOR_PRIVADO', json.dumps(metadados))
        metadados['equipe_modelos'].append('outro:latest')
        self.assertEqual(self.ativo()['equipe_modelos'], self.modelos)

    def test_chat_legado_recebe_defaults_sem_perder_historico(self):
        central.registrar_troca(self.contexto, 'Histórico antigo', 'Resposta antiga', 'Ollama')
        dados = json.loads(self.arquivo())
        legado = next(iter(dados['contextos'].values()))['chats'][0]
        legado.pop('equipe_modelos', None)
        legado.pop('equipe_paralela', None)
        nucleo.gravar_json(central.ARQUIVO, dados)
        historico = central.historico_chat(self.contexto, self.chat['id'])
        atual = self.ativo()
        self.assertIs(atual['equipe_paralela'], False)
        self.assertEqual(atual['equipe_modelos'], [])
        self.assertEqual(central.historico_chat(self.contexto), historico)
        self.assertEqual(json.loads(self.arquivo())['versao'], 1)


if __name__ == '__main__':
    unittest.main()
