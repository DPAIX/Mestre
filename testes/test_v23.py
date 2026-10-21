"""Regressões de falhas do MeuControlePC v2.2 identificadas no ZIP de 13:43:55.

Sem chamadas externas, automações de mouse ou reinícios do Windows.
"""
from pathlib import Path
import datetime as dt
import tempfile
import unittest
from unittest.mock import patch,MagicMock
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import nucleo
import evolucao_segura as evo
import assistente_pc as app

class RegressaoV23(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.patch_dados=patch.object(nucleo,'DADOS',Path(self.temp.name))
        self.patch_dados.start()
        nucleo.gravar_json('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':0},'habitos_saude':{}})
        nucleo.gravar_json('minhas_macros.json',{})
        nucleo.gravar_json('base_auto_aprendizado.json',{})

    def tearDown(self):
        self.patch_dados.stop()
        self.temp.cleanup()

    def test_menu_multi_ia_responde_ao_chat_correto(self):
        fake=MagicMock()
        with patch.object(app,'BOT',fake),patch.object(app,'mostrar_ias',return_value='Provedores de teste'):
            app.menu_secundario(123456,app.MENU_BOTOES[6],123456)
        fake.send_message.assert_called_once_with(123456,'Provedores de teste')

    def test_auditoria_detecta_nome_global_inexistente(self):
        source='def menu_secundario(chat_id):\n    print(chat)\n'
        self.assertIn("menu_secundario: nome 'chat' não definido",evo.nomes_globais_indefinidos(source))

    def test_auditoria_aceita_codigo_corrigido(self):
        source='def menu_secundario(chat_id):\n    print(chat_id)\n'
        self.assertEqual(evo.nomes_globais_indefinidos(source),[])
        for nome in evo.FONTES:
            self.assertEqual(evo.nomes_globais_indefinidos((nucleo.BASE/nome).read_text(encoding='utf-8'),nome),[],nome)

    def test_autoanalise_informa_acao_e_causa_da_falha(self):
        nucleo.gravar_json('log_acoes_e_erros.json',[{
            'timestamp':dt.datetime.now().isoformat(timespec='seconds'),
            'acao':'comando','status':'falha','detalhes':"name 'chat' is not defined"
        }])
        r=evo.analisar(registrar_resultado=False)
        self.assertEqual(r['falhas_recentes'],1)
        self.assertTrue(any(x['alvo']=='log: comando' and "name 'chat'" in x['detalhe'] for x in r['problemas']))

    def test_autoanalise_rejeita_nome_inexistente_antes_de_melhorar(self):
        origem=nucleo.BASE
        with tempfile.TemporaryDirectory() as raiz:
            teste=Path(raiz)
            for nome in evo.FONTES:
                (teste/nome).write_bytes((origem/nome).read_bytes())
            (teste/'assistente_pc.py').write_text('def f(chat_id):\n    print(chat)\n',encoding='utf-8')
            with patch.object(nucleo,'BASE',teste):
                r=evo.analisar(registrar_resultado=False)
            self.assertTrue(any(x['alvo']=='assistente_pc.py' and "nome 'chat'" in x['detalhe'] for x in r['problemas']))

    def test_desligar_continua_bloqueado(self):
        self.assertEqual(nucleo.classificar_texto('desligar meu computador'),'desligamento_bloqueado')
        self.assertIn('não oferece desligamento',app.interpretar_comando('desligar computador'))

if __name__=='__main__': unittest.main()
