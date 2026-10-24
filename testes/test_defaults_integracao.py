"""Defaults completos com Telegram/serviço simulados e dados temporários."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app
import instancia_assistente as instancia
import iniciar_servicos_locais as servicos
import nucleo
import transcritor_local as local


class DefaultsIntegracaoTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        for modulo,nome,valor in ((nucleo,'DADOS',self.raiz),(app,'DADOS',self.raiz),
                                 (app,'BOT',MagicMock()),(app,'PENDENTES',{})):
            p=patch.object(modulo,nome,valor);p.start();self.addCleanup(p.stop)
        p=patch.dict(os.environ,{'TELEGRAM_TOKEN':'123456789:'+'X'*35,'TELEGRAM_ALLOWED_USER_IDS':'1'},clear=True)
        p.start();self.addCleanup(p.stop)
        self.contexto='1:10:0'

    def mensagem(self,texto='',usuario=1):
        return SimpleNamespace(chat=SimpleNamespace(id=10),from_user=SimpleNamespace(id=usuario),
            text=texto,message_thread_id=None,voice=SimpleNamespace(file_id='fixture',file_size=12),audio=None)

    def handler_voz(self):
        handlers={};bot=MagicMock()
        def registrar(**opcoes):
            def decorar(fn):
                for tipo in opcoes.get('content_types',[]):handlers[tipo]=fn
                return fn
            return decorar
        bot.message_handler.side_effect=registrar
        bot.callback_query_handler.side_effect=lambda **kw:lambda fn:fn
        with patch.dict(sys.modules,{'telebot':SimpleNamespace(TeleBot=MagicMock(return_value=bot))}):
            app.configurar_bot()
        bot.get_file.return_value=SimpleNamespace(file_path='fixture/voz.ogg')
        bot.download_file.return_value=b'fixture-audio'
        return handlers['voice'],bot

    def test_mensagem_comum_usa_todos_sem_comandos_de_ativacao(self):
        roteador=MagicMock();modelos=['llama3.2:latest','mistral:latest','qwen3.5:4b','qwen3.8:27b']
        roteador.catalogo_ollama.return_value={'habilitado':True,'modelos':[{'nome':m,'nuvem':False} for m in modelos]}
        roteador.responder.return_value=(json.dumps({'resposta':'Plano consolidado.','acao':'nenhuma','campos':{}}),'Ollama')
        with patch.object(app,'ROTEADOR',roteador),patch.object(app,'executar') as executar:
            app.tratar_pedido(self.mensagem('Compare estratégias para estudar melhor'))
        self.assertEqual(roteador.responder.call_count,5)
        self.assertEqual([c.kwargs['modelo_ollama'] for c in roteador.responder.call_args_list[:-1]],modelos)
        self.assertEqual(app.CENTRAL.obter_chat_ativo(self.contexto)['equipe_politica'],'automatica')
        executar.assert_not_called()
        self.assertIn('Plano consolidado',app.BOT.send_message.call_args.args[1])

    def test_nao_autorizado_nao_consulta_catalogo_ou_baixa_audio(self):
        handler,bot=self.handler_voz()
        with patch.object(app.ROTEADOR,'catalogo_ollama') as catalogo, \
                patch.object(local,'verificar_disponibilidade') as verificar:
            app.tratar_pedido(self.mensagem('Olá',usuario=2))
            handler(self.mensagem(usuario=2))
        catalogo.assert_not_called();verificar.assert_not_called()
        bot.get_file.assert_not_called();bot.download_file.assert_not_called()

    def test_voz_local_sem_gemini_prepara_confirmacao_e_nao_executa(self):
        handler,bot=self.handler_voz()
        with patch.object(local,'verificar_disponibilidade') as verificar, \
                patch.object(local,'transcrever_audio',return_value='Abra a calculadora') as transcrever, \
                patch.object(app,'inline',return_value=None),patch.object(app,'executar') as executar:
            handler(self.mensagem())
        verificar.assert_called_once();transcrever.assert_called_once_with(b'fixture-audio','audio/ogg')
        executar.assert_not_called();self.assertEqual(len(app.PENDENTES),1)
        pedido=next(iter(app.PENDENTES.values()))
        self.assertEqual(pedido['dados']['plano']['campos'],{'comando':'calc'})
        self.assertEqual(pedido['dados']['contexto'],self.contexto)
        bot.download_file.assert_called_once_with('fixture/voz.ogg')

    def test_falha_local_nao_baixa_audio_e_nao_faz_fallback_externo(self):
        handler,bot=self.handler_voz()
        with patch.object(local,'verificar_disponibilidade',side_effect=local.FalhaTranscritorLocal('Modelo não preparado','configuracao')), \
                patch.object(app.ROTEADOR,'responder') as responder:
            handler(self.mensagem())
        bot.get_file.assert_not_called();responder.assert_not_called()
        self.assertIn('Voz local',bot.send_message.call_args.args[1])

    def test_main_adquire_lock_antes_de_inicializar_e_executar(self):
        ordem=[]
        @contextlib.contextmanager
        def trava(pasta):
            self.assertEqual(pasta,self.raiz);ordem.append('lock')
            yield
            ordem.append('liberar')
        with patch.object(sys,'argv',['assistente_pc.py']),patch.object(app,'ler_env'), \
                patch.object(instancia,'instancia_unica',side_effect=trava), \
                patch.object(app,'inicializar',side_effect=lambda *a:ordem.append('inicializar')), \
                patch.object(app,'_executar_instancia',side_effect=lambda *a:ordem.append('executar')), \
                contextlib.redirect_stdout(io.StringIO()):app.main()
        self.assertEqual(ordem,['lock','inicializar','executar','liberar'])
        self.assertEqual(os.environ['OLLAMA_HABILITADO'],'1')

    def test_segundo_inicio_nao_toca_dados_ou_processos(self):
        with patch.object(sys,'argv',['assistente_pc.py']),patch.object(app,'ler_env'), \
                patch.object(instancia,'instancia_unica',side_effect=instancia.InstanciaAtiva('Já ativo')), \
                patch.object(app,'inicializar') as inicializar,patch.object(app,'_executar_instancia') as executar, \
                contextlib.redirect_stdout(io.StringIO()):app.main()
        inicializar.assert_not_called();executar.assert_not_called()

    def test_diagnostico_nao_inicia_servico_nem_registra_startup(self):
        with patch.object(sys,'argv',['assistente_pc.py','--diagnostico']),patch.object(app,'ler_env'), \
                patch.object(app,'inicializar'),patch.object(app,'diagnostico',return_value={}), \
                patch.object(instancia,'instancia_unica') as trava, \
                patch.object(servicos,'garantir_ollama') as iniciar,contextlib.redirect_stdout(io.StringIO()):app.main()
        trava.assert_not_called();iniciar.assert_not_called()

    def test_inicio_windows_abre_painel_sem_esperar_ollama(self):
        ordem=[];servidor=MagicMock();bot=MagicMock()
        sistema=SimpleNamespace(name='nt',getenv=os.getenv,environ=os.environ)
        with patch.object(app,'os',sistema),patch.object(app,'registrar'), \
                patch.object(servicos,'garantir_ollama',side_effect=lambda:ordem.append('ollama') or {'ok':True,'mensagem':'Metadados locais'}) as iniciar, \
                patch.object(app,'iniciar_painel',side_effect=lambda:ordem.append('painel') or servidor), \
                patch.object(app.threading,'Thread') as threads,patch.object(app,'catalogo_robotask'), \
                patch.object(app,'configurar_bot',return_value=bot),contextlib.redirect_stdout(io.StringIO()):
            app._executar_instancia(SimpleNamespace(somente_painel=False))
        self.assertEqual(ordem,['painel'])
        self.assertTrue(any(c.kwargs.get('target') is app.preparar_ia_em_segundo_plano for c in threads.call_args_list))
        iniciar.assert_not_called()
        bot.infinity_polling.assert_called_once();servidor.shutdown.assert_called_once();servidor.server_close.assert_called_once()


if __name__=='__main__':unittest.main()
