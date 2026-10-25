"""Preparação automática com contas/processos simulados e HTTP só em loopback."""
from contextlib import contextmanager
import http.client
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import preparacao_autonoma as preparo
import instancia_assistente as instancia
import controlar_instancia_preparacao as controle
import implantacao_assistente as implantacao
import redirecionar_assistente as redirecionar

TOKEN='123456789:token_ficticio_de_teste_123456789'
CHAVE='credencial_ficticia_para_teste'


class BasePreparacao(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.raiz=Path(self.tmp.name).resolve()
        self.origem=self.raiz/'pacote';self.origem.mkdir()
        self.codigo=self.raiz/'codigo';self.codigo.mkdir()
        self.env=self.raiz/'privado'/'.env';self.dados=self.raiz/'privado'/'dados'
        self.ctx=preparo.caminhos(self.origem,self.codigo,self.env,self.dados)
        self.motor=preparo.Preparador(self.ctx)
        p=patch.dict(os.environ,{});p.start();self.addCleanup(p.stop)

    def escrever_env(self,texto):
        self.env.parent.mkdir(parents=True,exist_ok=True);self.env.write_text(texto,encoding='utf-8')


class ConfiguracaoAutomatica(BasePreparacao):
    def test_seletor_de_dados_externo_e_respeitado(self):
        escolhido=self.raiz/'outros_dados'
        with patch.dict(os.environ,{'MEUCONTROLEPC_DADOS':str(escolhido)}):
            ctx=preparo.caminhos(self.origem,self.codigo,self.env)
        self.assertEqual(ctx.dados,escolhido)
        with patch.dict(os.environ,{'MEUCONTROLEPC_DADOS':'relativo'}),self.assertRaises(ValueError):
            preparo.caminhos(self.origem,self.codigo,self.env)

    def test_caminhos_privados_dentro_do_codigo_sao_recusados(self):
        for env,dados in ((self.codigo/'.env',self.dados),(self.env,self.codigo/'dados')):
            with self.subTest(env=env,dados=dados),self.assertRaises(ValueError):
                preparo.caminhos(self.origem,self.codigo,env,dados)

    def test_dados_legados_nao_sao_substituidos_por_pasta_vazia(self):
        (self.codigo/'dados').mkdir()
        with self.assertRaises(ValueError):preparo.caminhos(self.origem,self.codigo,self.env,self.dados)
        self.dados.mkdir(parents=True)
        self.assertEqual(preparo.caminhos(self.origem,self.codigo,self.env,self.dados).dados,self.dados)

    def test_reutiliza_contas_porta_e_opcoes_sem_expor_segredos(self):
        texto=('# preservar\nTELEGRAM_TOKEN='+TOKEN+'\nTELEGRAM_ALLOWED_USER_IDS=12345\n'
            'GEMINI_API_KEY='+CHAVE+'\nGOOGLE_API_KEY=alias_ficticio\nNINE_ROUTER_API_KEY=router_ficticio\n'
            'PAINEL_PORTA=8769\nOLLAMA_NUVEM_HABILITADA=0\nDESCONHECIDA=preservada\n')
        self.escrever_env(texto)
        valores=self.motor._configuracao();self.motor._configuracao()
        self.assertEqual(valores['TELEGRAM_TOKEN'],TOKEN)
        self.assertEqual(valores['GEMINI_API_KEY'],CHAVE)
        self.assertEqual(valores['NINE_ROUTER_API_KEY'],'router_ficticio')
        self.assertNotIn('DESCONHECIDA',valores)
        self.assertEqual(os.environ['OLLAMA_NUVEM_HABILITADA'],'0')
        self.assertEqual(self.motor.snapshot()['painel_url'],'http://127.0.0.1:8769')
        self.assertEqual(self.env.read_text(encoding='utf-8'),texto)
        backups=list((self.ctx.backups/'configuracao').glob('*.bak'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(encoding='utf-8'),texto)
        publico=json.dumps(self.motor.snapshot())
        self.assertNotIn(CHAVE,publico);self.assertNotIn(TOKEN,publico)

    def test_porta_invalida_usa_valor_local_seguro(self):
        for porta in ('x','0','65536'):
            with self.subTest(porta=porta):
                self.escrever_env('PAINEL_PORTA='+porta+'\n');self.motor._configuracao()
                self.assertEqual(self.motor.snapshot()['painel_url'],'http://127.0.0.1:8765')

    def test_salvar_chave_faz_backup_e_preserva_demais_opcoes(self):
        original='OUTRA_OPCAO=valor\nTELEGRAM_TOKEN='+TOKEN+'\n'
        self.escrever_env(original)
        resposta=self.motor.salvar_credencial('GEMINI_API_KEY',CHAVE)
        self.assertTrue(resposta['ok']);self.assertNotIn(CHAVE,json.dumps(resposta))
        texto=self.env.read_text(encoding='utf-8')
        self.assertIn(original,texto);self.assertIn('GEMINI_API_KEY='+CHAVE,texto)
        backups=list((self.ctx.backups/'configuracao').glob('*.bak'))
        self.assertEqual(len(backups),1);self.assertEqual(backups[0].read_text(encoding='utf-8'),original)
        self.assertNotIn(CHAVE,json.dumps(self.motor.snapshot()))

    def test_chave_invalida_ou_worker_ativo_nao_altera_env(self):
        self.escrever_env('PRESERVAR=sim\n');original=self.env.read_bytes()
        casos=[('DESCONHECIDA',CHAVE),([],CHAVE),('GEMINI_API_KEY',None),('GEMINI_API_KEY','x\ny'),
            ('GEMINI_API_KEY','a b'),('GEMINI_API_KEY','"segredo"'),('TELEGRAM_TOKEN','invalido'),
            ('TELEGRAM_ALLOWED_USER_IDS','id-invalido')]
        for nome,valor in casos:
            with self.subTest(nome=nome,valor=valor),self.assertRaises(ValueError):
                self.motor.salvar_credencial(nome,valor)
        self.motor.estado['executando']=True
        with self.assertRaises(RuntimeError):self.motor.salvar_credencial('GEMINI_API_KEY',CHAVE)
        self.assertEqual(self.env.read_bytes(),original)

    def test_link_substituido_apos_planejamento_nao_e_gravado(self):
        self.escrever_env('PRESERVAR=sim\n');outro=self.raiz/'fora.env';outro.write_text('intacto',encoding='utf-8')
        self.env.unlink()
        try:self.env.symlink_to(outro)
        except OSError:self.skipTest('Criação de symlink não disponível neste Windows.')
        with self.assertRaises(ValueError):self.motor.salvar_credencial('GEMINI_API_KEY',CHAVE)
        self.assertEqual(outro.read_text(encoding='utf-8'),'intacto')

    def test_ambiente_filho_nao_herda_segredos_proxy_ou_injecoes(self):
        with patch.dict(os.environ,{'GEMINI_API_KEY':CHAVE,'HTTP_PROXY':'http://ficticio',
                'PYTHONPATH':'injetado','NODE_OPTIONS':'injetado','PATH':'permitido'}):
            ambiente=preparo._ambiente(self.ctx)
        for nome in ('GEMINI_API_KEY','HTTP_PROXY','PYTHONPATH','NODE_OPTIONS'):self.assertNotIn(nome,ambiente)
        self.assertEqual(ambiente['PATH'],'permitido');self.assertEqual(ambiente['MEUCONTROLEPC_ENV'],str(self.env))

    def test_snapshot_e_copia_independente(self):
        self.motor.item('a','Etapa','pronto','Seguro');s=self.motor.snapshot();s['itens'][0]['detalhe']=CHAVE
        self.assertNotIn(CHAVE,json.dumps(self.motor.snapshot()))


class MetadadosConta(BasePreparacao):
    def resposta(self,conteudo):
        resposta=Mock();resposta.__enter__=Mock(return_value=resposta);resposta.__exit__=Mock(return_value=False)
        resposta.read.return_value=conteudo
        return resposta

    def test_uma_leitura_telegram_sem_geracao_ou_retentativa(self):
        opener=Mock();opener.open.return_value=self.resposta(b'{"ok":true,"result":{"is_bot":true}}')
        with patch.object(preparo.urllib.request,'build_opener',return_value=opener):
            resultado=preparo._verificar_conta('telegram',TOKEN)
        self.assertEqual(resultado,{'ok':True,'codigo':200});opener.open.assert_called_once()
        req=opener.open.call_args.args[0];self.assertTrue(req.full_url.endswith('/getMe'))
        self.assertEqual(opener.open.call_args.kwargs,{'timeout':7});self.assertNotIn(TOKEN,json.dumps(resultado))

    def test_gemini_usa_header_na_rota_fixa_sem_chave_na_url(self):
        opener=Mock();opener.open.return_value=self.resposta(b'{"models":[]}')
        with patch.object(preparo.urllib.request,'build_opener',return_value=opener):
            resultado=preparo._verificar_conta('gemini',CHAVE)
        self.assertTrue(resultado['ok']);req=opener.open.call_args.args[0]
        self.assertNotIn(CHAVE,req.full_url);self.assertEqual(req.get_header('X-goog-api-key'),CHAVE)
        self.assertNotIn(CHAVE,json.dumps(resultado))

    def test_erros_respostas_grandes_e_json_inesperado_nao_expoem_corpo(self):
        for resposta in (b'x'*100001,b'[]',b'{"erro":"'+CHAVE.encode()+b'"}',b'invalido'):
            opener=Mock();opener.open.return_value=self.resposta(resposta)
            with self.subTest(tamanho=len(resposta)),patch.object(preparo.urllib.request,'build_opener',return_value=opener):
                resultado=preparo._verificar_conta('gemini',CHAVE)
            self.assertFalse(resultado['ok']);self.assertNotIn(CHAVE,json.dumps(resultado));opener.open.assert_called_once()

    def test_http_error_so_retorna_codigo_e_fecha_recurso(self):
        for codigo in (401,403,404,429,503):
            corpo=io.BytesIO(CHAVE.encode());erro=urllib.error.HTTPError('https://ficticio',codigo,CHAVE,{},corpo)
            opener=Mock();opener.open.side_effect=erro
            with self.subTest(codigo=codigo),patch.object(preparo.urllib.request,'build_opener',return_value=opener):
                resultado=preparo._verificar_conta('gemini',CHAVE)
            self.assertEqual(resultado,{'ok':False,'codigo':codigo});self.assertTrue(corpo.closed)
            self.assertNotIn(CHAVE,preparo._falha_conta(codigo));opener.open.assert_called_once()

    def test_conta_invalida_nao_abre_rede_e_redirecionamento_nao_e_seguido(self):
        with patch.object(preparo.urllib.request,'build_opener') as abrir:
            self.assertFalse(preparo._verificar_conta('telegram','invalido')['ok'])
            self.assertFalse(preparo._verificar_conta('outro',CHAVE)['ok'])
        abrir.assert_not_called();self.assertIsNone(preparo._SemRedirecionamento().redirect_request(None,None,None,None,None,None))

    def test_telegram_sem_proprietario_permanece_pendente(self):
        with patch.object(preparo,'_verificar_conta') as api,patch('ponte_preparacao_windows.detectar_robotask',return_value={}):
            self.assertFalse(self.motor._contas({'TELEGRAM_TOKEN':TOKEN,'TELEGRAM_ALLOWED_USER_IDS':''}))
        api.assert_not_called();self.assertEqual(self.motor.snapshot()['itens'][0]['estado'],'pendente')


class OrquestracaoAutomatica(BasePreparacao):
    def test_componentes_saudaveis_nao_reinstalam_bibliotecas_ou_pesos(self):
        with patch.object(preparo,'_dependencias',return_value=True),patch.object(preparo,'_filho',return_value=SimpleNamespace(returncode=0)) as filho,patch('preparar_inicio_automatico.preparar_componentes') as instalar:
            self.motor._componentes()
        instalar.assert_not_called();self.assertEqual(filho.call_count,2)
        self.assertEqual(self.motor.snapshot()['itens'][-1]['estado'],'pronto')

    def test_instancia_sem_identidade_confirmada_impede_mutacoes(self):
        @contextmanager
        def trava(_):yield
        with patch.object(instancia,'instancia_unica',side_effect=trava),patch.object(controle,'parar_assistente',return_value={'livre':False,'mensagem':'Identidade não confirmada.'}),patch.object(self.motor,'_configuracao') as configurar,patch.object(implantacao,'implantar') as copiar,patch.object(preparo.subprocess,'Popen') as iniciar:
            self.motor._executar(None)
        configurar.assert_not_called();copiar.assert_not_called();iniciar.assert_not_called()
        self.assertTrue(self.motor.snapshot()['finalizado']);self.assertFalse(self.motor.snapshot()['bot_iniciado'])

    def test_ordem_parada_trava_implantacao_e_liberacao_antes_do_bot(self):
        eventos=[];travado=[False];self.escrever_env('PAINEL_PORTA=8765\n')
        @contextmanager
        def trava(_):
            eventos.append('travar');travado[0]=True
            try:yield
            finally:travado[0]=False;eventos.append('liberar')
        def parar(*args,**kw):eventos.append('parar');self.assertTrue(kw['autorizado']);return {'livre':True}
        def copiar(*args,**kw):
            eventos.append('implantar');self.assertTrue(travado[0]);return {'arquivos_verificados':3}
        def iniciar(*args,**kw):eventos.append('iniciar');self.assertFalse(travado[0]);self.assertFalse(kw['shell'])
        # Mesma pasta evita mock de manifesto para esta prova de ordem.
        self.motor.ctx=preparo.Caminhos(self.codigo,self.codigo,self.env,self.dados,self.ctx.preparacao,self.ctx.backups,self.ctx.manifesto)
        with patch.object(instancia,'instancia_unica',side_effect=trava),patch.object(controle,'parar_assistente',side_effect=parar),patch.object(implantacao,'implantar',side_effect=copiar),patch.object(self.motor,'_configuracao',return_value={}),patch.object(self.motor,'_componentes'),patch.object(self.motor,'_servicos'),patch.object(self.motor,'_gateway'),patch.object(self.motor,'_contas',return_value=False),patch('startup_windows.consolidar_inicio'),patch.object(redirecionar,'plano_execucao',return_value={'comando':['python','ficticio'],'cwd':str(self.codigo),'ambiente':{}}) as plano,patch.object(preparo.subprocess,'Popen',side_effect=iniciar):
            self.motor._executar(None)
        self.assertLess(eventos.index('parar'),eventos.index('implantar'))
        self.assertEqual(eventos[-2:],['liberar','iniciar']);self.assertEqual(plano.call_args.kwargs['modo'],'painel')
        self.assertTrue(self.motor.snapshot()['bot_iniciado'])

    def test_falha_interna_nao_revela_segredo_nem_inicia_bot(self):
        @contextmanager
        def trava(_):yield
        with patch.object(instancia,'instancia_unica',side_effect=trava),patch.object(controle,'parar_assistente',return_value={'livre':True}),patch.object(self.motor,'_configuracao',side_effect=RuntimeError(CHAVE)),patch.object(preparo.subprocess,'Popen') as iniciar:
            self.motor._executar(None)
        iniciar.assert_not_called();estado=self.motor.snapshot();self.assertTrue(estado['finalizado'])
        self.assertNotIn(CHAVE,json.dumps(estado));self.assertEqual(estado['pendencias'][-1]['tipo'],'retomar')

    def test_inicio_simultaneo_nao_cria_segundo_worker(self):
        entrada=threading.Event();sair=threading.Event()
        def executar(_):
            entrada.set();sair.wait(3)
            with self.motor.lock:self.motor.estado['executando']=False
        with patch.object(self.motor,'_executar',side_effect=executar):
            self.assertTrue(self.motor.iniciar());self.assertTrue(entrada.wait(1))
            self.assertFalse(self.motor.iniciar());sair.set();self.motor.worker.join(3)

    def test_versao_preparada_em_execucao_nao_para_ou_duplica_bot(self):
        self.escrever_env('PAINEL_PORTA=8765\n')
        self.motor.ctx=preparo.Caminhos(self.codigo,self.codigo,self.env,self.dados,self.ctx.preparacao,self.ctx.backups,self.ctx.manifesto)
        preparo._json_gravar(self.ctx.preparacao/'ultima.json',{'versao':preparo.VERSAO,'bot_iniciado':True,'codigo':str(self.codigo),'config_mtime':self.env.stat().st_mtime_ns,'painel_url':'http://127.0.0.1:8765'})
        @contextmanager
        def trava(_):raise instancia.InstanciaAtiva('ocupada');yield
        with patch.object(instancia,'instancia_unica',side_effect=trava),patch.object(controle,'parar_assistente') as parar,patch.object(preparo.subprocess,'Popen') as iniciar:
            self.motor._executar(None)
        parar.assert_not_called();iniciar.assert_not_called();self.assertTrue(self.motor.snapshot()['bot_iniciado'])


class InterfaceLocal(BasePreparacao):
    def setUp(self):
        super().setUp();self.servidor=preparo.Interface(self.motor)
        self.thread=threading.Thread(target=self.servidor.serve_forever,kwargs={'poll_interval':0.01},daemon=True);self.thread.start()
        self.addCleanup(self.fechar)

    def fechar(self):
        self.servidor.shutdown();self.servidor.server_close();self.thread.join(2)

    def pedido(self,metodo='POST',corpo=None,headers=None,path='/api/acao'):
        dados=json.dumps(corpo).encode() if isinstance(corpo,(dict,list)) else corpo
        cabecalhos=[('Host','127.0.0.1:'+str(self.servidor.server_port)),('X-Preparacao-Token',self.servidor.token),
            ('Origin','http://127.0.0.1:'+str(self.servidor.server_port)),('Content-Type','application/json')]
        if dados is not None:cabecalhos.append(('Content-Length',str(len(dados))))
        if headers is not None:cabecalhos=headers
        conexao=http.client.HTTPConnection('127.0.0.1',self.servidor.server_port,timeout=3)
        try:
            conexao.putrequest(metodo,path,skip_host=True,skip_accept_encoding=True)
            for k,v in cabecalhos:conexao.putheader(k,v)
            conexao.endheaders(dados);r=conexao.getresponse();bruto=r.read()
            return r.status,dict(r.getheaders()),bruto
        finally:conexao.close()

    def validos(self,corpo):
        return [('Host','127.0.0.1:'+str(self.servidor.server_port)),('X-Preparacao-Token',self.servidor.token),
            ('Origin','http://127.0.0.1:'+str(self.servidor.server_port)),('Content-Type','application/json'),('Content-Length',str(len(corpo)))]

    def test_estado_e_html_nunca_exibem_credenciais(self):
        self.escrever_env('GEMINI_API_KEY='+CHAVE+'\nTELEGRAM_TOKEN='+TOKEN+'\n');self.motor._configuracao()
        for path in ('/api/estado','/'):
            status,headers,bruto=self.pedido('GET',path=path)
            self.assertEqual(status,200);self.assertNotIn(CHAVE,bruto.decode());self.assertNotIn(TOKEN,bruto.decode())
            self.assertEqual(headers['Cache-Control'],'no-store');self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])

    def test_acao_autorizada_salva_so_localmente_sem_eco(self):
        status,_,bruto=self.pedido(corpo={'tipo':'chave','nome':'GEMINI_API_KEY','valor':CHAVE})
        self.assertEqual(status,200);self.assertNotIn(CHAVE,bruto.decode());self.assertIn(CHAVE,self.env.read_text(encoding='utf-8'))

    def test_host_token_origin_ausentes_duplicados_ou_externos_impedem_gravacao(self):
        corpo=json.dumps({'tipo':'chave','nome':'GEMINI_API_KEY','valor':CHAVE}).encode();base=self.validos(corpo)
        casos=[[p for p in base if p[0]!=nome] for nome in ('Host','X-Preparacao-Token','Origin')]
        casos += [base+[base[i]] for i in (0,1,2)]
        casos += [[(k,'http://externo.invalid' if k=='Origin' else v) for k,v in base],
            [(k,'externo.invalid' if k=='Host' else v) for k,v in base],
            [(k,'invalido' if k=='X-Preparacao-Token' else v) for k,v in base]]
        with patch.object(self.motor,'salvar_credencial') as salvar:
            for h in casos:
                with self.subTest(headers=[k for k,_ in h]):self.assertEqual(self.pedido(corpo=corpo,headers=h)[0],403)
        salvar.assert_not_called();self.assertFalse(self.env.exists())

    def test_json_duplicado_nan_acoes_extras_e_campo_injetado_sao_recusados(self):
        corpos=[b'{"tipo":"retomar","tipo":"chave"}',b'{"tipo":"retomar","modelo":NaN}',
            b'[]',b'{"tipo":"retomar","executar":"codigo"}',b'{"tipo":"shell","comando":"ficticio"}',
            b'{"tipo":"chave","nome":[],"valor":"ficticio"}']
        with patch.object(self.motor,'iniciar') as iniciar:
            for corpo in corpos:
                with self.subTest(corpo=corpo):self.assertEqual(self.pedido(corpo=corpo)[0],400)
        iniciar.assert_not_called();self.assertFalse(self.env.exists())

    def test_tamanho_tipo_e_transferencia_invalidos_sao_recusados(self):
        corpo=b'{"tipo":"retomar"}';base=self.validos(corpo)
        casos=[[p for p in base if p[0]!='Content-Length'],base+[('Content-Length',str(len(corpo)))],
            [(k,str(preparo.MAX_CORPO+1) if k=='Content-Length' else v) for k,v in base],
            [(k,'text/plain' if k=='Content-Type' else v) for k,v in base],base+[('Transfer-Encoding','chunked')]]
        with patch.object(self.motor,'iniciar') as iniciar:
            for h in casos:
                with self.subTest(headers=h):self.assertEqual(self.pedido(corpo=corpo,headers=h)[0],400)
        iniciar.assert_not_called()

    def test_retomar_valida_modelo_e_nao_aceita_credencial_como_modelo(self):
        with patch.object(self.motor,'iniciar',return_value=True) as iniciar:
            self.assertEqual(self.pedido(corpo={'tipo':'retomar','modelo':'provedor/modelo-mini'})[0],200)
            iniciar.assert_called_once_with('provedor/modelo-mini')
            self.assertEqual(self.pedido(corpo={'tipo':'retomar','modelo':'sk-'+'A'*35})[0],400)
        self.assertEqual(iniciar.call_count,1)

    def test_excecao_nao_expoe_chave_em_resposta(self):
        with patch.object(self.motor,'salvar_credencial',side_effect=RuntimeError(CHAVE)):
            status,_,bruto=self.pedido(corpo={'tipo':'chave','nome':'GEMINI_API_KEY','valor':CHAVE})
        self.assertEqual(status,400);self.assertNotIn(CHAVE,bruto.decode())


if __name__=='__main__':unittest.main()
