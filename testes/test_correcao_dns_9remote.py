"""Manutenção dos bundles com fontes fictícias; sem produtos ou rede reais."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import correcao_dns_9remote as app


def sha(valor):
    return hashlib.sha256(valor).hexdigest()


class CorrecaoDNS9Remote(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.raiz = Path(self.tmp.name)
        self.local = self.raiz / 'local'
        self.pacote = self.local / 'MeuControlePC' / 'integracoes' / '9remote' / 'node_modules' / '9remote'
        (self.pacote / 'dist').mkdir(parents=True)
        (self.pacote / 'package.json').write_text(json.dumps({'name': '9remote', 'version': '3.0.43'}))
        self.originais = {}
        self.corrigidos = {}
        self.especificacoes = {}
        for nome in ('cli.cjs', 'server.cjs'):
            antes = ('override_' + nome + '();').encode()
            depois = ('native_' + nome + '();').encode()
            original = b'/* fixture publica */' + antes + b'/* fim */'
            corrigido = original.replace(antes, depois)
            self.originais[nome] = original
            self.corrigidos[nome] = corrigido
            self.especificacoes[nome] = {'original': sha(original), 'corrigido': sha(corrigido),
                                        'antes': antes, 'depois': depois}
            (self.pacote / 'dist' / nome).write_bytes(original)
        for objeto in (patch.dict(os.environ, {'LOCALAPPDATA': str(self.local)}, clear=True),
                       patch.object(app, 'ESPECIFICACOES', self.especificacoes)):
            objeto.start()
            self.addCleanup(objeto.stop)

    def arquivo(self, nome):
        return self.pacote / 'dist' / nome

    def copia(self, nome):
        return self.pacote / app.BACKUP / (nome + '.original')

    def conferir(self, conteudos):
        for nome, conteudo in conteudos.items():
            self.assertEqual(self.arquivo(nome).read_bytes(), conteudo)

    def symlink(self, origem, alvo, *, diretorio=False):
        try:
            origem.symlink_to(alvo, target_is_directory=diretorio)
        except (OSError, NotImplementedError):
            self.skipTest('Criação de symlinks indisponível nesta plataforma.')

    def test_planejar_confere_todos_sem_escrever_ou_criar_backup(self):
        with patch.object(app, '_gravar_atomico', side_effect=AssertionError('Sem escritas.')):
            resultado = app.planejar_correcao(self.pacote)
        self.assertEqual(resultado['estado'], 'original')
        self.assertEqual(resultado['arquivos_pendentes'], 2)
        self.assertFalse(resultado['backup_disponivel'])
        self.assertFalse((self.pacote / app.BACKUP).exists())
        self.conferir(self.originais)

    def test_aplicacao_backup_idempotencia_reversao_reaplicacao(self):
        privado = self.pacote / '.env'
        privado.write_text('NAO_LER_FIXTURE')
        primeira = app.aplicar_correcao(self.pacote)
        self.assertEqual(primeira['arquivos_alterados'], 2)
        self.assertTrue(primeira['backup_disponivel'])
        self.conferir(self.corrigidos)
        for nome, original in self.originais.items():
            self.assertEqual(self.copia(nome).read_bytes(), original)
        with patch.object(app, '_gravar_atomico', side_effect=AssertionError('Já aplicado.')):
            self.assertEqual(app.aplicar_correcao(self.pacote)['arquivos_alterados'], 0)
        self.assertEqual(app.planejar_correcao(self.pacote)['estado'], 'aplicada')
        self.assertEqual(app.reverter_correcao(self.pacote)['arquivos_alterados'], 2)
        self.conferir(self.originais)
        self.assertEqual(app.reverter_correcao(self.pacote)['arquivos_alterados'], 0)
        self.assertEqual(app.aplicar_correcao(self.pacote)['arquivos_alterados'], 2)
        self.assertEqual(privado.read_text(), 'NAO_LER_FIXTURE')
        self.assertFalse(list((self.pacote / 'dist').glob('.dns-9remote-*')))

    def test_reversao_original_sem_backup_e_idempotente_sem_escrita(self):
        self.assertEqual(app.reverter_correcao(self.pacote)['arquivos_alterados'], 0)
        self.assertFalse((self.pacote / app.BACKUP).exists())

    def test_segundo_bundle_desconhecido_recusa_antes_do_backup(self):
        self.arquivo('server.cjs').write_bytes(b'fonte desconhecida')
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.assertEqual(self.arquivo('cli.cjs').read_bytes(), self.originais['cli.cjs'])
        self.assertFalse((self.pacote / app.BACKUP).exists())

    def test_hash_esperado_nao_dispensa_literal_unico(self):
        nome = 'cli.cjs'
        self.arquivo(nome).write_bytes(b'fixture sem bloco')
        self.especificacoes[nome]['original'] = sha(b'fixture sem bloco')
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.assertFalse((self.pacote / app.BACKUP).exists())

    def test_literal_duplicado_recusa(self):
        nome = 'cli.cjs'
        dados = self.originais[nome] * 2
        self.arquivo(nome).write_bytes(dados)
        self.especificacoes[nome]['original'] = sha(dados)
        with self.assertRaises(app.FalhaCorrecao):
            app.planejar_correcao(self.pacote)

    def test_hash_resultante_incorreto_recusa(self):
        self.especificacoes['server.cjs']['corrigido'] = '0' * 64
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.conferir(self.originais)
        self.assertFalse((self.pacote / app.BACKUP).exists())

    def test_nome_versao_json_e_campos_duplicados_invalidos(self):
        manifesto = self.pacote / 'package.json'
        for dados in ('null', '[]', '{', '{"name":"9router","version":"3.0.43"}',
                      '{"name":"9remote","version":"3.0.44"}',
                      '{"name":"9remote","name":"9remote","version":"3.0.43"}'):
            with self.subTest(dados=dados):
                manifesto.write_text(dados)
                with self.assertRaises(app.FalhaCorrecao):
                    app.aplicar_correcao(self.pacote)
        self.conferir(self.originais)

    def test_limites_de_manifesto_e_bundle(self):
        manifesto = self.pacote / 'package.json'
        manifesto.write_bytes(b' ' * (app.MAX_MANIFESTO + 1))
        with self.assertRaises(app.FalhaCorrecao):
            app.planejar_correcao(self.pacote)
        manifesto.write_text('{"name":"9remote","version":"3.0.43"}')
        with self.arquivo('server.cjs').open('wb') as arquivo:
            arquivo.truncate(10 * 1024 * 1024 + 1)
        with self.assertRaises(app.FalhaCorrecao):
            app.planejar_correcao(self.pacote)

    def test_apenas_pasta_exata_do_ambiente_e_aceita(self):
        invalidos = (self.raiz, self.pacote / '..' / '9remote', 'relativo', None, 3, b'/tmp')
        for valor in invalidos:
            with self.subTest(valor=valor), self.assertRaises(app.FalhaCorrecao):
                app.aplicar_correcao(valor)
        with patch.dict(os.environ, {'LOCALAPPDATA': 'relativo'}):
            with self.assertRaises(app.FalhaCorrecao):
                app.aplicar_correcao(self.pacote)
        self.conferir(self.originais)

    def test_manifesto_symlink_e_recusado(self):
        manifesto = self.pacote / 'package.json'
        fora = self.raiz / 'manifesto.json'
        manifesto.rename(fora)
        self.symlink(manifesto, fora)
        with self.assertRaises(app.FalhaCorrecao):
            app.planejar_correcao(self.pacote)

    def test_bundle_symlink_e_recusado(self):
        arquivo = self.arquivo('cli.cjs')
        fora = self.raiz / 'fora.cjs'
        arquivo.rename(fora)
        self.symlink(arquivo, fora)
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.assertEqual(fora.read_bytes(), self.originais['cli.cjs'])

    def test_ancestral_node_modules_symlink_e_recusado(self):
        pasta = self.pacote.parent
        fora = self.raiz / 'fora'
        pasta.rename(fora)
        self.symlink(pasta, fora, diretorio=True)
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)

    def test_ancestral_localappdata_symlink_e_recusado(self):
        fora = self.raiz / 'fora'
        self.local.rename(fora)
        self.symlink(self.local, fora, diretorio=True)
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)

    def test_junction_simulada_em_ancestral_e_recusada(self):
        alvo = self.pacote.parent
        lstat = Path.lstat
        def meta(caminho):
            if caminho == alvo:
                return SimpleNamespace(st_mode=stat.S_IFDIR, st_file_attributes=0x400)
            return lstat(caminho)
        with patch.object(Path, 'lstat', meta):
            with self.assertRaises(app.FalhaCorrecao):
                app.planejar_correcao(self.pacote)

    def test_backup_symlink_ou_junction_e_recusado(self):
        backup = self.pacote / app.BACKUP
        fora = self.raiz / 'fora'
        fora.mkdir()
        self.symlink(backup, fora, diretorio=True)
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.assertEqual(list(fora.iterdir()), [])

    def test_arquivo_do_backup_redirecionado_e_recusado(self):
        app.aplicar_correcao(self.pacote)
        copia = self.copia('cli.cjs')
        fora = self.raiz / 'fora.cjs'
        copia.rename(fora)
        self.symlink(copia, fora)
        with self.assertRaises(app.FalhaCorrecao):
            app.reverter_correcao(self.pacote)
        self.conferir(self.corrigidos)

    def test_backup_corrompido_impede_aplicacao_e_reversao(self):
        app.aplicar_correcao(self.pacote)
        self.copia('server.cjs').write_bytes(b'backup desconhecido')
        for funcao in (app.planejar_correcao, app.aplicar_correcao, app.reverter_correcao):
            with self.subTest(funcao=funcao), self.assertRaises(app.FalhaCorrecao):
                funcao(self.pacote)
        self.conferir(self.corrigidos)

    def test_corrigido_sem_backup_nao_e_assumido_como_instalacao_propria(self):
        self.arquivo('cli.cjs').write_bytes(self.corrigidos['cli.cjs'])
        with self.assertRaises(app.FalhaCorrecao):
            app.aplicar_correcao(self.pacote)
        self.assertFalse((self.pacote / app.BACKUP).exists())

    def test_estado_parcial_de_tentativa_interrompida_pode_ser_concluido(self):
        app.aplicar_correcao(self.pacote)
        self.arquivo('cli.cjs').write_bytes(self.originais['cli.cjs'])
        self.assertEqual(app.planejar_correcao(self.pacote)['estado'], 'parcial')
        self.assertEqual(app.aplicar_correcao(self.pacote)['arquivos_alterados'], 1)
        self.conferir(self.corrigidos)

    def test_falha_de_backup_nao_altera_bundles(self):
        with patch.object(app, '_gravar_atomico', side_effect=OSError('SEGREDO_FIXTURE')):
            with self.assertRaises(app.FalhaCorrecao) as erro:
                app.aplicar_correcao(self.pacote)
        self.assertNotIn('SEGREDO', str(erro.exception))
        self.conferir(self.originais)

    def test_falha_no_segundo_bundle_restaura_o_primeiro(self):
        gravar = app._gravar_atomico
        def falhar(caminho, dados):
            if caminho == self.arquivo('server.cjs') and dados == self.corrigidos['server.cjs']:
                raise OSError('falha simulada')
            return gravar(caminho, dados)
        with patch.object(app, '_gravar_atomico', side_effect=falhar):
            with self.assertRaises(app.FalhaCorrecao) as erro:
                app.aplicar_correcao(self.pacote)
        self.assertTrue(erro.exception.reversao_completa)
        self.conferir(self.originais)
        for nome, dados in self.originais.items():
            self.assertEqual(self.copia(nome).read_bytes(), dados)

    def test_rollback_preserva_arquivo_externo_alterado_durante_falha(self):
        gravar = app._gravar_atomico
        def falhar(caminho, dados):
            if caminho == self.arquivo('server.cjs'):
                self.arquivo('cli.cjs').write_bytes(b'mudanca externa concorrente')
                raise OSError('falha simulada')
            return gravar(caminho, dados)
        with patch.object(app, '_gravar_atomico', side_effect=falhar):
            with self.assertRaises(app.FalhaCorrecao) as erro:
                app.aplicar_correcao(self.pacote)
        self.assertFalse(erro.exception.reversao_completa)
        self.assertEqual(self.arquivo('cli.cjs').read_bytes(), b'mudanca externa concorrente')

    def test_multiplas_transformacoes_sao_verificadas_e_reversiveis(self):
        nome = 'cli.cjs'
        antes = self.especificacoes[nome]['antes']
        depois = self.especificacoes[nome]['depois']
        original = b'guard_before();' + self.originais[nome]
        corrigido = original.replace(b'guard_before();', b'guard_safe();').replace(antes, depois)
        self.especificacoes[nome].update({'original': sha(original), 'corrigido': sha(corrigido),
            'trocas': ((antes, depois), (b'guard_before();', b'guard_safe();'))})
        self.arquivo(nome).write_bytes(original)
        app.aplicar_correcao(self.pacote)
        self.assertEqual(self.arquivo(nome).read_bytes(), corrigido)
        app.reverter_correcao(self.pacote)
        self.assertEqual(self.arquivo(nome).read_bytes(), original)


class SerializacaoWindows9Remote(unittest.TestCase):
    def kernel(self, espera=0):
        from unittest.mock import Mock
        kernel = Mock()
        kernel.CreateMutexW.return_value = 123
        kernel.WaitForSingleObject.return_value = espera
        return kernel

    def test_outra_manutencao_impede_entrar_e_fecha_handle(self):
        kernel = self.kernel(258)
        with patch.object(app.sys, 'platform', 'win32'), \
                patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True):
            with self.assertRaises(app.FalhaCorrecao):
                with app.manutencao():
                    self.fail('Mutex ocupado não permite manutenção.')
        kernel.ReleaseMutex.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(123)

    def test_falha_durante_manutencao_libera_mutex(self):
        kernel = self.kernel()
        with patch.object(app.sys, 'platform', 'win32'), \
                patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True):
            with self.assertRaisesRegex(ValueError, 'fixture'):
                with app.manutencao():
                    raise ValueError('fixture')
        kernel.ReleaseMutex.assert_called_once_with(123)
        kernel.CloseHandle.assert_called_once_with(123)

    def test_mutex_abandonado_permite_recuperar_arquivos_verificados(self):
        kernel = self.kernel(0x80)
        with patch.object(app.sys, 'platform', 'win32'), \
                patch.object(app.ctypes, 'WinDLL', return_value=kernel, create=True):
            with app.manutencao():
                pass
        kernel.ReleaseMutex.assert_called_once_with(123)
        kernel.CloseHandle.assert_called_once_with(123)


class ContratoJavaScript9Remote(unittest.TestCase):
    def test_blocos_isolados_preservam_ipv6_e_encerram_apenas_filhos_registrados(self):
        node = shutil.which('node') or shutil.which('node.exe')
        if not node:
            self.skipTest('Node.js não disponível para o contrato isolado.')
        payload = json.dumps({'dns_antes': app._BLOCO_CLI.decode(),
            'trocas': [[antes.decode(), depois.decode()] for antes, depois in app._TROCAS_PROCESSOS]})
        script = 'const dados = ' + payload + ';\n' + r'''
const assert = require('node:assert/strict');
const vm = require('node:vm');
(async () => {
  const execucoes = [], encerramentos = [];
  const enderecos = [{address: '2001:db8::1', family: 6}, {address: '192.0.2.1', family: 4}];
  const native = (nome, opcoes, callback) => callback(null, enderecos);
  const proibido = (...args) => execucoes.push(args);
  const contexto = vm.createContext({
    gr: {default: {lookup: native}}, eo: native, xS: {default: {lookup: native}}, z1: native,
    Mn: {resolve4: async () => ['192.0.2.1'], resolve6: async () => ['2001:db8::1']},
    Ac: {test: () => false}, fr: {execSync: proibido}, un: {execSync: proibido},
    ze: {execSync: proibido}, process: {platform: 'win32', kill: proibido},
    z: {existsSync: () => true, readFileSync: () => '1234', unlinkSync: proibido},
    Rs: proibido, Io: 'fixture.pid', En: true, gn: null, or: true
  });
  // Reproduz a perda da resposta IPv6 no bloco original, com DNS inteiramente simulado.
  vm.runInContext(dados.dns_antes, contexto);
  const antigo = await new Promise((resolve, reject) => contexto.gr.default.lookup('fixture.invalid',
    {all: true}, (erro, resultado) => erro ? reject(erro) : resolve(resultado)));
  assert.deepEqual(Array.from(antigo, x => x.family), [4]);
  vm.runInContext('gr.default.lookup=eo;xS.default.lookup=z1;', contexto);
  assert.equal(contexto.gr.default.lookup, native);
  assert.equal(contexto.xS.default.lookup, native);
  const novo = await new Promise(resolve => contexto.gr.default.lookup('fixture.invalid',
    {all: true}, (_, resultado) => resolve(resultado)));
  assert.deepEqual(novo.map(x => x.family), [6, 4]);
  // Executa somente os quatro pequenos blocos corrigidos, nunca o produto.
  for (const indice of [0, 1, 3]) vm.runInContext(dados.trocas[indice][1], contexto);
  vm.runInContext('Wr(2208);Pl();Fr(9999);', contexto);
  assert.equal(execucoes.length, 0);
  assert.equal(encerramentos.length, 0);
  function filho(nome, pid) {
    const eventos = {};
    return {pid, eventos, kill: sinal => encerramentos.push([nome, sinal]),
      once: (evento, callback) => {eventos[evento] = callback;}};
  }
  const primeiro = filho('primeiro', 1234);
  contexto.mockChild = primeiro;
  vm.runInContext('(function(c){' + dados.trocas[2][1] + ';})(mockChild)', contexto);
  vm.runInContext('Fr(1234)', contexto);
  assert.deepEqual(encerramentos, [['primeiro', 'SIGTERM']]);
  const segundo = filho('segundo', 1234);
  contexto.mockChild = segundo;
  vm.runInContext('(function(c){' + dados.trocas[2][1] + ';})(mockChild)', contexto);
  primeiro.eventos.exit();
  vm.runInContext('Fr(1234)', contexto);
  assert.deepEqual(encerramentos, [['primeiro', 'SIGTERM'], ['segundo', 'SIGTERM']]);
  segundo.eventos.exit();
  vm.runInContext('Fr(1234);Fr(9999);Wr(2208);Pl();', contexto);
  assert.equal(encerramentos.length, 2);
  assert.equal(execucoes.length, 0);
  console.log('CONTRATO9REMOTE=OK');
})().catch(erro => {console.error(erro);process.exitCode = 1;});
'''
        ambiente = {k: v for k, v in os.environ.items()
                    if k.upper() in {'PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP'}}
        resultado = subprocess.run([node, '-'], input=script, text=True, encoding='utf-8',
            capture_output=True, timeout=10, check=False, env=ambiente)
        self.assertEqual(resultado.returncode, 0, resultado.stderr)
        self.assertEqual(resultado.stdout.strip(), 'CONTRATO9REMOTE=OK')


if __name__ == '__main__':
    unittest.main()
