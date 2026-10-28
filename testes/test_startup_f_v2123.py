"""Início em F com atalhos e volumes simulados; nenhuma ação Windows real."""
import errno
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import instalacao_em_f as volume
import startup_windows as inicio


class StartupEmFTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.f=self.base/'F';self.f.mkdir()
        self.c=self.base/'C';self.c.mkdir()
        self.codigo=self.f/'aplicativo';self.codigo.mkdir()
        self.python=self.codigo/'.venv'/'Scripts'/'python.exe'
        self.env=self.f/'.env';self.dados=self.f/'dados';self.dados.mkdir()
        self.atalho=self.c/'Startup'/inicio.NOME;self.atalho.parent.mkdir()
        self.legado=self.atalho.parent/inicio.LEGADOS[0]
        self.externo=self.atalho.parent/'Outro aplicativo.lnk';self.externo.write_bytes(b'nao mudar')
        for contexto in (patch.dict(os.environ,{'MEUCONTROLEPC_SOMENTE_F':'1'},clear=True),
                        patch.object(volume,'raiz',return_value=self.f),
                        patch.object(volume,'validar_caminho',side_effect=self.validar),
                        patch.object(inicio,'destino',return_value=self.atalho)):
            contexto.start();self.addCleanup(contexto.stop)

    def validar(self,p):
        caminho=Path(p)
        if not caminho.is_relative_to(self.f):raise ValueError('Exige F na fixture.')
        return caminho

    def texto(self,**extras):
        opcoes={'pasta':self.codigo,'python':self.python,'arquivo_env_externo':self.env,'dados':self.dados}
        opcoes.update(extras)
        return inicio.texto_inicio(**opcoes)

    def consolidar(self,**extras):
        return inicio.consolidar_inicio(self.codigo,self.python,
            arquivo_env_externo=self.env,dados=self.dados,confirmado=True,**extras)

    def test_script_persiste_modo_e_caminhos_f_sem_ler_configuracao(self):
        self.assertFalse(self.env.exists())
        texto=self.texto()
        self.assertIn('set "MEUCONTROLEPC_SOMENTE_F=1"',texto)
        self.assertIn('set "MEUCONTROLEPC_RAIZ_F='+str(self.f)+'"',texto)
        self.assertIn('set "PYTHONDONTWRITEBYTECODE=1"',texto)
        self.assertIn(str(self.python),texto)
        self.assertIn(str(self.env),texto)
        self.assertIn(str(self.dados),texto)
        self.assertNotIn(str(self.c),texto)
        self.assertFalse(self.env.exists())

    def test_script_recusa_codigo_python_configuracao_ou_dados_fora_f(self):
        for chave in ('pasta','python','arquivo_env_externo','dados'):
            with self.subTest(chave=chave),self.assertRaises(ValueError):
                self.texto(**{chave:self.c/'destino'})

    def test_consolidacao_transfere_entre_volumes_sem_rename_cruzado(self):
        self.legado.write_bytes(b'atalho antigo permitido')
        original_replace=os.replace
        def substituir(a,b):
            if Path(a).is_relative_to(self.c)!=Path(b).is_relative_to(self.c):
                raise OSError(errno.EXDEV,'volumes diferentes')
            return original_replace(a,b)
        with patch.object(inicio.os,'replace',side_effect=substituir):
            resultado=self.consolidar()
        self.assertTrue(resultado['backup'].is_relative_to(self.f/'preparacao'/'inicio_guardado'))
        self.assertEqual((resultado['backup']/self.legado.name).read_bytes(),b'atalho antigo permitido')
        self.assertFalse(self.legado.exists())
        self.assertEqual(self.externo.read_bytes(),b'nao mudar')
        self.assertEqual(self.atalho.read_text(),self.texto())

    def test_backup_do_script_atual_tambem_fica_em_f(self):
        anterior=(inicio.ASSINATURA+'\n@echo off\necho versao anterior\n').encode()
        self.atalho.write_bytes(anterior)
        resultado=self.consolidar()
        self.assertEqual((resultado['backup']/self.atalho.name).read_bytes(),anterior)
        self.assertEqual(self.atalho.read_text(),self.texto())
        self.assertEqual(resultado['legados_movidos'],[])

    def test_backup_explicito_fora_f_e_recusado_antes_de_mover_atalhos(self):
        self.legado.write_bytes(b'antigo')
        with self.assertRaises(ValueError):self.consolidar(diretorio_backup=self.c/'backup')
        self.assertEqual(self.legado.read_bytes(),b'antigo')
        self.assertFalse(self.atalho.exists())

    def test_falha_no_registro_restaura_atalho_entre_volumes(self):
        self.legado.write_bytes(b'antigo')
        with patch.object(inicio,'registrar_inicio',side_effect=OSError('fixture')):
            with self.assertRaises(OSError):self.consolidar()
        self.assertEqual(self.legado.read_bytes(),b'antigo')
        self.assertEqual(self.externo.read_bytes(),b'nao mudar')
        self.assertFalse(self.atalho.exists())

    def test_reversao_nao_sobrescreve_script_alterado_depois(self):
        anterior=(inicio.ASSINATURA+'\n@echo off\necho anterior\n').encode()
        posterior=(inicio.ASSINATURA+'\n@echo off\necho alteracao posterior\n').encode()
        self.atalho.write_bytes(anterior);self.legado.write_bytes(b'antigo')
        def falhar(*args,**kwargs):
            self.atalho.write_bytes(posterior)
            raise OSError('fixture')
        with patch.object(inicio,'registrar_inicio',side_effect=falhar):
            with self.assertRaises(OSError):self.consolidar()
        self.assertEqual(self.atalho.read_bytes(),posterior)
        self.assertEqual(self.legado.read_bytes(),b'antigo')
        backups=list((self.f/'preparacao'/'inicio_guardado').glob('*/'+self.atalho.name))
        self.assertEqual(len(backups),1)
        self.assertEqual(backups[0].read_bytes(),anterior)

    def test_reversao_recusa_backup_que_foi_alterado(self):
        self.legado.write_bytes(b'antigo')
        def falhar(*args,**kwargs):
            copia=next((self.f/'preparacao'/'inicio_guardado').glob('*/'+self.legado.name))
            copia.write_bytes(b'alterado por outro processo')
            raise OSError('fixture')
        with patch.object(inicio,'registrar_inicio',side_effect=falhar):
            with self.assertRaisesRegex(RuntimeError,'reversão não foi completa'):self.consolidar()
        self.assertFalse(self.legado.exists())
        copia=next((self.f/'preparacao'/'inicio_guardado').glob('*/'+self.legado.name))
        self.assertEqual(copia.read_bytes(),b'alterado por outro processo')

    def test_transferencia_preserva_destino_existente_e_origem(self):
        origem=self.c/'origem.lnk';destino=self.f/'destino.lnk'
        origem.write_bytes(b'original');destino.write_bytes(b'outro')
        with self.assertRaises(FileExistsError):inicio._transferir_verificado(origem,destino)
        self.assertEqual(origem.read_bytes(),b'original');self.assertEqual(destino.read_bytes(),b'outro')

    def test_transferencia_recusa_arquivo_acima_do_limite(self):
        origem=self.c/'origem.lnk';destino=self.f/'destino.lnk'
        origem.write_bytes(b'x'*(inicio.MAX_GERENCIADO+1))
        with self.assertRaises(RuntimeError):inicio._transferir_verificado(origem,destino)
        self.assertTrue(origem.exists());self.assertFalse(destino.exists())

    def test_mudanca_da_origem_durante_copia_impede_exclusao(self):
        origem=self.c/'origem.lnk';destino=self.f/'destino.lnk';origem.write_bytes(b'original')
        ler=Path.read_bytes;mudou=False
        def observar(p):
            nonlocal mudou
            resultado=ler(p)
            if p==destino and not mudou:
                mudou=True;origem.write_bytes(b'alteracao posterior')
            return resultado
        with patch.object(Path,'read_bytes',observar):
            with self.assertRaisesRegex(RuntimeError,'mudou durante a cópia'):
                inicio._transferir_verificado(origem,destino)
        self.assertEqual(origem.read_bytes(),b'alteracao posterior')
        self.assertFalse(destino.exists())

    def test_repetir_consolidacao_identica_nao_cria_outro_backup(self):
        self.consolidar()
        self.assertFalse((self.f/'preparacao'/'inicio_guardado').exists())
        self.consolidar()
        self.assertFalse((self.f/'preparacao'/'inicio_guardado').exists())


if __name__=='__main__':unittest.main()
