"""Orçamento CPU e consultas de metadados com dados/HTTP somente fictícios."""
from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configurar_ia_local as configurar
import conversa_equipe as equipe
import multi_ia as ia

GIB=1024**3
MODELOS=['qwen3.8:27b','mistral:latest','llama3.2:latest','qwen3.5:4b']
CATALOGO=[{'nome':nome,'nuvem':False,'tamanho_bytes':tamanho}
          for nome,tamanho in zip(MODELOS,(int(16.52*GIB),4*GIB,2*GIB,3*GIB))]


class VelocidadeEquipeTeste(unittest.TestCase):
    def setUp(self):
        env=patch.dict(os.environ,{'OLLAMA_HABILITADO':'1','OLLAMA_PERFIL':'cpu',
            'OLLAMA_MODEL':'llama3.2:latest','OLLAMA_URL':'http://127.0.0.1:11434'},clear=True)
        env.start();self.addCleanup(env.stop)
        for alvo,valor in (('ler_json',{}),('gravar_json',None),('registrar',None)):
            p=patch.object(ia,alvo,return_value=valor)
            p.start();self.addCleanup(p.stop)
        p=patch.object(configurar,'listar_catalogo',side_effect=lambda *a:copy.deepcopy(CATALOGO))
        self.listar=p.start();self.addCleanup(p.stop)
        self.agora=1000
        p=patch.object(ia.time,'monotonic',side_effect=lambda:self.agora)
        p.start();self.addCleanup(p.stop)
        p=patch.object(ia,'memoria_fisica_bytes',return_value=16*GIB)
        self.memoria=p.start();self.addCleanup(p.stop)
        p=patch.object(equipe,'_TRAVA',threading.Lock())
        p.start();self.addCleanup(p.stop)
        self.roteador=ia.Roteador()

    def gerar(self,modelo='llama3.2:latest',**opcoes):
        with patch.object(ia,'postar',return_value={'message':{'content':'Contribuição local.'}}) as enviar:
            resposta=self.roteador.ollama('Compare as opções.',modelo=modelo,**opcoes)
        self.assertEqual(resposta,'Contribuição local.')
        enviar.assert_called_once()
        return enviar.call_args.args[2]

    def test_catalogo_explicito_e_fresco_e_cache_cpu_usa_copias(self):
        catalogo=self.roteador.catalogo_ollama()
        catalogo['modelos'][2]['nuvem']=True
        catalogo['modelos'][2]['tamanho_bytes']=999*GIB
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,1)
        self.roteador.catalogo_ollama()
        self.assertEqual(self.listar.call_count,2)
        copiado=self.roteador._obter_catalogo_ollama('http://127.0.0.1:11434',usar_cache=True)
        copiado.clear()
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,2)

    def test_cache_expira_em_cinco_segundos_sem_renovacao_por_leitura(self):
        self.roteador.catalogo_ollama()
        self.agora+=4
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,1)
        self.agora+=1
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,2)

    def test_trocar_endpoint_ou_invalidar_exige_nova_leitura(self):
        self.roteador.catalogo_ollama()
        os.environ['OLLAMA_URL']='http://127.0.0.1:11435'
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_args.args,('http://127.0.0.1:11435',))
        self.assertEqual(self.listar.call_count,2)
        self.roteador.invalidar_catalogo_ollama()
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,3)

    def test_erro_de_metadados_nao_preserva_cache_anterior(self):
        self.roteador.catalogo_ollama()
        self.listar.side_effect=configurar.FalhaConfiguracao('Serviço fictício indisponível.')
        with self.assertRaises(ia.FalhaAPI):self.roteador.catalogo_ollama()
        self.assertIsNone(self.roteador._catalogo_cpu_cache)
        self.listar.side_effect=lambda *a:copy.deepcopy(CATALOGO)
        self.gerar(modo_cooperativo=True)
        self.assertEqual(self.listar.call_count,3)

    def test_erro_http_ou_rede_invalida_cache_sem_repetir_geracao(self):
        for codigo,categoria in ((404,'modelo_indisponivel'),(0,'rede')):
            with self.subTest(codigo=codigo):
                self.roteador.catalogo_ollama()
                with patch.object(ia,'postar',side_effect=ia.FalhaAPI('Ollama',codigo,'Fixture falhou.',categoria)) as enviar, \
                        patch.object(configurar,'listar_modelos',return_value=MODELOS):
                    with self.assertRaises(ia.FalhaAPI):self.roteador.ollama('Pedido.',modelo=MODELOS[2],modo_cooperativo=True)
                self.assertIsNone(self.roteador._catalogo_cpu_cache)
                enviar.assert_called_once()

    def test_modelo_maior_que_orcamento_fisico_nao_inicia_geracao_cooperativa(self):
        with patch.object(ia,'postar') as enviar:
            with self.assertRaises(ia.FalhaAPI) as erro:
                self.roteador.ollama('Pedido.',modelo=MODELOS[0],modo_cooperativo=True)
        self.assertEqual(erro.exception.categoria,'recursos')
        self.assertIn('estimativa',erro.exception.detalhe)
        self.assertIn('continua selecionada',erro.exception.detalhe)
        self.assertIn('nenhuma geração',erro.exception.detalhe)
        enviar.assert_not_called()
        self.gerar(modelo=MODELOS[0])

    def test_ram_ou_tamanho_desconhecidos_nao_impedem_tentativa(self):
        self.memoria.return_value=None
        self.gerar(modelo=MODELOS[0],modo_cooperativo=True)
        self.roteador.invalidar_catalogo_ollama()
        self.listar.side_effect=lambda *a:[{'nome':n,'nuvem':False} for n in MODELOS]
        self.memoria.reset_mock()
        self.gerar(modelo=MODELOS[0],modo_cooperativo=True)
        self.memoria.assert_not_called()

    def test_perfil_padrao_nao_altera_execucao_por_orcamento_cpu(self):
        os.environ['OLLAMA_PERFIL']='padrao'
        payload=self.gerar(modelo=MODELOS[0],modo_cooperativo=True)
        self.assertEqual(payload['options'],{'num_ctx':4096,'num_predict':384})
        self.listar.assert_not_called()
        self.memoria.assert_not_called()

    def test_menores_geram_primeiro_e_relatorio_preserva_todas_as_tags(self):
        original=list(MODELOS)
        self.roteador.catalogo_ollama()
        with patch.object(ia,'postar',return_value={'message':{'content':'Contribuição.'}}) as enviar:
            resultado=equipe.consultar_modelos('Compare opções.',[],MODELOS,self.roteador,modo='cooperativa')
        self.assertEqual([c.args[2]['model'] for c in enviar.call_args_list],
            ['llama3.2:latest','qwen3.5:4b','mistral:latest','llama3.2:latest'])
        self.assertEqual(MODELOS,original)
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual([r['ok'] for r in resultado['resultados']],[False,True,True,True])
        self.assertIn('3/4 modelos responderam',resultado['texto'])
        self.assertIn('orçamento de RAM CPU',resultado['texto'])
        self.assertEqual(self.listar.call_count,1)

    def test_participante_adiado_nao_e_removido_do_consenso_de_acao(self):
        resposta=json.dumps({'resposta':'Proponho abrir.','acao':'pc','campos':{'comando':'calc'}})
        with patch.object(ia,'postar',return_value={'message':{'content':resposta}}) as enviar:
            resultado=equipe.consultar_modelos('Abra a calculadora.',[],MODELOS,self.roteador,
                modo='cooperativa',interpretar=True)
        self.assertIsNone(resultado['plano'])
        self.assertIn('Nenhuma ação foi preparada',resultado['texto'])
        self.assertEqual(len(resultado['resultados']),4)
        self.assertEqual(enviar.call_count,4)

    def test_sem_tamanhos_preserva_ordem_e_mock_nao_recebe_chamada_de_planejador(self):
        self.listar.side_effect=lambda *a:[{'nome':n,'nuvem':False} for n in MODELOS]
        self.assertEqual(self.roteador.ordenar_equipe_cpu(MODELOS),MODELOS)
        roteador=MagicMock()
        roteador.responder.return_value=('Resposta.','Ollama')
        resultado=equipe.consultar_modelos('Pedido.',[],MODELOS,roteador,modo='cooperativa')
        self.assertEqual([r['modelo'] for r in resultado['resultados']],MODELOS)
        self.assertEqual([c[0] for c in roteador.mock_calls],['responder']*5)

    def test_io_de_catalogo_nao_mantem_mutex_e_configuracao_trocada_nao_publica_cache(self):
        liberado=[]
        def listar(base):
            def conferir():
                adquirido=self.roteador.mutex.acquire(blocking=False)
                liberado.append(adquirido)
                if adquirido:self.roteador.mutex.release()
            t=threading.Thread(target=conferir)
            t.start();t.join(timeout=1)
            self.assertFalse(t.is_alive())
            os.environ['OLLAMA_URL']='http://127.0.0.1:11435'
            self.roteador.atualizar_configuracao_ollama()
            return copy.deepcopy(CATALOGO)
        self.listar.side_effect=listar
        self.roteador.catalogo_ollama()
        self.assertEqual(liberado,[True])
        self.assertIsNone(self.roteador._catalogo_cpu_cache)


