"""Política de armazenamento, sem criar drives, processos ou arquivos reais de uso."""
import os
from pathlib import PureWindowsPath
import unittest
from unittest.mock import patch

import instalacao_em_f as politica


class PoliticaFTeste(unittest.TestCase):
    def setUp(self):
        p=patch.dict(os.environ,{},clear=True);p.start();self.addCleanup(p.stop)

    def test_somente_opt_in_explicito(self):
        self.assertFalse(politica.ativo())
        with patch.dict(os.environ,{'MEUCONTROLEPC_SOMENTE_F':'1'}):self.assertTrue(politica.ativo())
        with patch.dict(os.environ,{'MEUCONTROLEPC_SOMENTE_F':'sim'}):
            with self.assertRaises(ValueError):politica.ativo()

    def test_destino_e_caches_f_sem_trocar_perfil_windows_ou_segredos(self):
        with patch.dict(os.environ,{'TEMP':'C:/temp','OPENAI_API_KEY':'fixture-nao-copiar'}):
            env=politica.ambiente()
        for chave,valor in env.items():
            if chave in ('MEUCONTROLEPC_SOMENTE_F','PYTHONUTF8','PYTHONDONTWRITEBYTECODE'):continue
            self.assertEqual(PureWindowsPath(valor).drive.casefold(),'f:',chave)
        self.assertNotIn('OPENAI_API_KEY',env)
        self.assertNotIn('USERPROFILE',env)
        self.assertNotIn('APPDATA',env)
        self.assertNotIn('HOME',env)

    def test_rejeita_outro_drive_relativo_unc_ads_e_traversal(self):
        for caminho in ('C:/apps','G:/apps','F:apps','apps','//servidor/share/apps',
                        'F:/apps/../outro','F:/apps/cache:stream','F:/apps\nruim'):
            with self.subTest(caminho=caminho),self.assertRaises(ValueError):
                politica.validar_caminho(caminho)

    def test_aceita_f_maiusculo_ou_minusculo_e_espacos(self):
        for caminho in ('F:/MeuControlePC_v2','f:/meus programas/app'):
            self.assertEqual(PureWindowsPath(str(politica.validar_caminho(caminho))),PureWindowsPath(caminho))

    def test_raiz_configuravel_continua_restrita_ao_f(self):
        with patch.dict(os.environ,{'MEUCONTROLEPC_RAIZ_F':'F:/Aplicativos/Mestre'}):
            self.assertEqual(PureWindowsPath(str(politica.raiz())),PureWindowsPath('F:/Aplicativos/Mestre'))
        with patch.dict(os.environ,{'MEUCONTROLEPC_RAIZ_F':'C:/apps'}):
            with self.assertRaises(ValueError):politica.raiz()


if __name__=='__main__':unittest.main()
