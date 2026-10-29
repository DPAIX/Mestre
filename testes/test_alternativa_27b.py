"""Seleção de artefato conferido, sem pesos, serviço real ou histórico pessoal."""
import copy
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import alternativa_27b as alternativa
import bateria_modelos
import colaboracao_chats as central
import nucleo
import servicos_chat


def catalogo():
    return [{'nome':'llama3.2:latest','nuvem':False},
            {'nome':alternativa.MODELO_ORIGINAL,'nuvem':False},
            {'nome':alternativa.MODELO_LEVE,'nuvem':False,'digest':alternativa.DIGEST_MANIFESTO}]


class AlternativaTeste(unittest.TestCase):
    def setUp(self):
        ambiente=patch.dict(os.environ,{'OLLAMA_27B_LEVE':'1','OLLAMA_PERFIL':'equilibrado',
            'NINE_ROUTER_HABILITADO':'0','MEMORIA_HABILITADA':'0'},clear=True)
        ambiente.start();self.addCleanup(ambiente.stop)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        dados=patch.object(nucleo,'DADOS',Path(self.tmp.name));dados.start();self.addCleanup(dados.stop)

    def test_sem_opcao_preserva_todas_as_tags_e_nao_exige_metadados(self):
        nomes=[m['nome'] for m in catalogo()]
        with patch.dict(os.environ,{'OLLAMA_27B_LEVE':'0'}):
            self.assertEqual(alternativa.selecionar(nomes,[]),(nomes,''))

    def test_escolha_deduplica_original_e_alternativa_sem_alterar_catalogo(self):
        registros=catalogo();antes=copy.deepcopy(registros)
        nomes,aviso=alternativa.selecionar([m['nome'] for m in registros],registros)
        self.assertEqual(nomes,['llama3.2:latest',alternativa.MODELO_LEVE])
        self.assertIn(alternativa.MODELO_ORIGINAL,aviso)
        self.assertIn('não foi consultado',aviso)
        self.assertEqual(registros,antes)

    def test_nuvem_digest_ausente_diferente_ou_nao_textual_bloqueiam(self):
        for alteracao in ({'nuvem':True},{'digest':''},{'digest':'f'*64},{'digest':None}):
            with self.subTest(alteracao=alteracao):
                itens=catalogo();itens[-1].update(alteracao)
                with self.assertRaises(ValueError):alternativa.selecionar([alternativa.MODELO_ORIGINAL],itens)
        with self.assertRaises(ValueError):alternativa.conferir_alternativa([])

    def test_duplicata_contraditoria_nao_confirma_artefato(self):
        itens=catalogo();itens.append({**itens[-1],'digest':'e'*64})
        with self.assertRaises(ValueError):alternativa.conferir_alternativa(itens)

    def test_selecao_manual_de_outros_modelos_nao_adiciona_27b(self):
        self.assertEqual(alternativa.selecionar(['llama3.2:latest'],[]),(['llama3.2:latest'],''))

    def test_opcao_invalida_nao_e_opt_in(self):
        with patch.dict(os.environ,{'OLLAMA_27B_LEVE':'sim'}):
            with self.assertRaises(ValueError):alternativa.ativada()

    def roteador(self):
        r=MagicMock();r.catalogo_ollama.return_value={'habilitado':True,'modelos':catalogo()}
        return r

    def test_equipe_manual_antiga_usa_alternativa_sem_reescrever_composicao_salva(self):
        chat=central.criar_chat('fixture','Manual','Ollama')
        originais=['llama3.2:latest',alternativa.MODELO_ORIGINAL]
        central.configurar_chat('fixture',chat['id'],equipe_paralela=True,equipe_modelos=originais,
            equipe_modo='cooperativa')
        r=self.roteador()
        with patch('conversa_equipe.consultar_modelos',return_value={'texto':'Conteúdo válido','plano':None}) as consulta:
            resposta=servicos_chat.conversar('Explique números primos.','fixture',r,retornar_plano=True)
        self.assertEqual(consulta.call_args.args[2],['llama3.2:latest',alternativa.MODELO_LEVE])
        self.assertIn(alternativa.MODELO_LEVE,resposta['texto'])
        self.assertEqual(central.obter_chat_ativo('fixture')['equipe_modelos'],originais)

    def test_equipe_automatica_e_ativacao_revelam_versao_leve(self):
        r=self.roteador()
        with patch('conversa_equipe.consultar_modelos',return_value={'texto':'Conteúdo válido','plano':None}) as consulta:
            resposta=servicos_chat.conversar('Explique números primos.','automatico',r,retornar_plano=True)
        self.assertEqual(consulta.call_args.args[2],['llama3.2:latest',alternativa.MODELO_LEVE])
        self.assertIn(alternativa.MODELO_ORIGINAL,resposta['texto'])
        texto=servicos_chat.executar_acao('chat_equipe',{'ativo':True},'ativacao',r)
        self.assertIn('Versão leve selecionada',texto)
        self.assertEqual(central.obter_chat_ativo('ativacao')['equipe_modelos'],['llama3.2:latest',alternativa.MODELO_LEVE])

    def test_digest_trocado_impede_equipe_sem_fallback(self):
        r=self.roteador();r.catalogo_ollama.return_value['modelos'][-1]['digest']='f'*64
        with patch('conversa_equipe.consultar_modelos') as consulta:
            with self.assertRaises(ValueError):servicos_chat.conversar('Explique números primos.','fixture',r)
        consulta.assert_not_called();r.responder.assert_not_called()

    def test_bateria_testa_alternativa_uma_vez_e_informa_original_preservado(self):
        r=self.roteador();r.responder.return_value=('OK','Ollama')
        resposta=bateria_modelos.testar_catalogo(r)
        self.assertEqual(resposta['total'],2)
        self.assertEqual(r.responder.call_count,2)
        nomes=[c.kwargs['modelo_ollama'] for c in r.responder.call_args_list]
        self.assertEqual(nomes,['llama3.2:latest',alternativa.MODELO_LEVE])
        self.assertIn(alternativa.MODELO_ORIGINAL,bateria_modelos.texto_resultado(resposta))


if __name__=='__main__':unittest.main()
