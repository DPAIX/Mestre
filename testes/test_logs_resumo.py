"""Logs usam fixtures: detalhes úteis apenas da última falha autorizada."""
import copy
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app


def evento(indice,status='sucesso',detalhes='Pedido privado de fixture.'):
    return {'timestamp':f'2026-10-23T16:48:{indice:02d}','acao':'comando_'+str(indice),
            'status':status,'detalhes':detalhes,'provedor':'local'}


class LogsResumo(unittest.TestCase):
    def test_resumo_preserva_ultimos_quinze_e_causa_da_ultima_falha(self):
        eventos=[evento(i) for i in range(20)]
        eventos[2]=evento(2,'falha','Falha antiga que não deve aparecer.')
        eventos[18]=evento(18,'falha',"TypeError: preparar_pedido_natural() got an unexpected keyword argument 'chat_id'")
        antes=copy.deepcopy(eventos)
        texto=app.texto_logs_resumo(eventos)
        self.assertIn('comando_5 sucesso',texto)
        self.assertIn('comando_19 sucesso',texto)
        self.assertNotIn('comando_4 sucesso',texto)
        self.assertIn('Última falha registrada (2026-10-23T16:48:18)',texto)
        self.assertIn("unexpected keyword argument 'chat_id'",texto)
        self.assertNotIn('Falha antiga',texto)
        self.assertNotIn('Pedido privado',texto)
        self.assertEqual(eventos,antes)

    def test_detalhe_de_falha_antiga_tem_data_sem_parecer_nova(self):
        eventos=[evento(0,'ERRO','Causa de fixture antiga.')]+[evento(i) for i in range(1,20)]
        texto=app.texto_logs_resumo(eventos)
        self.assertIn('Última falha registrada (2026-10-23T16:48:00)',texto)
        self.assertIn('Causa de fixture antiga.',texto)

    def test_redige_credenciais_legadas_antes_do_corte(self):
        segredo='fixture-segredo-sem-prefixo-'+('x'*600)
        detalhes='Falha: api_key='+segredo+'; Authorization: Bearer fixture-outro-segredo'
        texto=app.texto_logs_resumo([evento(1,'indisponivel',detalhes)])
        self.assertNotIn('fixture-segredo',texto)
        self.assertNotIn('fixture-outro-segredo',texto)
        self.assertIn('REDACTADA',texto)

    def test_campos_resumo_tambem_sao_redigidos_e_sem_injecao_de_linhas(self):
        item=evento(1,'falha','Falha\nsegunda linha de fixture')
        item['acao']='api_key=fixture-injetado\nOUTRO STATUS'
        texto=app.texto_logs_resumo([item])
        self.assertNotIn('fixture-injetado',texto)
        self.assertNotIn('\nOUTRO STATUS',texto)
        self.assertNotIn('Falha\nsegunda',texto)

    def test_limites_incluem_unicode_e_nao_retornam_todos_os_logs(self):
        eventos=[evento(i,'falha','😀'*10000) for i in range(300)]
        for item in eventos:
            item.update(timestamp='😀'*100,acao='😀'*100,status='falha')
        texto=app.texto_logs_resumo(eventos)
        self.assertLessEqual(len(texto),2000)
        self.assertLessEqual(len(texto.encode('utf-16-le'))//2,4000)
        self.assertEqual(sum(linha.endswith(' falha') for linha in texto.splitlines()),15)

    def test_estrutura_invalida_vazios_e_falhas_sem_detalhe(self):
        for invalido in (None,{},'registros',10):
            with self.subTest(invalido=invalido),self.assertRaises(ValueError):
                app.texto_logs_resumo(invalido)
        self.assertIn('Nenhum registro disponível',app.texto_logs_resumo([None,'invalido']))
        for detalhe in (None,{},'',5):
            self.assertIn('Detalhes não registrados',app.texto_logs_resumo([evento(1,'falha',detalhe)]))

    def test_logs_autorizado_exibe_causa_sem_consulta_de_ia(self):
        mensagem=SimpleNamespace(text='/logs',chat=SimpleNamespace(id=10),from_user=SimpleNamespace(id=1),message_thread_id=0)
        bot=MagicMock()
        with patch.dict(os.environ,{'TELEGRAM_ALLOWED_USER_IDS':'1'},clear=True), \
                patch.object(app,'BOT',bot), \
                patch.object(app,'ler_json',return_value=[evento(1,'falha','Causa de fixture.')]) as ler, \
                patch.object(app.ROTEADOR,'responder') as ia:
            app.tratar_pedido(mensagem)
        ler.assert_called_once_with('log_acoes_e_erros.json',[])
        ia.assert_not_called()
        self.assertIn('Causa de fixture.',bot.send_message.call_args.args[1])

    def test_nao_autorizado_nao_le_nem_exibe_logs(self):
        mensagem=SimpleNamespace(text='/logs',chat=SimpleNamespace(id=10),from_user=SimpleNamespace(id=2),message_thread_id=0)
        bot=MagicMock()
        with patch.dict(os.environ,{'TELEGRAM_ALLOWED_USER_IDS':'1'},clear=True), \
                patch.object(app,'BOT',bot),patch.object(app,'ler_json') as ler:
            app.tratar_pedido(mensagem)
        ler.assert_not_called()
        bot.send_message.assert_not_called()
        self.assertIn('Acesso negado',bot.reply_to.call_args.args[1])


if __name__=='__main__':unittest.main()