class MetadadosPublicosTeste(unittest.TestCase):
    def test_tamanho_aceita_so_inteiros_positivos_e_nunca_hosts(self):
        itens=[{'name':'local:3b','size':3*GIB},
               {'name':'local:3b','size':4*GIB},
               {'name':'alias:latest','size':2*GIB,'remote_host':'https://nao-consultar.example'},
               *({'name':'fixture:'+str(i),'size':t} for i,t in enumerate((True,-1,0,'100',float('inf'),2**50)))]
        cliente=MagicMock()
        cliente.open.return_value=io.BytesIO(json.dumps({'models':itens}).encode())
        with patch.object(configurar.urllib.request,'build_opener',return_value=cliente):
            catalogo=configurar.listar_catalogo()
        self.assertEqual(catalogo[0],{'nome':'local:3b','nuvem':False,'tamanho_bytes':4*GIB})
        self.assertTrue(catalogo[1]['nuvem'])
        self.assertTrue(all('tamanho_bytes' not in m for m in catalogo[2:]))
        self.assertNotIn('nao-consultar',repr(catalogo))
        cliente.open.assert_called_once()

    def test_consulta_ram_usa_total_em_vez_de_memoria_livre_transitoria(self):
        psutil=SimpleNamespace(virtual_memory=lambda:SimpleNamespace(total=16*GIB,available=1),Error=RuntimeError)
        with patch.dict(sys.modules,{'psutil':psutil}):
            self.assertEqual(ia.memoria_fisica_bytes(),16*GIB)
        psutil.virtual_memory=lambda:(_ for _ in ()).throw(RuntimeError('Fixture sem permissão.'))
        with patch.dict(sys.modules,{'psutil':psutil}):
            self.assertIsNone(ia.memoria_fisica_bytes())


if __name__=='__main__':unittest.main()
