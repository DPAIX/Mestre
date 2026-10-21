"""Chats e colaboração com fontes fictícias, sem rede nem execução de propostas."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import colaboracao_chats as colab
import nucleo


class ColaboracaoChats(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name)
        self.fontes=self.raiz/'projeto'
        self.fontes.mkdir()
        self.dados=self.raiz/'dados_privados'
        self.dados.mkdir()
        self.base_patch=patch.object(nucleo,'BASE',self.fontes)
        self.base_patch.start();self.addCleanup(self.base_patch.stop)
        self.dados_patch=patch.object(nucleo,'DADOS',self.dados)
        self.dados_patch.start();self.addCleanup(self.dados_patch.stop)
        self.contexto='painel:local'
        self.outro='telegram:1:10'
        self.segredo='sk-proj-'+'Z'*38
        self.codigo='CHAVE_FICTICIA = '+repr(self.segredo)+'\n'
        (self.fontes/'nucleo.py').write_text(self.codigo,encoding='utf8')
        (self.fontes/'assistente_pc.py').write_text('def principal():\n    return "exemplo"\n',encoding='utf8')
        (self.fontes/'colaboracao_chats.py').write_text('# módulo fictício\n',encoding='utf8')
        # Arquivos privados fictícios servem para detectar inclusões indevidas no ZIP.
        (self.fontes/'.env').write_text('POISON_ENV=NAO_EXPORTAR_ENV\n',encoding='utf8')
        (self.fontes/'dados').mkdir()
        (self.fontes/'dados'/'privado.json').write_text('{"pessoal":"NAO_EXPORTAR_DADOS"}',encoding='utf8')

    def conteudo_exportado(self,caminho):
        with zipfile.ZipFile(caminho) as pacote:
            nomes=pacote.namelist()
            conteudo=b'\n'.join(pacote.read(nome) for nome in nomes)
        return nomes,conteudo.decode('utf8')

    def test_chat_padrao_e_isolamento_por_contexto(self):
        principal=colab.obter_chat_ativo(self.contexto)
        self.assertEqual(principal['titulo'],'Conversa principal')
        self.assertEqual(principal['mensagens'],[])
        colab.registrar_troca(self.contexto,'Pergunta privada','Resposta privada','Gemini')
        self.assertEqual(colab.historico_chat(self.contexto),[
            {'role':'user','content':'Pergunta privada'},
            {'role':'assistant','content':'Resposta privada'}
        ])
        self.assertEqual(colab.historico_chat(self.outro),[])
        with self.assertRaises(ValueError):
            colab.selecionar_chat(self.outro,principal['id'])
        self.assertEqual(colab.historico_chat(self.contexto)[0]['content'],'Pergunta privada')

    def test_novo_chat_seleciona_e_troca_preserva_historicos(self):
        primeiro=colab.criar_chat(self.contexto,'Planejamento','Gemini')
        colab.registrar_troca(self.contexto,'Plano A','Resposta A','Gemini')
        segundo=colab.criar_chat(self.contexto,'Revisão','Claude')
        self.assertEqual(colab.obter_chat_ativo(self.contexto)['id'],segundo['id'])
        self.assertEqual(colab.historico_chat(self.contexto),[])
        colab.selecionar_chat(self.contexto,primeiro['id'])
        self.assertEqual(colab.historico_chat(self.contexto)[0]['content'],'Plano A')
        colab.configurar_chat(self.contexto,primeiro['id'],'Ollama')
        self.assertEqual(colab.obter_chat_ativo(self.contexto)['provedor'],'Ollama')
        with self.assertRaises(ValueError):
            colab.configurar_chat(self.outro,primeiro['id'],'OpenAI')

    def test_lista_expoe_apenas_metadados_e_provedores_validos(self):
        chat=colab.criar_chat(self.contexto,'Conversas de teste')
        colab.registrar_troca(self.contexto,'MARCADOR_PRIVADO','Resposta','OpenAI')
        lista=colab.listar_chats(self.contexto)
        self.assertIn(chat['id'],[item['id'] for item in lista])
        self.assertTrue(all('mensagens' not in item for item in lista))
        self.assertNotIn('MARCADOR_PRIVADO',json.dumps(lista))
        for provedor in ('auto','Gemini','OpenAI','Claude','Ollama'):
            with self.subTest(provedor=provedor):
                colab.configurar_chat(self.contexto,chat['id'],provedor)
                self.assertEqual(colab.obter_chat_ativo(self.contexto)['provedor'],provedor)
        with self.assertRaises(ValueError):
            colab.configurar_chat(self.contexto,chat['id'],'provedor-inexistente')

    def test_historico_limita_trocas_tamanho_e_redige_segredos(self):
        colab.criar_chat(self.contexto,'Histórico limitado')
        for numero in range(22):
            colab.registrar_troca(self.contexto,f'Pergunta {numero}',f'Resposta {numero}','Gemini')
        historico=colab.historico_chat(self.contexto)
        self.assertEqual(len(historico),40)
        self.assertEqual(historico[0],{'role':'user','content':'Pergunta 2'})
        colab.registrar_troca(self.contexto,self.segredo+'A'*5000,'B'*5000,'Gemini')
        historico=colab.historico_chat(self.contexto)
        self.assertEqual(len(historico),40)
        self.assertTrue(all(len(item['content'])<=4096 for item in historico))
        self.assertNotIn(self.segredo,json.dumps(historico))
        # O arquivo durável deve conter o chat e os limites já aplicados.
        estado=json.loads((self.dados/'colaboracao_chats.json').read_text(encoding='utf8'))
        self.assertIn('Histórico limitado',json.dumps(estado,ensure_ascii=False))
        self.assertNotIn(self.segredo,json.dumps(estado))

    def test_tarefas_sao_globais_e_validam_transicoes_de_estado(self):
        tarefa=colab.criar_tarefa('Revisar persistência','Validar gravação atômica','revisor')
        estado=colab.estado_central(self.outro)
        self.assertIn(tarefa['id'],[item['id'] for item in estado['tarefas']])
        for status in ('em_andamento','concluido','pendente','cancelada'):
            with self.subTest(status=status):
                colab.alterar_tarefa(tarefa['id'],status)
                atual=next(t for t in colab.estado_central(self.contexto)['tarefas'] if t['id']==tarefa['id'])
                self.assertEqual(atual['status'],'concluida' if status=='concluido' else status)
        with self.assertRaises(ValueError):
            colab.alterar_tarefa(tarefa['id'],'executar_codigo')

    def test_atualizacoes_concorrentes_nao_perdem_tarefas(self):
        def criar(numero):
            return colab.criar_tarefa(f'Tarefa concorrente {numero}')
        with ThreadPoolExecutor(max_workers=8) as executor:
            criadas=list(executor.map(criar,range(24)))
        tarefas=colab.estado_central(self.contexto)['tarefas']
        self.assertEqual(len(tarefas),24)
        self.assertEqual(len({t['id'] for t in tarefas}),24)
        self.assertEqual({t['id'] for t in criadas},{t['id'] for t in tarefas})

    def test_contribuicao_e_codigo_inerte_inclusive_apos_aceite(self):
        marcador=self.raiz/'NAO_EXECUTADO.txt'
        codigo='from pathlib import Path\nPath('+repr(str(marcador))+').write_text("executado")'
        tarefa=colab.criar_tarefa('Revisar proposta')
        proposta=colab.importar_contribuicao('ChatGPT','Proposta de teste',codigo,tarefa_id=tarefa['id'])
        self.assertEqual(proposta['status'],'rascunho')
        self.assertEqual(proposta['texto'],codigo)
        self.assertEqual(proposta['hash'],hashlib.sha256(codigo.encode('utf8')).hexdigest())
        self.assertFalse(marcador.exists())
        colab.decidir_contribuicao(proposta['id'],'aceitar')
        central=colab.estado_central(self.outro)
        atual=next(p for p in central['contribuicoes'] if p['id']==proposta['id'])
        self.assertEqual(atual['status'],'aceita')
        self.assertFalse(marcador.exists())
        self.assertEqual((self.fontes/'nucleo.py').read_text(encoding='utf8'),self.codigo)

    def test_contribuicao_redige_credenciais_e_rejeita_decisao_desconhecida(self):
        proposta=colab.importar_contribuicao('Gemini','Revisão',f'Chave fictícia: {self.segredo}')
        self.assertNotIn(self.segredo,proposta['texto'])
        with self.assertRaises(ValueError):
            colab.decidir_contribuicao(proposta['id'],'executar')
        colab.decidir_contribuicao(proposta['id'],'rejeitada')
        atual=next(p for p in colab.estado_central(self.contexto)['contribuicoes'] if p['id']==proposta['id'])
        self.assertEqual(atual['status'],'rejeitada')

    def test_hash_de_base_conflitante_impede_aceite_e_permite_rejeicao(self):
        base_hash=hashlib.sha256((self.fontes/'nucleo.py').read_bytes()).hexdigest()
        sem_conflito=colab.importar_contribuicao('Claude','Base atual','Texto de revisão',base_hashes={'nucleo.py':base_hash})
        self.assertFalse(sem_conflito['conflito_base'])
        (self.fontes/'nucleo.py').write_text('# nova versão da base\n',encoding='utf8')
        proposta=colab.importar_contribuicao('Claude','Base antiga','Texto de revisão',base_hashes={'nucleo.py':base_hash})
        self.assertTrue(proposta['conflito_base'])
        self.assertIn('nucleo.py',proposta['arquivos_conflitantes'])
        with self.assertRaises(ValueError):
            colab.decidir_contribuicao(proposta['id'],'aceitar')
        colab.decidir_contribuicao(proposta['id'],'rejeitar')
        atual=next(p for p in colab.estado_central(self.contexto)['contribuicoes'] if p['id']==proposta['id'])
        self.assertEqual(atual['status'],'rejeitada')

    def test_exportacao_tem_fontes_sanitizadas_e_hashes_verificaveis(self):
        caminho=colab.exportar_contexto(self.contexto)
        with zipfile.ZipFile(caminho) as pacote:
            nomes=set(pacote.namelist())
            self.assertTrue({
                'RESUMO.md','manifesto.json','prompts/chatgpt.md','prompts/gemini.md',
                'prompts/claude.md','prompts/manus.md','prompts/claude_code.md','prompts/opencode.md',
                'prompts/cline.md','template_contribuicao.json','tarefas.json','fontes/nucleo.py'
            }.issubset(nomes))
            manifesto=json.loads(pacote.read('manifesto.json'))
            sanitizado=pacote.read('fontes/nucleo.py')
            self.assertEqual(manifesto['hashes_fontes']['nucleo.py'],hashlib.sha256((self.fontes/'nucleo.py').read_bytes()).hexdigest())
            self.assertEqual(manifesto['hashes_sanitizados']['nucleo.py'],hashlib.sha256(sanitizado).hexdigest())
            self.assertNotIn(self.segredo,sanitizado.decode('utf8'))
        self.assertEqual(caminho.parent,self.dados/'colaboracao')

    def test_exportacao_exclui_dados_chats_e_texto_de_propostas_e_usa_nome_unico(self):
        colab.criar_chat(self.contexto,'TITULO_PRIVADO_NAO_EXPORTAR')
        colab.registrar_troca(self.contexto,'HISTORICO_PRIVADO_NAO_EXPORTAR','RESPOSTA_PRIVADA_NAO_EXPORTAR','Gemini')
        colab.importar_contribuicao('ChatGPT','Proposta de projeto','TEXTO_PROPOSTA_NAO_EXPORTAR')
        primeiro=colab.exportar_contexto(self.contexto)
        segundo=colab.exportar_contexto(self.contexto)
        self.assertNotEqual(primeiro,segundo)
        self.assertTrue(primeiro.is_file());self.assertTrue(segundo.is_file())
        nomes,conteudo=self.conteudo_exportado(primeiro)
        self.assertFalse(any('.env' in Path(nome).parts or 'dados' in Path(nome).parts for nome in nomes))
        self.assertFalse(any('colaboracao_chats.json' in nome for nome in nomes))
        for marcador in (
            'NAO_EXPORTAR_ENV','NAO_EXPORTAR_DADOS','TITULO_PRIVADO_NAO_EXPORTAR',
            'HISTORICO_PRIVADO_NAO_EXPORTAR','RESPOSTA_PRIVADA_NAO_EXPORTAR','TEXTO_PROPOSTA_NAO_EXPORTAR'
        ):
            self.assertNotIn(marcador,conteudo)

    def test_exportacao_nao_segue_symlink_para_fora_da_base(self):
        fora=self.raiz/'fora_da_base.py'
        fora.write_text('MARCADOR_FORA_DA_BASE\n',encoding='utf8')
        try:
            (self.fontes/'multi_ia.py').symlink_to(fora)
        except (OSError,NotImplementedError):
            self.skipTest('O sistema não permite criar symlink neste ambiente.')
        caminho=colab.exportar_contexto(self.contexto)
        nomes,conteudo=self.conteudo_exportado(caminho)
        self.assertNotIn('fontes/multi_ia.py',nomes)
        self.assertNotIn('MARCADOR_FORA_DA_BASE',conteudo)


if __name__=='__main__':unittest.main()
