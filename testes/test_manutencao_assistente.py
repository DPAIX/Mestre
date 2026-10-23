"""Manutenção somente em fixtures; não instala pacotes nem acessa o Windows."""
from __future__ import annotations

from contextlib import contextmanager
import io
from pathlib import Path
import stat
from types import SimpleNamespace
import sys
import tempfile
import unittest
from unittest.mock import MagicMock,patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import manutencao_assistente as manutencao
import preparar_inicio_automatico as preparacao


class LimpezaGeradosTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve();self.codigo=self.raiz/'codigo';self.codigo.mkdir()
        for nome in preparacao.redirecionar.FONTES_NECESSARIAS:
            (self.codigo/nome).write_bytes(b'fixture-fonte')

    def arquivo(self,nome,conteudo=b'fixture'):
        caminho=self.codigo/nome;caminho.parent.mkdir(parents=True,exist_ok=True)
        caminho.write_bytes(conteudo)
        return caminho

    def link(self,origem,destino,*,diretorio=False):
        try:origem.symlink_to(destino,target_is_directory=diretorio)
        except (OSError,NotImplementedError):self.skipTest('Links não disponíveis neste ambiente.')

    def test_remove_somente_cache_gerado_e_bytecode_com_fonte(self):
        removidos=[self.arquivo('__pycache__/modulo.cpython-314.pyc',b'123'),
                   self.arquivo('__pycache__/antigo.cpython-311.opt-1.pyc',b'12345'),
                   self.arquivo('testes/__pycache__/test_fixture.cpython-312.pyc',b'12'),
                   self.arquivo('modulo.pyc',b'1234'),self.arquivo('testes/test_fixture.pyo',b'1')]
        preservados=[self.arquivo('modulo.py'),self.arquivo('testes/test_fixture.py'),
                     self.arquivo('orfao.pyc'),self.arquivo('__pycache__/anotacao.txt'),
                     self.arquivo('dados/__pycache__/pessoal.cpython-314.pyc'),
                     self.arquivo('.venv/__pycache__/biblioteca.cpython-314.pyc'),
                     self.arquivo('modelos_voz/base/model.bin'),self.arquivo('backups/backup.zip'),
                     self.arquivo('README.md'),self.arquivo('.env'),self.arquivo('instalador.zip')]
        antes={p:p.read_bytes() for p in preservados}
        resultado=manutencao.limpar_gerados(self.codigo)
        self.assertEqual(resultado['arquivos_removidos'],len(removidos))
        self.assertEqual(resultado['bytes_liberados'],15)
        self.assertTrue(all(not p.exists() for p in removidos))
        self.assertEqual({p:p.read_bytes() for p in preservados},antes)
        self.assertTrue((self.codigo/'__pycache__').exists())
        self.assertFalse((self.codigo/'testes'/'__pycache__').exists())

    def test_repetir_limpeza_e_idempotente_e_nao_cria_arquivos(self):
        self.arquivo('__pycache__/modulo.cpython-314.pyc')
        manutencao.limpar_gerados(self.codigo)
        resultado=manutencao.limpar_gerados(self.codigo)
        self.assertEqual(resultado['arquivos_removidos'],0)
        self.assertEqual(resultado['diretorios_removidos'],0)
        self.assertEqual(sorted(p.name for p in self.codigo.iterdir()),sorted(preparacao.redirecionar.FONTES_NECESSARIAS))

    def test_nao_segue_link_de_cache_para_fora(self):
        externo=self.raiz/'externo';externo.mkdir()
        alvo=externo/'modulo.cpython-314.pyc';alvo.write_bytes(b'preservar')
        cache=self.codigo/'__pycache__';self.link(cache,externo,diretorio=True)
        resultado=manutencao.limpar_gerados(self.codigo)
        self.assertEqual(resultado['arquivos_removidos'],0)
        self.assertEqual(alvo.read_bytes(),b'preservar')
        self.assertTrue(cache.is_symlink())

    def test_nao_remove_link_de_arquivo_ou_percorre_testes_redirecionados(self):
        externo=self.raiz/'externo';externo.mkdir()
        alvo=externo/'modulo.cpython-314.pyc';alvo.write_bytes(b'preservar')
        cache=self.codigo/'__pycache__';cache.mkdir()
        link=cache/alvo.name;self.link(link,alvo)
        self.link(self.codigo/'testes',externo,diretorio=True)
        resultado=manutencao.limpar_gerados(self.codigo)
        self.assertEqual(resultado['arquivos_removidos'],0)
        self.assertEqual(alvo.read_bytes(),b'preservar')
        self.assertTrue(link.is_symlink())

    def test_junction_reparse_point_e_recusado(self):
        caminho=MagicMock()
        caminho.lstat.return_value=SimpleNamespace(st_mode=stat.S_IFDIR,st_file_attributes=1024)
        with patch.object(manutencao.stat,'FILE_ATTRIBUTE_REPARSE_POINT',1024,create=True):
            self.assertTrue(manutencao._redirecionado(caminho))

    def test_falha_de_acesso_e_registrada_sem_exclusao_forcada(self):
        caminho=self.arquivo('__pycache__/modulo.cpython-314.pyc')
        with patch.object(Path,'unlink',side_effect=PermissionError('fixture')):
            resultado=manutencao.limpar_gerados(self.codigo)
        self.assertTrue(caminho.exists())
        self.assertEqual(resultado['arquivos_removidos'],0)
        self.assertEqual(resultado['ignorados'],1)

    def test_diretorio_relativo_e_link_raiz_sao_recusados(self):
        with self.assertRaises(ValueError):manutencao.limpar_gerados(Path('codigo'))
        link=self.raiz/'codigo-link';self.link(link,self.codigo,diretorio=True)
        with self.assertRaises(ValueError):manutencao.limpar_gerados(link)

    def test_lista_limitada_nao_remove_arquivos_alem_do_orcamento(self):
        a=self.arquivo('__pycache__/a.cpython-314.pyc')
        b=self.arquivo('__pycache__/b.cpython-314.pyc')
        with patch.object(manutencao,'MAX_ENTRADAS',1):
            resultado=manutencao.limpar_gerados(self.codigo)
        self.assertTrue(resultado['limite_atingido'])
        self.assertEqual(resultado['arquivos_removidos'],1)
        self.assertEqual(sum(p.exists() for p in (a,b)),1)

    def test_nao_limpa_pasta_generica_ou_fontes_redirecionadas(self):
        outra=self.raiz/'outra';cache=outra/'__pycache__';cache.mkdir(parents=True)
        arquivo=cache/'modulo.cpython-314.pyc';arquivo.write_bytes(b'preservar')
        with self.assertRaisesRegex(ValueError,'raiz completa'):
            manutencao.limpar_gerados(outra)
        self.assertEqual(arquivo.read_bytes(),b'preservar')


