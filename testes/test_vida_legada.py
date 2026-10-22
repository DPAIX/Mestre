"""Compatibilidade com os exemplos distribuídos e hábitos mistos, sem dados reais."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import nucleo
import evolucao_segura


class VidaLegadaTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.dados=Path(self.tmp.name)
        alteracao=patch.object(nucleo,'DADOS',self.dados)
        alteracao.start();self.addCleanup(alteracao.stop)
        ambiente=patch.dict(os.environ,{'ROBOTASK_TASKS_DIR':str(self.dados/'tarefas-inexistentes')})
        ambiente.start();self.addCleanup(ambiente.stop)
        self.exemplo=json.loads((nucleo.BASE/'dados_iniciais'/'gestao_vida.json').read_text(encoding='utf-8'))
        nucleo.gravar_json('gestao_vida.json',self.exemplo)
        nucleo.gravar_json('minhas_macros.json',{})
        nucleo.gravar_json('base_auto_aprendizado.json',{})

    def test_exemplo_distribuido_passa_sem_alterar_bytes(self):
        arquivo=self.dados/'gestao_vida.json';antes=arquivo.read_bytes()
        self.assertEqual(nucleo.vida(),self.exemplo)
        self.assertEqual(arquivo.read_bytes(),antes)

    def test_habitos_textuais_e_fracionarios_nao_bloqueiam_operacoes_locais(self):
        valor=copy.deepcopy(self.exemplo)
        valor['habitos_saude']['Horas_Sono']['valor']=7.5
        valor['habitos_saude']['Exercicio_Minutos']['valor']=22.5
        valor['habitos_saude']['Personalizado']={'valor':'Bem','meta':'Manter','observacao':'fixture'}
        valor['campo_futuro']={'fixture':['preservar']}
        nucleo.gravar_json('gestao_vida.json',valor)
        habitos=copy.deepcopy(valor['habitos_saude'])
        self.assertEqual(nucleo.resumo_status()['agua'],0)
        self.assertEqual(nucleo.registrar_agua(),(1,8))
        self.assertEqual(nucleo.registrar_pomodoro(),1)
        self.assertEqual(nucleo.movimentar('entrada',1,'fixture'),1)
        final=nucleo.vida()
        for nome in ('Horas_Sono','Exercicio_Minutos','Pausa_Mental_Foco','Personalizado'):
            self.assertEqual(final['habitos_saude'][nome],habitos[nome])
        self.assertEqual(final['campo_futuro'],valor['campo_futuro'])

    def test_autoanalise_do_exemplo_nao_inventa_erro_de_integridade(self):
        with patch.object(nucleo.shutil,'disk_usage') as disco:
            disco.return_value.free=8*1024**3
            relatorio=evolucao_segura.analisar(registrar_resultado=False)
        erros=[p for p in relatorio['problemas_locais'] if p['nivel']=='erro']
        self.assertEqual(erros,[])

    def test_reparo_do_exemplo_preserva_habitos_e_arquivo_original(self):
        arquivo=self.dados/'gestao_vida.json';antes=arquivo.read_bytes()
        resultado=nucleo.reparo_seguro()
        self.assertIn('status',resultado)
        self.assertEqual(arquivo.read_bytes(),antes)

    def test_melhorias_com_exemplo_completo_geram_backup_e_notebook(self):
        arquivo=self.dados/'gestao_vida.json';antes=arquivo.read_bytes()
        resultado=evolucao_segura.melhorar(('backup','notebook'))
        self.assertFalse(resultado['codigo_modificado'])
        self.assertTrue(Path(resultado['backup']).is_file())
        self.assertTrue((self.dados/'tabela_rotina.csv').is_file())
        self.assertTrue((self.dados/'analise_autonoma_rotina.ipynb').is_file())
        self.assertTrue(all(item['resultado']=='concluído' for item in resultado['acoes']))
        self.assertEqual(arquivo.read_bytes(),antes)

    def test_contadores_invalidos_sao_recusados_sem_gravar(self):
        arquivo=self.dados/'gestao_vida.json'
        for nome in ('Agua_Copos','Pomodoros_Hoje'):
            for campo in ('valor','meta'):
                for numero in (-1,0.5,True,'Normal','Infinity','1e9999',None,[]):
                    with self.subTest(nome=nome,campo=campo,numero=numero):
                        valor=copy.deepcopy(self.exemplo)
                        valor['habitos_saude'].setdefault(nome,{})[campo]=numero
                        nucleo.gravar_json('gestao_vida.json',valor);antes=arquivo.read_bytes()
                        with self.assertRaises(ValueError) as erro:nucleo.vida()
                        self.assertIn('habitos_saude.'+nome+'.'+campo,str(erro.exception))
                        self.assertEqual(arquivo.read_bytes(),antes)

    def test_erro_estrutural_informa_campo_e_nao_seu_conteudo(self):
        valor=copy.deepcopy(self.exemplo)
        valor['financeiro']['saldo']='valor-ficticio-privado'
        nucleo.gravar_json('gestao_vida.json',valor)
        with self.assertRaises(ValueError) as erro:nucleo.vida()
        self.assertIn('financeiro.saldo',str(erro.exception))
        self.assertNotIn('valor-ficticio-privado',str(erro.exception))

    def test_contador_legado_em_string_numerica_continua_funcionando(self):
        valor=copy.deepcopy(self.exemplo)
        valor['habitos_saude']['Agua_Copos']['valor']='2'
        valor['habitos_saude']['Agua_Copos']['meta']='8'
        nucleo.gravar_json('gestao_vida.json',valor)
        self.assertEqual(nucleo.registrar_agua(),(3,8))
        self.assertEqual(nucleo.vida()['habitos_saude']['Agua_Copos']['meta'],'8')


if __name__=='__main__':unittest.main()
