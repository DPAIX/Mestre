"""Retentativas de melhorias sem APIs, macros ou comandos do Windows."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import evolucao_segura as evol
import nucleo


class MelhoriasRegressoes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patch_dados=patch.object(nucleo,'DADOS',Path(self.tmp.name))
        self.patch_dados.start()
        self.addCleanup(self.patch_dados.stop)
        for nome,valor in (
            ('gestao_vida.json',{'rotina':[],'financeiro':{'saldo':1},'habitos_saude':{}}),
            ('minhas_macros.json',{}),('base_auto_aprendizado.json',{}),
            ('robotask_conhecimento.json',{'tarefas':[]})
        ):
            nucleo.gravar_json(nome,valor)
        # Representa arquivos de uma execução anterior que não provam sucesso atual.
        nucleo.gerar_notebook()

    def test_falha_notebook_com_arquivos_antigos_permite_retentar(self):
        with patch.object(nucleo,'gerar_notebook',side_effect=OSError('Disco indisponível na simulação')):
            primeira=evol.melhorar()
        self.assertEqual(next(a['resultado'] for a in primeira['acoes'] if a['acao']=='notebook'),'falha')
        with patch.object(nucleo,'gerar_notebook',wraps=nucleo.gerar_notebook) as gerar:
            segunda=evol.melhorar()
        self.assertFalse(segunda['sem_alteracoes'])
        gerar.assert_called_once_with()

    def test_falha_catalogo_com_arquivo_antigo_permite_retentar(self):
        with patch.object(evol.os,'name','nt'),patch.object(nucleo,'catalogo_robotask',side_effect=OSError('Catálogo indisponível na simulação')):
            primeira=evol.melhorar()
        self.assertEqual(next(a['resultado'] for a in primeira['acoes'] if a['acao']=='robotask'),'falha')
        with patch.object(evol.os,'name','nt'),patch.object(nucleo,'catalogo_robotask',return_value=[]) as catalogar:
            segunda=evol.melhorar()
        self.assertFalse(segunda['sem_alteracoes'])
        catalogar.assert_called_once_with()

    def test_backup_excluido_precisa_ser_recriado(self):
        primeira=evol.melhorar()
        Path(primeira['backup']).unlink()
        segunda=evol.melhorar()
        self.assertFalse(segunda['sem_alteracoes'])
        self.assertTrue(Path(segunda['backup']).is_file())

    def test_mudanca_durante_geracao_nao_marca_novos_dados_como_processados(self):
        gerar_original=nucleo.gerar_notebook
        marca_inicial=evol._impressao_dados()
        def gerar_e_mudar_entrada():
            arquivos=gerar_original()
            dados=nucleo.vida()
            dados['financeiro']['saldo']=50
            nucleo.gravar_json('gestao_vida.json',dados)
            return arquivos
        with patch.object(nucleo,'gerar_notebook',side_effect=gerar_e_mudar_entrada):
            primeira=evol.melhorar()
        self.assertEqual(primeira['impressao_dados'],marca_inicial)
        self.assertNotEqual(primeira['impressao_dados'],evol._impressao_dados())
        with patch.object(nucleo,'gerar_notebook',wraps=gerar_original) as gerar:
            segunda=evol.melhorar()
        self.assertFalse(segunda['sem_alteracoes'])
        gerar.assert_called_once_with()


if __name__=='__main__':unittest.main()