class ManutencaoFluxoTeste(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.plano={'codigo':self.raiz/'codigo','dados':self.raiz/'externo'/'dados',
                    'python':self.raiz/'python.exe'}
        self.plano['codigo'].mkdir()
        self.eventos=[]
        self.ativo=False
        @contextmanager
        def bloquear(dados):
            self.assertEqual(dados,self.plano['dados'])
            self.assertFalse(self.ativo);self.ativo=True;self.eventos.append('trava')
            try:yield
            finally:self.ativo=False;self.eventos.append('liberar')
        p=patch.object(manutencao,'instancia_unica',side_effect=bloquear)
        self.bloquear=p.start();self.addCleanup(p.stop)
        p=patch.object(preparacao,'planejar_preparacao',return_value=self.plano)
        self.planejar=p.start();self.addCleanup(p.stop)
        def componentes(plano,**opcoes):
            self.assertTrue(self.ativo);self.eventos.append('componentes');return plano
        p=patch.object(preparacao,'preparar_componentes',side_effect=componentes)
        self.componentes=p.start();self.addCleanup(p.stop)
        def limpar(codigo):
            self.assertTrue(self.ativo);self.eventos.append('limpeza')
            return {'arquivos_removidos':1,'bytes_liberados':12,'ignorados':0,'limite_atingido':False}
        p=patch.object(manutencao,'limpar_gerados',side_effect=limpar)
        self.limpar=p.start();self.addCleanup(p.stop)
        def iniciar(plano):
            self.assertFalse(self.ativo);self.eventos.append('iniciar');return 'fixture-processo'
        p=patch.object(preparacao,'iniciar_assistente',side_effect=iniciar)
        self.iniciar=p.start();self.addCleanup(p.stop)
        p=patch.object(preparacao.startup,'registrar_inicio',side_effect=AssertionError('Não alterar Startup'))
        p.start();self.addCleanup(p.stop)
        p=patch.object(preparacao.startup,'conferir_destino',side_effect=AssertionError('Não consultar Startup'))
        p.start();self.addCleanup(p.stop)
        p=patch('sys.stdout',new_callable=io.StringIO)
        p.start();self.addCleanup(p.stop)

    def test_manutencao_completa_instala_integracoes_limpa_e_inicia_sem_startup(self):
        resultado=manutencao.manter(self.plano['codigo'],'fixture-env')
        self.planejar.assert_called_once_with(self.plano['codigo'],'fixture-env',None,None,incluir_google=True)
        self.componentes.assert_called_once_with(self.plano,python_explicito=False,incluir_google=True)
        self.assertEqual(self.eventos,['trava','componentes','limpeza','liberar','iniciar'])
        self.assertEqual(resultado['processo'],'fixture-processo')

    def test_instancia_ativa_impede_pip_limpeza_e_novo_inicio(self):
        self.bloquear.side_effect=manutencao.InstanciaAtiva('fixture')
        with self.assertRaisesRegex(RuntimeError,'Encerre a janela'):
            manutencao.manter()
        self.componentes.assert_not_called();self.limpar.assert_not_called();self.iniciar.assert_not_called()

    def test_falha_dependencia_preserva_arquivos_e_nao_inicia(self):
        self.componentes.side_effect=RuntimeError('Biblioteca indisponível')
        with self.assertRaises(RuntimeError):manutencao.manter()
        self.limpar.assert_not_called();self.iniciar.assert_not_called()
        self.assertEqual(self.eventos,['trava','liberar'])

    def test_sem_iniciar_preserva_escolha_e_python_explicito(self):
        resultado=manutencao.manter(python='fixture-python',iniciar=False)
        self.componentes.assert_called_once_with(self.plano,python_explicito=True,incluir_google=True)
        self.assertIsNone(resultado['processo']);self.iniciar.assert_not_called()


class DependenciasCompletasTeste(unittest.TestCase):
    def test_componentes_incluem_google_pipcheck_e_preparacao_idempotente_da_voz(self):
        with tempfile.TemporaryDirectory() as tmp:
            codigo=Path(tmp).resolve();python=codigo/'.venv'/'Scripts'/'python.exe'
            python.parent.mkdir(parents=True);python.write_bytes(b'fixture')
            plano={'codigo':codigo,'arquivo_env':codigo.parent/'externo'/'.env',
                   'dados':codigo.parent/'externo'/'dados','python':python,
                   'cwd':str(codigo),'ambiente':{'PATH':'fixture','OPENAI_API_KEY':'fixture-segredo'}}
            with patch.object(preparacao,'_executar',return_value=None) as executar,patch('sys.stdout',new_callable=io.StringIO):
                self.assertIs(preparacao.preparar_componentes(plano,incluir_google=True),plano)
        comandos=[c.args[0] for c in executar.call_args_list]
        self.assertEqual(len(comandos),4)
        self.assertIn(str(codigo/'requirements-google.txt'),comandos[1])
        self.assertEqual(comandos[2][-2:],['pip','check'])
        self.assertIn('preparar_modelo()',comandos[3][-1])
        self.assertFalse(any('--upgrade' in c for c in comandos))
        self.assertTrue(all('fixture-segredo' not in repr(c.args[2]) for c in executar.call_args_list))


if __name__=='__main__':unittest.main()
