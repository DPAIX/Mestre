"""Integração F com disco/daemon/processos simulados; nenhum download real."""
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import armazenamento_ollama_f as armazenamento
import configurar_ia_local as configurar
import iniciar_servicos_locais as servicos
import instalacao_em_f as politica
import preparacao_autonoma as preparacao
import preparar_27b_leve as quantizacao
import preparar_inicio_automatico as componentes


class FluxoFTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name)/'F';self.raiz.mkdir()
        self.env=self.raiz/'.env';self.env.write_text('OLLAMA_HABILITADO=1\nOLLAMA_URL=http://127.0.0.1:11434\nOUTRA_OPCAO=preservada\n')
        self.dados=self.raiz/'dados';self.dados.mkdir()
        self.codigo=self.raiz/'aplicativo';self.codigo.mkdir()
        self.python=self.codigo/'.venv'/'Scripts'/'python.exe'
        self.python.parent.mkdir(parents=True);self.python.write_text('fixture')
        self.exe=self.raiz/'ollama.exe';self.exe.write_text('fixture')
        self.patches=ExitStack();self.addCleanup(self.patches.close)
        for p in (patch.dict(os.environ,{'MEUCONTROLEPC_SOMENTE_F':'1',
                'MEUCONTROLEPC_ENV':str(self.env),'MEUCONTROLEPC_DADOS':str(self.dados)},clear=True),
                patch.object(politica,'raiz',return_value=self.raiz),
                patch.object(politica,'validar_caminho',side_effect=lambda p:Path(p)),
                patch.object(politica,'preparar_pastas'),
                patch.object(servicos,'_executavel_ollama',return_value=self.exe)):
            self.patches.enter_context(p)

    def prova(self):
        return {'url':'http://127.0.0.1:11435','modelos':str(self.raiz/'modelos_ollama'),
                'iniciado':True,'importado':True}

    def test_so_salva_url_e_store_depois_da_prova_do_daemon(self):
        def conferir(*args,**kwargs):
            self.assertNotIn('11435',self.env.read_text())
            return self.prova()
        with patch.dict(sys.modules,{'psutil':SimpleNamespace()}), \
                patch.object(armazenamento,'garantir_armazenamento_f',side_effect=conferir) as garantir:
            r=servicos.garantir_ollama_em_f('http://127.0.0.1:11434')
        self.assertTrue(r['ok']);garantir.assert_called_once()
        self.assertIn('OLLAMA_URL=http://127.0.0.1:11435',self.env.read_text())
        self.assertIn('OUTRA_OPCAO=preservada',self.env.read_text())
        self.assertEqual(os.environ['OLLAMA_MODELS'],self.prova()['modelos'])

    def test_sem_prova_nao_muda_configuracao_nem_pede_pull(self):
        antes=self.env.read_bytes()
        with patch.dict(sys.modules,{'psutil':SimpleNamespace()}), \
                patch.object(armazenamento,'garantir_armazenamento_f',side_effect=armazenamento.FalhaArmazenamento('fixture')):
            r=servicos.garantir_ollama_em_f('http://127.0.0.1:11434')
        self.assertFalse(r['ok']);self.assertEqual(self.env.read_bytes(),antes)

    def test_python_bootstrap_sem_psutil_usa_venv_f_sem_pip_no_c(self):
        retorno=SimpleNamespace(returncode=0,stdout=json.dumps({'ok':True,**self.prova()}))
        with patch.dict(sys.modules,{'psutil':None}),patch.object(servicos.subprocess,'run',return_value=retorno) as run:
            self.assertTrue(servicos.garantir_ollama_em_f('http://127.0.0.1:11434')['ok'])
        comando=run.call_args.args[0]
        self.assertEqual(comando[0],str(self.python))
        self.assertIn('--garantir',comando);self.assertNotIn('pip',comando)
        self.assertEqual(run.call_args.kwargs['env']['TEMP'],str(self.raiz/'temporarios'))

    def test_cli_de_armazenamento_invalida_nao_aplica_opcoes(self):
        antes=self.env.read_bytes()
        with patch.dict(sys.modules,{'psutil':None}), \
                patch.object(servicos.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='invalido')):
            self.assertFalse(servicos.garantir_ollama_em_f('http://127.0.0.1:11434')['ok'])
        self.assertEqual(self.env.read_bytes(),antes)

    def test_preparar27b_nao_baixa_antes_de_comprovar_f(self):
        with patch.object(servicos,'garantir_ollama_em_f',return_value={'ok':False,'mensagem':'Store F não confirmado.'}), \
                patch.object(quantizacao,'_baixar') as baixar, \
                patch.object(configurar,'listar_catalogo') as catalogo:
            with self.assertRaises(quantizacao.FalhaPreparacao):
                quantizacao.preparar(self.env,self.dados,autorizado=True)
        baixar.assert_not_called();catalogo.assert_not_called()

    def test_destino_padrao_f_sem_usar_documents_do_windows(self):
        origem=self.raiz/'pacote';origem.mkdir()
        ctx=preparacao.caminhos(origem=origem)
        self.assertEqual(ctx.codigo,self.codigo)
        self.assertEqual(ctx.arquivo_env,self.env)
        self.assertEqual(ctx.backups,self.raiz/'backups_codigo')
        self.assertFalse((self.raiz/'Documents').exists())

    def test_metadados_nao_instalam_ollama_com_winget_em_c(self):
        with patch.object(preparacao.sys,'platform','win32'), \
                patch.dict(os.environ,{'OLLAMA_HABILITADO':'1'}), \
                patch.object(servicos,'_executavel_ollama',return_value=None), \
                patch.object(preparacao.subprocess,'run') as run:
            ctx=preparacao.caminhos(origem=self.raiz)
            self.assertFalse(preparacao._instalar_ollama_ausente(ctx))
        run.assert_not_called()

    def test_venv_em_f_e_criada_antes_de_pip_mesmo_com_bootstrap_explicito(self):
        self.python.unlink()
        bootstrap=self.raiz.parent/'C'/'python.exe'
        bootstrap.parent.mkdir();bootstrap.write_text('fixture')
        for nome in ('assistente_pc.py','nucleo.py','caminhos_instalacao.py',
                     'requirements.txt','requirements-voz-local.txt','transcritor_local.py'):
            (self.codigo/nome).write_text('fixture')
        import redirecionar_assistente as redirecionar
        plano=redirecionar.plano_execucao(self.codigo,self.env,self.dados,bootstrap,modo='start')
        comandos=[]
        def executar(comando,*args):
            comandos.append(comando)
            if comando[1:3]==['-m','venv']:
                self.assertEqual(comando[-1],str(self.codigo/'.venv'))
                self.python.write_text('venv fixture')
            return SimpleNamespace(returncode=0,stdout='')
        with patch.object(componentes,'_executar',side_effect=executar):
            novo=componentes.preparar_componentes(plano,python_explicito=True)
        pip=[c for c in comandos if c[1:3]==['-m','pip']]
        self.assertTrue(pip)
        self.assertTrue(all(c[0]==str(self.python) for c in pip))
        self.assertEqual(novo['python'],self.python)

    def test_venv_f_existente_e_usada_sem_instalar_no_bootstrap_c(self):
        bootstrap=self.raiz.parent/'C'/'python.exe'
        bootstrap.parent.mkdir();bootstrap.write_text('fixture')
        for nome in ('assistente_pc.py','nucleo.py','caminhos_instalacao.py',
                     'requirements.txt','requirements-voz-local.txt','transcritor_local.py'):
            (self.codigo/nome).write_text('fixture')
        import redirecionar_assistente as redirecionar
        plano=redirecionar.plano_execucao(self.codigo,self.env,self.dados,bootstrap,modo='start')
        with patch.object(componentes,'_executar',return_value=SimpleNamespace(returncode=0,stdout='')) as executar:
            componentes.preparar_componentes(plano,python_explicito=True)
        pip=[c.args[0] for c in executar.call_args_list if c.args[0][1:3]==['-m','pip']]
        self.assertTrue(pip);self.assertTrue(all(c[0]==str(self.python) for c in pip))

    def test_etapa27b_e_explicita_usando_python_f_e_sem_flag_no_bot(self):
        ctx=preparacao.caminhos(origem=self.raiz)
        motor=preparacao.Preparador(ctx);motor.python=self.python
        motor.item=Mock();motor.pendente=Mock();motor._configuracao=Mock()
        with patch.object(preparacao.subprocess,'run') as run:
            motor._modelo_27b_em_f();run.assert_not_called()
        with patch.dict(os.environ,{'MEUCONTROLEPC_PREPARAR_27B':'1'}), \
                patch.object(preparacao.subprocess,'run',return_value=SimpleNamespace(returncode=0)) as run, \
                patch.object(configurar,'valores_env',return_value={'OLLAMA_PERFIL':'equilibrado','OLLAMA_27B_LEVE':'1'}):
            motor._modelo_27b_em_f()
        self.assertEqual(run.call_args.args[0][0],str(self.python))
        self.assertNotIn('MEUCONTROLEPC_PREPARAR_27B',run.call_args.kwargs['env'])
        self.assertEqual(motor.item.call_args.args[2],'pronto')

    def test_etapa27b_falha_deixa_pendencia_sem_simular_sucesso(self):
        ctx=preparacao.caminhos(origem=self.raiz)
        motor=preparacao.Preparador(ctx);motor.python=self.python
        motor.item=Mock();motor.pendente=Mock()
        with patch.dict(os.environ,{'MEUCONTROLEPC_PREPARAR_27B':'1'}), \
                patch.object(preparacao.subprocess,'run',return_value=SimpleNamespace(returncode=2)), \
                patch.object(configurar,'valores_env',return_value={}):
            motor._modelo_27b_em_f()
        self.assertEqual(motor.item.call_args.args[2],'pendente');motor.pendente.assert_called_once()

    def test_gateway_antigo_c_nao_recebe_autenticacao_ou_geracao(self):
        import roteador_9router as router
        from multi_ia import FalhaAPI
        with patch.dict(os.environ,{'NINE_ROUTER_HABILITADO':'1','NINE_ROUTER_MODEL':'fixture/modelo'}), \
                patch('integracoes_9stack.servico_f_comprovado',return_value=False), \
                patch.object(router.urllib.request,'build_opener') as abrir:
            with self.assertRaises(FalhaAPI):router.listar_modelos()
        abrir.assert_not_called()

    def test_conversa_automatica_usa_ollama_quando_gateway_antigo_nao_e_f(self):
        import nucleo
        import servicos_chat
        roteador=Mock();roteador.catalogo_ollama.return_value={'habilitado':True,'modelos':[{'nome':'fixture:latest'}]}
        with patch.object(nucleo,'DADOS',self.dados), \
                patch('roteador_9router.configurado',return_value=True), \
                patch('integracoes_9stack.servico_f_comprovado',return_value=False), \
                patch('conversa_equipe.consultar_modelos',return_value={'texto':'Contribuição válida.','plano':None}) as consulta:
            servicos_chat.conversar('Explique números primos.','fixture-f',roteador,retornar_plano=True)
        self.assertEqual(consulta.call_args.args[2],['fixture:latest'])
        roteador.nine_router.assert_not_called()


if __name__=='__main__':unittest.main()
