"""Configuração guiada com subprocessos e integrações totalmente simulados."""
from __future__ import annotations

import contextlib
import importlib
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import configuracao_assistente as local
import configurar_9router as cliente
import diagnostico_ollama as diagnostico
import integracoes_9stack as stack
import roteador_9router as gateway


class ConfiguracaoAssistente(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        for alvo,nome,valor in ((local,'_PROCESSO',None),(local.sys,'platform','win32')):
            p=patch.object(alvo,nome,valor);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'PATH':'fixture-path','SYSTEMROOT':'fixture-system',
            'MEUCONTROLEPC_ENV':str(self.raiz/'config-ficticia.env'),
            'MEUCONTROLEPC_DADOS':str(self.raiz/'dados-ficticios'),
            'OLLAMA_URL':'http://127.0.0.1:11434',
            'TELEGRAM_TOKEN':'SEGREDO_BOT_FIXTURE','NINE_ROUTER_API_KEY':'SEGREDO_GATEWAY_FIXTURE',
            'OPENAI_API_KEY':'SEGREDO_OPENAI_FIXTURE','NODE_OPTIONS':'-r codigo_nao_herdar',
            'PYTHONPATH':'codigo_nao_herdar'},clear=True)
        p.start();self.addCleanup(p.stop)
        self.itens=[{'servico':nome,'nome':item['nome'],'instalado_gerenciado':False}
                    for nome,item in stack.SERVICOS.items()]
        p=patch.object(stack,'catalogo_9stack',return_value=self.itens)
        self.catalogo=p.start();self.addCleanup(p.stop)
        p=patch.object(gateway,'diagnostico_local',return_value={'configurado':False})
        self.gateway=p.start();self.addCleanup(p.stop)

    def test_importacao_e_plano_nao_sondam_ou_abrem_programas(self):
        with patch.object(local.subprocess,'Popen') as processo, \
                patch.object(local.shutil,'which') as caminho:
            importlib.reload(local)
            plano=local.preparar_configuracao()
            self.assertEqual(plano,local.plano_configuracao())
            self.assertEqual(set(plano),{'acao','campos','descricao'})
            self.assertEqual(plano['acao'],'configurar_assistente')
            self.assertEqual(plano['campos'],{})
            self.assertLessEqual(len(plano['descricao']),500)
            processo.assert_not_called();caminho.assert_not_called()
        self.catalogo.assert_not_called();self.gateway.assert_not_called()

    def test_resumo_e_local_sem_env_dados_processos_ou_consulta_ollama(self):
        with patch.object(local,'_dependencia',return_value=False), \
                patch.object(local.shutil,'which',return_value=None), \
                patch.object(Path,'read_text',side_effect=AssertionError('Não ler configuração.')), \
                patch.object(Path,'read_bytes',side_effect=AssertionError('Não ler dados.')), \
                patch.object(local.subprocess,'run') as run,patch.object(local.subprocess,'Popen') as popen, \
                patch.object(diagnostico,'consultar') as consulta:
            resumo=local.resumo_configuracao()
        self.assertIn('pendente',resumo.lower())
        self.assertIn('nodejs.org',resumo)
        self.assertIn('sem consulta às IAs',resumo)
        self.assertNotIn('SEGREDO',resumo)
        self.assertLessEqual(len(resumo),2400)
        run.assert_not_called();popen.assert_not_called();consulta.assert_not_called()

    def test_presente_nao_vira_afirmacao_de_servico_online(self):
        self.itens[0]['instalado_gerenciado']=True
        self.gateway.return_value={'configurado':True}
        with patch.object(local,'_dependencia',return_value=True),patch.object(local.shutil,'which',return_value='fixture'):
            resumo=local.resumo_configuracao()
        self.assertIn('pacote gerenciado presente; serviço não testado',resumo)
        self.assertIn('contas e resposta não verificadas',resumo)
        self.assertNotIn('online',resumo)
        self.assertNotIn('funcionando',resumo)

    def test_abertura_exige_confirmacao_estrita_antes_de_ler_caminhos(self):
        with patch.object(local,'_ambiente_configurador') as ambiente,patch.object(local.subprocess,'Popen') as popen:
            for confirmado in (False,None,1,'sim'):
                with self.subTest(confirmado=confirmado),self.assertRaises(PermissionError):
                    local.abrir_configuracao(confirmado=confirmado)
            ambiente.assert_not_called();popen.assert_not_called()

    def test_abertura_usa_console_separado_e_nao_herda_segredos(self):
        processo=SimpleNamespace(poll=lambda:None)
        with patch.object(local.subprocess,'Popen',return_value=processo) as popen:
            retorno=local.abrir_configuracao(confirmado=True)
            segunda=local.abrir_configuracao(confirmado=True)
        popen.assert_called_once()
        chamada=popen.call_args
        self.assertEqual(chamada.args[0],[sys.executable,str(Path(local.__file__).resolve()),'--assistente'])
        self.assertIs(chamada.kwargs['shell'],False)
        self.assertTrue(chamada.kwargs['close_fds'])
        self.assertEqual(chamada.kwargs['creationflags'],0x10)
        ambiente=chamada.kwargs['env']
        self.assertNotIn('SEGREDO',repr(ambiente))
        self.assertNotIn('NODE_OPTIONS',ambiente);self.assertNotIn('PYTHONPATH',ambiente)
        self.assertEqual(ambiente['MEUCONTROLEPC_ENV'],str(self.raiz/'config-ficticia.env'))
        self.assertEqual(ambiente['MEUCONTROLEPC_DADOS'],str(self.raiz/'dados-ficticios'))
        self.assertIn('nenhuma IA',retorno)
        self.assertIn('já está aberta',segunda)

    def test_configurador_encerrado_pode_ser_aberto_novamente_sem_matar(self):
        with patch.object(local,'_PROCESSO',SimpleNamespace(poll=lambda:0)), \
                patch.object(local.subprocess,'Popen',return_value=SimpleNamespace(poll=lambda:None)) as popen:
            local.abrir_configuracao(confirmado=True)
        popen.assert_called_once()

    def test_fora_windows_ou_falha_abertura_nao_repete_ou_expoe_dados(self):
        with patch.object(local.sys,'platform','linux'),patch.object(local.subprocess,'Popen') as popen:
            with self.assertRaises(RuntimeError):local.abrir_configuracao(confirmado=True)
            popen.assert_not_called()
        with patch.object(local.subprocess,'Popen',side_effect=OSError('SEGREDO_FIXTURE')) as popen:
            with self.assertRaises(RuntimeError) as erro:local.abrir_configuracao(confirmado=True)
            self.assertNotIn('SEGREDO',str(erro.exception));popen.assert_called_once()

    def test_etapas_arbitrarias_remotas_e_sem_confirmacao_sao_recusadas(self):
        with patch.object(stack,'executar_9stack') as executar,patch.object(stack,'instalar_9stack') as instalar:
            for etapa in ('iniciar_9remote','9remote start','instalar; calc',None,[]):
                with self.subTest(etapa=etapa),self.assertRaises(ValueError):
                    local.executar_etapa(etapa,confirmado=True)
            for etapa,_ in local._ETAPAS:
                with self.subTest(etapa=etapa),self.assertRaises(PermissionError):local.executar_etapa(etapa)
            executar.assert_not_called();instalar.assert_not_called()

    def test_instalacao_aguarda_worker_existente_e_pula_pacote_presente(self):
        self.itens[0]['instalado_gerenciado']=True
        with patch.object(stack,'instalar_9stack',return_value='Pacote conferido.') as instalar:
            resultado=local.executar_etapa('instalar_9router',confirmado=True)
            instalar.assert_not_called()
            self.assertIn('Não foi reinstalado',resultado)
            self.assertEqual(local.executar_etapa('instalar_9remote',confirmado=True),'Pacote conferido.')
            instalar.assert_called_once_with('9remote',confirmado=True)

    def test_etapa_9router_somente_inicia_gateway_e_abre_dashboard(self):
        with patch.object(stack,'executar_9stack',side_effect=['Início solicitado.','Dashboard solicitado.']) as executar:
            mensagem=local.executar_etapa('preparar_9router',confirmado=True)
        self.assertEqual([c.args for c in executar.call_args_list],[('9router','iniciar'),('9router','abrir')])
        self.assertTrue(all(c.kwargs=={'confirmado':True} for c in executar.call_args_list))
        self.assertIn('Conecte suas contas',mensagem)

    def test_etapa_9remote_abre_ui_sem_tunel(self):
        with patch.object(stack,'executar_9stack',return_value='Interface solicitada.') as executar:
            local.executar_etapa('abrir_9remote',confirmado=True)
        executar.assert_called_once_with('9remote','abrir',confirmado=True)

    def test_ollama_consulta_so_metadados_uma_vez_sem_geracao(self):
        with patch.object(diagnostico,'consultar',side_effect=[{'ok':True,'dados':{'version':'fixture'}},
                {'ok':True,'dados':{'models':[{'name':'llama3.2:latest'}]}}]) as consultar:
            mensagem=local.executar_etapa('consultar_ollama',confirmado=True)
        self.assertEqual([c.args[1] for c in consultar.call_args_list],['/api/version','/api/tags'])
        self.assertTrue(all(c.kwargs=={'timeout':3} for c in consultar.call_args_list))
        self.assertIn('1 modelo(s)',mensagem)
        self.assertIn('não foi testada',mensagem)

    def test_metadados_ollama_falhos_nao_disparam_retry_catalogo_ou_ia(self):
        with patch.object(diagnostico,'consultar',return_value={'ok':False,'categoria':'timeout'}) as consulta:
            mensagem=local.executar_etapa('consultar_ollama',confirmado=True)
        consulta.assert_called_once()
        self.assertIn('Nenhuma geração',mensagem)
        with patch.dict(os.environ,{'OLLAMA_URL':'http://example.invalid'}), \
                patch.object(diagnostico,'consultar') as consulta:
            with self.assertRaises(ValueError):local.executar_etapa('consultar_ollama',confirmado=True)
            consulta.assert_not_called()

    def test_configuracao_9router_usa_console_existente_sem_passar_chave(self):
        with patch.object(cliente,'main',return_value=0) as configurar:
            mensagem=local.executar_etapa('configurar_9router',confirmado=True)
        configurar.assert_called_once_with([])
        self.assertIn('cancelada não ativa',mensagem)

    def test_wizard_e_finito_e_nao_aciona_etapas_na_resposta_vazia(self):
        with patch.object(local,'resumo_configuracao',return_value='Resumo local.'), \
                patch('builtins.input',return_value='') as entrada, \
                patch.object(local,'executar_etapa') as executar,contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(local.assistente(),0)
        self.assertEqual(entrada.call_count,len(local._ETAPAS));executar.assert_not_called()
        self.assertIn('continuam pendentes',saida.getvalue())

    def test_wizard_nao_repete_etapa_falha_nem_mostra_excecao_bruta(self):
        respostas=['sim','sim']+['']*(len(local._ETAPAS)-2)
        with patch.object(local,'resumo_configuracao',return_value='Resumo.'), \
                patch('builtins.input',side_effect=respostas), \
                patch.object(local,'executar_etapa',side_effect=[RuntimeError('SEGREDO_FIXTURE'),'Segunda etapa encerrada.']) as executar, \
                contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(local.assistente(),0)
        self.assertEqual(executar.call_count,2)
        self.assertNotIn('SEGREDO',saida.getvalue())
        self.assertIn('continua pendente',saida.getvalue())
        self.assertIn('Segunda etapa encerrada',saida.getvalue())

    def test_cli_resumo_nao_inicia_wizard_e_interrupcao_e_limpa(self):
        with patch.object(local,'resumo_configuracao',return_value='Resumo local.'), \
                patch.object(local,'assistente') as assistente,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(local.main(['--resumo']),0)
            assistente.assert_not_called()
        with patch.object(local,'assistente',side_effect=EOFError),contextlib.redirect_stdout(io.StringIO()) as saida:
            self.assertEqual(local.main([]),0)
        self.assertIn('nenhuma nova etapa',saida.getvalue())


if __name__=='__main__':unittest.main()
