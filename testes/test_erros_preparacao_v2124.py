"""Falhas simuladas da preparação preservam diagnóstico público sem segredos."""
from contextlib import contextmanager
import errno
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import controlar_instancia_preparacao as controle
import implantacao_assistente as implantacao
import instancia_assistente as instancia
import preparacao_autonoma as preparo


SEGREDO='token_ficticio_nao_deve_aparecer_no_estado'


class ErrosPreparacao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.origem=self.raiz/'pacote';self.origem.mkdir()
        self.codigo=self.raiz/'aplicativo'
        self.env=self.raiz/'.env';self.env.write_text('OPCAO_FICTICIA=preservada\n')
        self.dados=self.raiz/'dados'
        ctx=preparo.Caminhos(self.origem,self.codigo,self.env,self.dados,
            self.raiz/'preparacao',self.raiz/'backups_codigo',self.origem/'manifesto_instalacao.json')
        self.motor=preparo.Preparador(ctx)

    def falhar(self,erro,codigo):
        @contextmanager
        def livre(_):yield
        with patch.object(instancia,'instancia_unica',side_effect=livre), \
                patch.object(controle,'parar_assistente',side_effect=erro), \
                patch.object(self.motor,'_configuracao') as configurar, \
                patch.object(implantacao,'implantar') as implantar, \
                patch.object(preparo.subprocess,'Popen') as iniciar:
            self.motor._executar(None)
        configurar.assert_not_called();implantar.assert_not_called();iniciar.assert_not_called()
        estado=self.motor.snapshot();publico=json.dumps(estado,ensure_ascii=False)
        self.assertNotIn(SEGREDO,publico)
        self.assertNotIn(str(self.raiz),publico)
        self.assertTrue(estado['finalizado']);self.assertFalse(estado['executando'])
        self.assertFalse(estado['bot_iniciado'])
        self.assertFalse(any(i['estado'] in ('executando','verificando') for i in estado['itens']))
        etapa=next(i for i in estado['itens'] if i['id']=='parada')
        self.assertEqual(etapa['estado'],'pendente')
        self.assertIn('Código: '+codigo+'.',etapa['detalhe'])
        self.assertIn('Retomar',etapa['detalhe'])
        self.assertNotIn('encerrou sem confirmação',etapa['detalhe'])
        self.assertIn(codigo,next(p['texto'] for p in estado['pendencias'] if p['id']=='erro'))
        self.assertEqual(self.env.read_text(),'OPCAO_FICTICIA=preservada\n')

    def test_acesso_negado_tem_instrucao_de_permissoes_sem_detalhes_da_excecao(self):
        self.falhar(PermissionError(errno.EACCES,SEGREDO,str(self.env)),'acesso_negado')

    def test_arquivo_ausente_indica_conferencia_do_pacote(self):
        self.falhar(FileNotFoundError(errno.ENOENT,SEGREDO,str(self.env)),'arquivo_ausente')

    def test_falta_de_espaco_indica_unidade_da_instalacao(self):
        self.falhar(OSError(errno.ENOSPC,SEGREDO,str(self.env)),'espaco_insuficiente')

    def test_compartilhamento_windows_tem_prioridade_sobre_erro_de_permissao(self):
        for winerror in (32,33):
            erro=PermissionError(errno.EACCES,SEGREDO,str(self.env));erro.winerror=winerror
            with self.subTest(winerror=winerror):self.falhar(erro,'arquivo_em_uso')

    def test_timeout_de_processo_nao_expoe_comando_stdout_ou_stderr(self):
        erro=subprocess.TimeoutExpired(['python.exe',SEGREDO],3,output=SEGREDO,stderr=SEGREDO)
        self.falhar(erro,'prazo_esgotado')

    def test_timeout_do_sistema_tambem_tem_codigo_estatico(self):
        self.falhar(TimeoutError(errno.ETIMEDOUT,SEGREDO),'prazo_esgotado')

    def test_erro_desconhecido_nao_e_formatado_nem_tem_classe_exposta(self):
        class ErroComInformacaoPrivada(Exception):
            def __str__(self):raise AssertionError('A exceção não pode ser formatada.')
        self.falhar(ErroComInformacaoPrivada(SEGREDO),'etapa_nao_concluida')
        self.assertNotIn('ErroComInformacaoPrivada',json.dumps(self.motor.snapshot()))

    def test_erro_os_desconhecido_nao_inventa_diagnostico(self):
        self.falhar(OSError(errno.EIO,SEGREDO,str(self.env)),'etapa_nao_concluida')


if __name__=='__main__':unittest.main()
