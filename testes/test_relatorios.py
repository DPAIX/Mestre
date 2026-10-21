"""Apresentação da evidência local e externa sem consultas reais."""
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import assistente_pc as app


class RelatoriosTeste(unittest.TestCase):
    def test_analise_recebe_snapshot_sem_consulta(self):
        roteador=MagicMock()
        snapshot={'Gemini':{'categoria':'servidor_ocupado','codigo':503}}
        roteador.estado_local.return_value=snapshot
        with patch.object(app,'ROTEADOR',roteador),patch.object(app,'autoanalisar',return_value={'estado':'ok'}) as analisar:
            self.assertEqual(app.analisar_sessao(),{'estado':'ok'})
        analisar.assert_called_once_with(estado_provedores=snapshot)
        roteador.responder.assert_not_called()

    def test_relatorio_distingue_registros_de_falhas_locais(self):
        relatorio={'estado':'avisos externos','estado_local':'sem falhas locais detectadas',
                   'verificacoes_ok':21,'problemas_locais':[],
                   'avisos_externos':[{'alvo':'api_Gemini','provedor':'Gemini',
                                      'detalhe':'Sobrecarga do provedor (HTTP 503).',
                                      'orientacao':'Aguarde e envie /ia novamente.'}],
                   'problemas':[],'falhas_recentes':1,'falhas_historicas':7,'sugestoes':[]}
        texto=app.texto_relatorio(relatorio)
        self.assertIn('sem falhas locais',texto)
        self.assertIn('0 aviso(s) local(is)',texto)
        self.assertIn('HTTP 503',texto)
        self.assertIn('/ia',texto)
        self.assertIn('Contagem de registros',texto)
        self.assertNotIn('falhas ativas',texto)
        self.assertNotIn('créditos',texto)

    def test_backup_atualizado_nao_promete_reparo_da_api(self):
        texto=app.texto_melhorias({'sem_alteracoes':True,'acoes':[
            {'acao':'backup/notebook/robotask','resultado':'já atualizado','detalhes':'Nenhuma entrada mudou.'}]})
        self.assertIn('Arquivos locais já atualizados',texto)
        self.assertIn('não alteram a disponibilidade das APIs',texto)

    def test_status_nao_esquece_falha_apos_pausa(self):
        for sucesso in (None,100):
            with self.subTest(sucesso=sucesso):
                roteador=MagicMock()
                roteador.status.return_value={'Gemini':'configurado; não testado'}
                roteador.estado_local.return_value={'Gemini':{
                    'configurado':True,'em_pausa':False,'categoria':'servidor_ocupado',
                    'codigo':503,'falha_em':100,'sucesso_em':sucesso}}
                with patch.object(app,'ROTEADOR',roteador):texto=app.mostrar_ias()
                self.assertIn('HTTP 503',texto)
                self.assertIn('recuperação ainda não verificada',texto)
                self.assertNotIn('Gemini: configurado; não testado',texto)
                roteador.responder.assert_not_called()

    def test_ultimo_sucesso_nao_promete_online_atual(self):
        roteador=MagicMock()
        roteador.status.return_value={'Gemini':'configurado; não testado'}
        roteador.estado_local.return_value={'Gemini':{
            'configurado':True,'em_pausa':False,'categoria':'servidor_ocupado',
            'codigo':503,'falha_em':100,'sucesso_em':101}}
        with patch.object(app,'ROTEADOR',roteador):texto=app.mostrar_ias()
        self.assertIn('respondeu na última consulta',texto)
        self.assertIn('disponibilidade atual não verificada',texto)


if __name__=='__main__':unittest.main()
