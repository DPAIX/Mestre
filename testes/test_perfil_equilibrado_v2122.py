"""Perfil compacto com GPU escolhida pelo serviço; somente HTTP e dados simulados."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import conversa_equipe as equipe
import multi_ia as ia


MODELOS = [
    {'nome':'maior:latest', 'nuvem':False, 'tamanho_bytes':18*1024**3},
    {'nome':'menor:latest', 'nuvem':False, 'tamanho_bytes':2*1024**3},
]


class PerfilEquilibrado(unittest.TestCase):
    def setUp(self):
        for alvo, opcoes in (
            (patch.dict, (os.environ, {'OLLAMA_HABILITADO':'1',
                'OLLAMA_URL':'http://127.0.0.1:11434', 'OLLAMA_PERFIL':'equilibrado',
                'OLLAMA_MODEL':'menor:latest'})),
        ):
            p=alvo(*opcoes, clear=True);p.start();self.addCleanup(p.stop)
        for nome, extras in (('ler_json', {'return_value':{}}), ('gravar_json', {}), ('registrar', {})):
            p=patch.object(ia,nome,**extras);p.start();self.addCleanup(p.stop)
        p=patch.object(configurar,'listar_catalogo',return_value=copy.deepcopy(MODELOS))
        self.catalogo=p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def gerar(self, **opcoes):
        with patch.object(ia,'postar',return_value={'done':True,'message':{'content':'Resposta utilizável.'}}) as enviar:
            resultado=self.roteador.ollama('Pedido atual',**opcoes)
        self.assertEqual(resultado,'Resposta utilizável.')
        enviar.assert_called_once()
        return enviar.call_args

    def test_contexto_curto_mantem_ollama_escolhendo_dispositivo(self):
        historico=[{'role':'user','content':'Pedido anterior.'}]
        chamada=self.gerar(historico=historico)
        payload=chamada.args[2]
        self.assertEqual(payload['options'],{'num_ctx':1024,'num_predict':256})
        self.assertEqual(payload['keep_alive'],0)
        self.assertIs(payload['think'],False)
        self.assertNotIn('num_gpu',payload['options'])
        self.assertEqual(payload['messages'][1:],historico+[{'role':'user','content':'Pedido atual'}])
        self.assertEqual(chamada.kwargs['timeout'],90)

    def test_cooperacao_compacta_sem_guard_cpu_nem_gpu_forcada(self):
        with patch.object(ia,'memoria_fisica_bytes',return_value=16*1024**3) as memoria:
            chamada=self.gerar(modelo='maior:latest',modo_cooperativo=True)
        memoria.assert_not_called()
        payload=chamada.args[2]
        self.assertIs(payload['think'],False)
        self.assertEqual(payload['options'],{'num_ctx':1024,'num_predict':256})
        self.assertEqual(payload['keep_alive'],0)
        self.assertEqual(payload['model'],'maior:latest')

    def test_cpu_continua_rejeitando_pesos_maiores_antes_de_gerar(self):
        with patch.dict(os.environ,{'OLLAMA_PERFIL':'cpu'}), \
                patch.object(ia,'memoria_fisica_bytes',return_value=16*1024**3), \
                patch.object(ia,'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.ollama('Pedido',modelo='maior:latest',modo_cooperativo=True)
        self.assertEqual(erro.exception.categoria,'recursos')
        enviar.assert_not_called()

    def test_equilibrado_exige_catalogo_e_tag_confirmada(self):
        for catalogo in ([], [{'nome':'menor:latest','nuvem':True}]):
            with self.subTest(catalogo=catalogo), \
                    patch.object(configurar,'listar_catalogo',return_value=catalogo), \
                    patch.object(ia,'postar') as enviar:
                self.roteador.invalidar_catalogo_ollama()
                with self.assertRaises(ia.FalhaAPI) as erro:self.roteador.ollama('Pedido')
                self.assertEqual(erro.exception.categoria,'configuracao')
                enviar.assert_not_called()

    def test_nuvem_opt_in_nao_remove_bloqueio_explicito(self):
        with patch.dict(os.environ,{'OLLAMA_NUVEM_HABILITADA':'1','OLLAMA_NO_CLOUD':'1'}), \
                patch.object(configurar,'listar_catalogo',return_value=[{'nome':'alias:latest','nuvem':True}]), \
                patch.object(ia,'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:self.roteador.ollama('Pedido',modelo='alias:latest')
        self.assertEqual(erro.exception.categoria,'configuracao')
        enviar.assert_not_called()

    def test_ordenacao_menor_primeiro_preserva_todos_e_selecao(self):
        antes=[item['nome'] for item in MODELOS]
        self.assertEqual(self.roteador.ordenar_equipe_cpu(antes),['menor:latest','maior:latest'])
        self.assertEqual(antes,['maior:latest','menor:latest'])
        self.assertEqual(os.environ['OLLAMA_MODEL'],'menor:latest')

    def test_paralelo_pedido_executa_sequencial_com_prazos_e_relatos_reais(self):
        chamadas=[]
        def enviar(url,chave,payload,provedor,**opcoes):
            chamadas.append((payload,opcoes))
            return {'done':True,'message':{'content':'Conteúdo de '+payload['model']}}
        with patch.object(equipe,'_TRAVA',threading.Lock()), \
                patch.object(equipe,'ThreadPoolExecutor',side_effect=AssertionError('Não criar fila paralela')), \
                patch.object(ia,'postar',side_effect=enviar):
            resultado=equipe.consultar_modelos('Compare opções.',[],['maior:latest','menor:latest'],
                self.roteador,modo='paralela',interpretar=True)
        self.assertEqual([payload['model'] for payload,_ in chamadas],['menor:latest','maior:latest'])
        self.assertEqual(resultado['execucao'],'sequencial_equilibrado')
        self.assertIn('sequencial no perfil equilibrado',resultado['texto'])
        self.assertEqual(resultado['orcamento']['por_modelo'],90)
        self.assertEqual([item['modelo'] for item in resultado['resultados']],['maior:latest','menor:latest'])
        self.assertTrue(all(item['ok'] for item in resultado['resultados']))
        self.assertTrue(all(payload['options']=={'num_ctx':1024,'num_predict':256} for payload,_ in chamadas))

    def test_timeout_nao_reenvia_nem_inicia_proximo_participante(self):
        with patch.object(equipe,'_TRAVA',threading.Lock()), \
                patch.object(ia,'postar',side_effect=ia.FalhaAPI('Ollama',0,'Prazo fictício','tempo_esgotado')) as enviar:
            with self.assertRaises(RuntimeError) as erro:
                equipe.consultar_modelos('Pedido',[],['maior:latest','menor:latest'],self.roteador,modo='cooperativa')
        enviar.assert_called_once()
        self.assertIn('Nenhuma geração foi enviada',str(erro.exception))


class ConfiguracaoEquilibrada(unittest.TestCase):
    def test_preserva_modelo_opcoes_e_arquivo_externo_sem_geracao(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=Path(tmp)/'.env'
            env.write_bytes(b'OUTRA_OPCAO=fixture\r\nOLLAMA_MODEL=menor:latest\r\nOLLAMA_PERFIL=cpu\r\n')
            with patch.object(configurar,'listar_catalogo',return_value=copy.deepcopy(MODELOS)), \
                    patch.object(configurar,'baixar_modelo') as baixar, \
                    patch.object(ia,'postar') as gerar:
                self.assertEqual(configurar.configurar_perfil('equilibrado',caminho=env),'menor:latest')
            self.assertEqual(configurar.valores_env(env)['OLLAMA_MODEL'],'menor:latest')
            self.assertEqual(configurar.valores_env(env)['OLLAMA_PERFIL'],'equilibrado')
            self.assertIn(b'OUTRA_OPCAO=fixture\r\n',env.read_bytes())
            baixar.assert_not_called();gerar.assert_not_called()

    def test_cli_equilibrado_sem_comandos_de_chat_ou_download(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(configurar,'configurar_perfil',return_value='menor:latest') as configurar_perfil, \
                patch('sys.stdout',new_callable=io.StringIO) as saida:
            self.assertEqual(configurar.main(['--perfil-equilibrado'],caminho=Path(tmp)/'.env'),0)
        self.assertEqual(configurar_perfil.call_args.args[0],'equilibrado')
        self.assertNotIn('/chat',saida.getvalue())
        self.assertIn('Nenhuma geração ou download',saida.getvalue())

    def test_configuracao_nao_ativa_alias_cloud(self):
        with tempfile.TemporaryDirectory() as tmp:
            env=Path(tmp)/'.env';original=b'OLLAMA_MODEL=alias:latest\n';env.write_bytes(original)
            with patch.object(configurar,'listar_catalogo',return_value=[{'nome':'alias:latest','nuvem':True}]):
                with self.assertRaises(configurar.FalhaConfiguracao):
                    configurar.configurar_perfil('equilibrado',caminho=env)
            self.assertEqual(env.read_bytes(),original)


class DigestCatalogo(unittest.TestCase):
    def listar(self,modelos):
        corpo=json.dumps({'models':modelos}).encode()
        resposta=io.BytesIO(corpo)
        class Cliente:
            def open(self,*args,**kwargs):return resposta
        with patch.object(configurar.urllib.request,'build_opener',return_value=Cliente()):
            return configurar.listar_catalogo()

    def test_digest_valido_normalizado_e_metadados_alheios_excluidos(self):
        for digest in ('A'*64,'sha256:'+'A'*64):
            with self.subTest(digest=digest):
                item=self.listar([{'name':'menor:latest','digest':digest,'prompt':'Não publicar.'}])[0]
                self.assertEqual(item,{'nome':'menor:latest','nuvem':False,'digest':'sha256:'+'a'*64})

    def test_digest_ausente_invalido_ou_duplicado_divergente_nao_e_prova(self):
        for digest in (None,'sha256:nao-hash','https://fixture.invalid','a'*63,True):
            with self.subTest(digest=digest):
                self.assertNotIn('digest',self.listar([{'name':'menor:latest','digest':digest}])[0])
        modelos=[{'name':'menor:latest','digest':'a'*64},{'name':'menor:latest','digest':'b'*64}]
        self.assertNotIn('digest',self.listar(modelos)[0])


if __name__=='__main__':unittest.main()
