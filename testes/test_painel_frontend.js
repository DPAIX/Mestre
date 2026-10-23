'use strict';
// Regressões do JavaScript real do painel, sem navegador nem chamadas de rede.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {webcrypto}=require('node:crypto');

const html=fs.readFileSync(path.join(__dirname,'..','painel_rotina.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const estado={vida:{rotina:[],kanban:{},habitos_saude:{},financeiro:{}},resumo:{},provedores:{},logs:[],robotask:[],versao_estado:0};
const resposta=(body,status=200)=>({ok:status<400,status,json:async()=>body});
function elemento(id=''){
 return {value:'',reportValidity(){return true},id,disabled:false,textContent:'',style:{},dataset:{},children:[],eventos:{},classList:{toggle(){}},
  setAttribute(){},addEventListener(nome,fn){this.eventos[nome]=fn},
  append(...filhos){this.children.push(...filhos)},replaceChildren(){this.children=[]},
  set innerHTML(_valor){throw Error('HTML dinâmico não permitido neste teste')}};
}
async function painel({estadoInicial=estado}={}){
 const ids=new Map(),botoes=[];
 const obter=id=>{if(!ids.has(id))ids.set(id,elemento(id));return ids.get(id)};
 botoes.push(obter('consultar'),obter('cancelar-windows'));
 const contexto=vm.createContext({
  document:{getElementById:obter,createElement:tag=>{const e=elemento();if(tag==='button')botoes.push(e);return e},
   querySelectorAll:seletor=>seletor==='button:not([data-tab])'?botoes:[]},
  fetch:async()=>resposta(estadoInicial),AbortController,crypto:webcrypto,setTimeout,clearTimeout,setInterval:()=>0,
  confirm:()=>true,prompt:()=>null
 });
 vm.runInContext(script,contexto,{filename:'painel_rotina.html'});
 await new Promise(setImmediate);
 return {contexto,obter,executar:codigo=>vm.runInContext(codigo,contexto)};
}

test('duplo clique aguarda a ação e a atualização, sem repetir escrita',async()=>{
 const p=await painel();let liberarAcao,liberarEstado,posts=0;
 p.contexto.fetch=(_url,opt)=>{
  if(opt.method==='POST'){posts++;return new Promise(resolve=>{liberarAcao=resolve})}
  return new Promise(resolve=>{liberarEstado=resolve});
 };
 const primeiro=p.executar("enviarAcao('concluir',{id:'r1'})");
 assert.equal(p.obter('consultar').disabled,true);
 assert.equal(await p.executar("enviarAcao('concluir',{id:'r1'})"),null);
 liberarAcao(resposta({ok:true}));await new Promise(setImmediate);
 assert.equal(await p.executar("enviarAcao('concluir',{id:'r1'})"),null);
 assert.equal(posts,1);
 liberarEstado(resposta(estado));await primeiro;
 assert.equal(p.obter('consultar').disabled,false);
});

test('perguntas repetidas não geram consultas pagas concorrentes',async()=>{
 const p=await painel();let liberar,posts=0;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  posts++;return new Promise(resolve=>{liberar=resolve});
 };
 p.obter('pergunta').value='Qual a fórmula?';
 const primeiro=p.obter('consultar').eventos.click();
 await p.obter('consultar').eventos.click();
 assert.equal(posts,1);
 liberar(resposta({mensagem:'Resposta verificada'}));await primeiro;
 assert.equal(p.obter('resposta').textContent,'Resposta verificada');
});

test('cancelar reinício continua disponível durante outra ação',async()=>{
 const p=await painel();let liberar,versaoCancelamento;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  if(JSON.parse(opt.body).acao==='cancelar_reinicio_windows'){versaoCancelamento=opt.headers['X-Estado-Versao'];return resposta({mensagem:'Cancelado'})}
  return new Promise(resolve=>{liberar=resolve});
 };
 const pendente=p.executar("enviarAcao('pergunta',{texto:'teste'})");
 assert.equal(p.obter('cancelar-windows').disabled,false);
 const cancelado=await p.executar("enviarAcao('cancelar_reinicio_windows')");
 assert.equal(cancelado.mensagem,'Cancelado');
 assert.equal(versaoCancelamento,'0');
 assert.equal(p.obter('consultar').disabled,true);
 liberar(resposta({mensagem:'Fim'}));await pendente;
});

test('uma leitura antiga não sobrescreve o estado mais recente',async()=>{
 const p=await painel(),leituras=[];
 p.executar('render=s=>{globalThis.renderizado=s.valor}');
 p.contexto.fetch=()=>new Promise(resolve=>leituras.push(resolve));
 const antiga=p.executar('atualizar()'),recente=p.executar('atualizar()');
 leituras[1](resposta({...estado,valor:'recente'}));await recente;
 leituras[0](resposta({...estado,valor:'antiga'}));await antiga;
 assert.equal(p.contexto.renderizado,'recente');
});

test('falha de rede informa resultado incerto e libera controles',async()=>{
 const p=await painel();
 p.contexto.fetch=async()=>{const erro=Error('offline');erro.name='AbortError';throw erro};
 await p.executar("agir('agua')");
 assert.match(p.obter('aviso').textContent,/Confira o estado antes de tentar novamente/);
 assert.equal(p.obter('consultar').disabled,false);
});

test('sessão expirada orienta recarregar sem mostrar dados da resposta',async()=>{
 const p=await painel();
 p.contexto.fetch=async()=>resposta({erro:'conteúdo arbitrário'},403);
 await assert.rejects(p.executar("api('/api/estado')"),/Recarregue o painel/);
});

test('JSON inválido produz erro legível',async()=>{
 const p=await painel();
 p.contexto.fetch=async()=>({ok:true,status:200,json:async()=>{throw SyntaxError('HTML')}});
 await assert.rejects(p.executar("api('/api/estado')"),/Resposta inválida do painel/);
});

test('dados contendo HTML permanecem texto na renderização',async()=>{
 const p=await painel();
 p.contexto.malicioso='<img src=x onerror=alert(1)>';
 p.executar("render({vida:{rotina:[],kanban:{A_Fazer:[malicioso]},habitos_saude:{},financeiro:{}},resumo:{},provedores:{},logs:[],robotask:[]})");
 const item=p.obter('colunas').children[0].children[1];
 assert.equal(item.textContent,p.contexto.malicioso);
});

test('autoanálise separa estado local de falha 503 do provedor',async()=>{
 const p=await painel();
 p.contexto.novoEstado={...estado,autoanalise:{
  quando:'2026-10-21T12:00:00',estado:'atenção',estado_local:'sem falhas locais detectadas',
  verificacoes_ok:8,falhas_recentes:1,falhas_historicas:6,
  falhas_locais_recentes:0,falhas_externas_recentes:1,falhas_externas_pendentes:1,
  problemas:[{alvo:'Gemini',detalhe:'texto legado misturado'}],problemas_locais:[],
  avisos_externos:[{nivel:'aviso',provedor:'Gemini',categoria:'servidor_ocupado',codigo:503,
   detalhe:'Última consulta falhou; disponibilidade atual não verificada.',em_pausa:true}],sugestoes:[]
 }};
 p.executar('render(novoEstado)');
 const texto=p.obter('resumo-analise').textContent;
 assert.match(texto,/Estado local: sem falhas locais detectadas/);
 assert.match(texto,/Gemini · HTTP 503/);
 assert.match(texto,/alta demanda ou sobrecarga temporária/);
 assert.match(texto,/não indica falta de créditos/);
 assert.match(texto,/disponibilidade atual das APIs não foi verificada/);
 assert.match(texto,/Backup e arquivos locais não corrigem/);
 assert.doesNotMatch(texto,/falhas ativas|texto legado misturado/);
});

test('ocorrência recente com sucesso posterior não vira falha atual',async()=>{
 const p=await painel();
 p.contexto.novoEstado={...estado,autoanalise:{
  estado_local:'sem falhas locais detectadas',falhas_locais_recentes:0,
  falhas_externas_recentes:1,falhas_externas_pendentes:0,
  problemas_locais:[],avisos_externos:[],falhas_historicas:4
 }};
 p.executar('render(novoEstado)');
 const texto=p.obter('resumo-analise').textContent;
 assert.match(texto,/Ocorrências nos últimos 10 min: 0 locais; 1 externas/);
 assert.match(texto,/0 aviso\(s\) pendente\(s\)/);
 assert.doesNotMatch(texto,/falhas ativas|indisponível|undefined/);
});

test('problema de código fica local e não se mistura ao aviso externo',async()=>{
 const p=await painel();
 p.contexto.novoEstado={...estado,autoanalise:{estado_local:'atenção',
  problemas_locais:[{alvo:'arquivo.py',detalhe:'Erro de sintaxe'}],
  avisos_externos:[{provedor:'Gemini',codigo:503,orientacao:'Aguarde a redução de demanda.'}],
  falhas_externas_pendentes:1
 }};
 p.executar('render(novoEstado)');
 const texto=p.obter('resumo-analise').textContent;
 assert.match(texto,/Problema local — arquivo.py: Erro de sintaxe/);
 assert.match(texto,/Gemini · HTTP 503/);
 assert.match(texto,/Aguarde a redução de demanda/);
 assert.doesNotMatch(texto,/undefined/);
});

test('relatório antigo preserva evidências sem repetir orientação de recarga histórica',async()=>{
 const p=await painel();
 p.contexto.novoEstado={...estado,autoanalise:{quando:'2026-10-20T12:00:00',estado:'atenção',
  verificacoes_ok:7,falhas_recentes:0,falhas_historicas:5,
  problemas:[{alvo:'Logs',detalhe:'Falhas registradas na data anterior'}],
  sugestoes:['Há falhas anteriores por falta de créditos; adicione saldo na plataforma.']
 }};
 p.executar('render(novoEstado)');
 const texto=p.obter('resumo-analise').textContent;
 assert.match(texto,/Resultado salvo \(formato anterior\): atenção/);
 assert.match(texto,/0 nos últimos 10 min; 5 anteriores/);
 assert.match(texto,/Execute «Analisar agora» para atualizar/);
 assert.match(texto,/Registro anterior — Logs/);
 assert.doesNotMatch(texto,/adicione saldo|falhas ativas|Estado local: atenção/);
});

test('relatório ausente ou parcial usa mensagens compatíveis sem undefined',async()=>{
 const p=await painel();
 p.contexto.novoEstado={...estado,autoanalise:{}};
 p.executar('render(novoEstado)');
 assert.equal(p.obter('resumo-analise').textContent,'Nenhuma análise registrada ainda.');
 p.contexto.novoEstado={...estado,autoanalise:{verificacoes_ok:4}};
 p.executar('render(novoEstado)');
 const texto=p.obter('resumo-analise').textContent;
 assert.match(texto,/Resultado salvo \(formato anterior\): não informado/);
 assert.doesNotMatch(texto,/undefined|falhas ativas/);
});


test('central renderiza chats e propostas como texto e seleciona a conversa',async()=>{
 const p=await painel();
 p.contexto.centro={chats:[{id:'chat_a',titulo:'<script>texto</script>',provedor:'Ollama'}],
  chat_ativo:{id:'chat_a',titulo:'A',provedor:'Ollama',mensagens:[{role:'user',content:'<img onerror=x>'}]},
  tarefas:[],contribuicoes:[{id:'p1',origem:'Chat web',titulo:'Proposta',texto:'__import__("os")',status:'rascunho'}]};
 p.executar('renderColaboracao(centro)');
 assert.match(p.obter('lista-chats').children[0].textContent,/<script>texto<\/script>/);
 assert.equal(p.obter('historico-chat').children[0].children[1].textContent,'<img onerror=x>');
 let enviado; p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST')enviado=JSON.parse(opt.body);return resposta(opt.method==='POST'?{mensagem:'Selecionado'}:estado)};
 p.obter('lista-chats').children[0].eventos.click();await new Promise(setImmediate);
 assert.equal(enviado.acao,'chat_selecionar');assert.equal(enviado.id,'chat_a');
});

test('formulário cria chat com o provedor escolhido',async()=>{
 const p=await painel();let enviado;
 p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST')enviado=JSON.parse(opt.body);return resposta(opt.method==='POST'?{mensagem:'Criado'}:estado)};
 p.obter('chat-novo-titulo').value='Implementação';p.obter('chat-novo-provedor').value='Ollama';
 await p.obter('form-chat').eventos.submit({preventDefault(){}});
 assert.equal(enviado.acao,'chat_criar');assert.equal(enviado.provedor,'Ollama');assert.equal(enviado.titulo,'Implementação');
});

test('equipe só envia consulta após ação explícita com confirmação',async()=>{
 const p=await painel();let enviado;
 p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST')enviado=JSON.parse(opt.body);return resposta(opt.method==='POST'?{mensagem:'Proposta salva'}:estado)};
 p.obter('equipe-objetivo').value='Revisar implementação';
 await p.obter('consultar-equipe').eventos.click();
 assert.equal(enviado.acao,'equipe_ia');assert.equal(enviado.confirmacao,'CONSULTAR EQUIPE');assert.equal(enviado.texto,'Revisar implementação');
 assert.equal(p.obter('equipe-resposta').textContent,'Proposta salva');
});

test('lista Ollama consulta somente ao clicar, autentica e distingue modelos cloud',async()=>{
 const p=await painel(),chamadas=[];
 p.contexto.fetch=async(url,opt)=>{chamadas.push({url,opt});return resposta({padrao:'qwen3.5:4b',habilitado:true,modelos:[{nome:'qwen3.5:4b',nuvem:false},{nome:'gemma4:31b-cloud',nuvem:true}]})};
 p.contexto.centro={chats:[],chat_ativo:{id:'chat_local',titulo:'Local',provedor:'Ollama',modelo_ollama:'qwen3.5:4b'},tarefas:[],contribuicoes:[]};
 p.executar('renderColaboracao(centro)');
 assert.equal(chamadas.length,0);
 await p.obter('atualizar-modelos-ollama').eventos.click();
 assert.equal(chamadas.length,1);assert.equal(chamadas[0].url,'/api/modelos_ollama');
 assert.equal(chamadas[0].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(chamadas[0].opt.method,undefined);
 const opcoes=p.obter('chat-modelo-ollama').children;
 assert.equal(opcoes[1].value,'qwen3.5:4b');assert.match(opcoes[1].textContent,/local/);
 assert.match(opcoes[2].textContent,/nuvem \(conta, internet e cota\)/);
 assert.match(p.obter('modelos-ollama-status').textContent,/não testa geração nem acesso à nuvem/);
 assert.equal(p.obter('equipe-modelos-ollama').children[1].children[0].checked,false);
});

test('modelo salvo acompanha a conversa e mudar seletor não escreve automaticamente',async()=>{
 const p=await painel();let enviado,posts=0;
 p.contexto.centro={chats:[],chat_ativo:{id:'chat_a',titulo:'Local',provedor:'Ollama',modelo_ollama:'qwen3.5:4b',mensagens:[{role:'assistant',content:'Anterior',modelo_ollama:'qwen2.5:3b'}]},tarefas:[],contribuicoes:[]};
 p.executar('renderColaboracao(centro)');
 assert.equal(p.obter('chat-modelo-ollama').value,'qwen3.5:4b');
 assert.match(p.obter('chat-modelo-ollama').children[1].textContent,/tipo a verificar/);assert.match(p.obter('chat-modelo-aviso').textContent,/alias também pode apontar/);
 assert.match(p.obter('historico-chat').children[0].children[0].textContent,/qwen2.5:3b/);
 p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST'){posts++;enviado=JSON.parse(opt.body)}return resposta(opt.method==='POST'?{mensagem:'Modelo salvo'}:estado)};
 p.obter('chat-modelo-ollama').value='gemma4:31b-cloud';p.obter('chat-modelo-ollama').eventos.change();
 assert.equal(posts,0);assert.match(p.obter('chat-modelo-aviso').textContent,/conta Ollama.*internet e cota/);
 p.executar('renderColaboracao(centro)');
 assert.equal(p.obter('chat-modelo-ollama').value,'gemma4:31b-cloud');
 await p.obter('chat-salvar-modelo').eventos.click();
 assert.equal(posts,1);assert.equal(enviado.acao,'chat_modelo');assert.equal(enviado.id,'chat_a');assert.equal(enviado.modelo,'gemma4:31b-cloud');
 p.contexto.centro.chat_ativo={id:'chat_b',titulo:'Nuvem',provedor:'Ollama',modelo_ollama:'gemma4:31b-cloud'};
 p.executar('renderColaboracao(centro)');assert.equal(p.obter('chat-modelo-ollama').value,'gemma4:31b-cloud');assert.match(p.obter('chat-provedor').textContent,/gemma4:31b-cloud/);
 p.contexto.centro.chat_ativo={id:'chat_a',titulo:'Local',provedor:'Ollama',modelo_ollama:'qwen3.5:4b'};
 p.executar('renderColaboracao(centro)');assert.equal(p.obter('chat-modelo-ollama').value,'qwen3.5:4b');
});

test('equipe envia duas tags Ollama após confirmar os modelos e o uso cloud',async()=>{
 const p=await painel();let enviado,confirmacao;
 const seletorAnterior=p.contexto.document.querySelectorAll;
 p.contexto.document.querySelectorAll=seletor=>seletor==='#equipe-modelos-ollama input:checked'?[{value:'qwen3.5:4b'},{value:'gemma4:31b-cloud'}]:seletorAnterior(seletor);
 p.contexto.confirm=texto=>{confirmacao=texto;return true};
 p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST')enviado=JSON.parse(opt.body);return resposta(opt.method==='POST'?{mensagem:'Duas propostas salvas'}:estado)};
 p.executar("catalogoOllama={padrao:'qwen3.5:4b',modelos:[{nome:'qwen3.5:4b',nuvem:false},{nome:'gemma4:31b-cloud',nuvem:true}]}");
 p.obter('equipe-objetivo').value='Propor melhorias';
 await p.obter('consultar-equipe').eventos.click();
 assert.deepEqual(enviado.provedores,['Ollama']);assert.deepEqual(enviado.modelos_ollama,['qwen3.5:4b','gemma4:31b-cloud']);
 assert.equal(enviado.confirmacao,'CONSULTAR EQUIPE');assert.match(confirmacao,/qwen3.5:4b · local/);assert.match(confirmacao,/gemma4:31b-cloud · nuvem \(conta, internet e cota\)/);
 assert.equal(p.obter('equipe-resposta').textContent,'Duas propostas salvas');
});

test('equipe recusa mais de quatro participantes antes de consultar',async()=>{
 const p=await painel();let chamadas=0;
 const seletorAnterior=p.contexto.document.querySelectorAll;
 p.contexto.document.querySelectorAll=seletor=>seletor==='#equipe-modelos-ollama input:checked'?[{value:'qwen3.5:4b'},{value:'gemma4:31b-cloud'}]:seletor==='#equipe-provedores input:checked'?[{value:'Gemini'},{value:'OpenAI'},{value:'Claude'}]:seletorAnterior(seletor);
 p.contexto.fetch=async()=>{chamadas++;return resposta(estado)};
 p.obter('equipe-objetivo').value='Propor melhorias';await p.obter('consultar-equipe').eventos.click();
 assert.equal(chamadas,0);assert.match(p.obter('aviso').textContent,/no máximo quatro participantes/);
});

test('catálogo mostra famílias e usos sugeridos só para as tags retornadas',async()=>{
 const p=await painel(),chamadas=[];
 p.contexto.fetch=async(url,opt)=>{chamadas.push({url,opt});return resposta({padrao:'mistral:latest',habilitado:true,modelos:[
  {nome:'mistral:latest',nuvem:false,familia:'Mistral',uso_sugerido:'Planejar e revisar propostas'},
  {nome:'llama3.2:latest',nuvem:false,familia:'Llama 3.2',uso_sugerido:'Organizar tarefas'},
  {nome:'qwen3.8:27b',nuvem:false,familia:'Qwen',uso_sugerido:'<b>Propor mudanças de código</b>'}
 ]})};
 assert.equal(chamadas.length,0);
 await p.obter('atualizar-modelos-ollama').eventos.click();
 assert.equal(chamadas.length,1);assert.equal(chamadas[0].url,'/api/modelos_ollama');
 const lista=p.obter('equipe-modelos-ollama').children;
 assert.equal(lista.length,3);
 assert.match(lista[0].children[1].textContent,/mistral:latest.*Mistral.*Planejar e revisar propostas/);
 assert.match(lista[1].children[1].textContent,/llama3.2:latest.*Llama 3\.2.*Organizar tarefas/);
 assert.match(lista[2].children[1].textContent,/<b>Propor mudanças de código<\/b>/);
 const tags=p.obter('chat-modelo-ollama').children.slice(1).map(o=>o.value);
 assert.deepEqual(tags,['mistral:latest','llama3.2:latest','qwen3.8:27b']);
});

test('detalhes consultam tag codificada com token e separam contexto máximo da janela ativa',async()=>{
 const p=await painel(),chamadas=[];
 p.contexto.fetch=async(url,opt)=>{chamadas.push({url,opt});return resposta({nome:'library/qwen3.8:27b',familia:'qwen',parametros:'27B',quantizacao:'Q4_K_M',capacidades:['completion','<img onerror=x>'],contexto_maximo:131072,nuvem:false})};
 p.obter('chat-modelo-ollama').value='library/qwen3.8:27b';
 assert.equal(chamadas.length,0);
 await p.obter('chat-detalhes-modelo').eventos.click();
 assert.equal(chamadas.length,1);
 assert.equal(chamadas[0].url,'/api/modelo_ollama?nome=library%2Fqwen3.8%3A27b');
 assert.equal(chamadas[0].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(chamadas[0].opt.method,undefined);
 const texto=p.obter('detalhes-modelo-ollama').textContent;
 assert.match(texto,/Contexto máximo declarado: 131072 tokens/);
 assert.match(texto,/não é a janela ativa, a memória disponível nem garantia/);
 assert.match(texto,/<img onerror=x>/);
 assert.match(texto,/nenhuma resposta foi gerada e nenhum modelo foi baixado/);
 assert.doesNotMatch(texto,/200000|200k/);
});

test('criar conversas envia só os modelos marcados sem consultar as IAs',async()=>{
 const p=await painel(),chamadas=[];
 const anterior=p.contexto.document.querySelectorAll;
 p.contexto.document.querySelectorAll=seletor=>seletor==='#equipe-modelos-ollama input:checked'?[{value:'mistral:latest'},{value:'llama3.2:latest'},{value:'qwen3.8:27b'}]:anterior(seletor);
 p.contexto.fetch=async(url,opt)=>{chamadas.push({url,opt});return resposta(opt.method==='POST'?{mensagem:'Conversas preparadas'}:estado)};
 await p.obter('criar-chats-modelos').eventos.click();
 const posts=chamadas.filter(c=>c.opt.method==='POST');
 assert.equal(posts.length,1);assert.equal(posts[0].url,'/api/acao');
 assert.deepEqual(JSON.parse(posts[0].opt.body),{acao:'chats_modelos_ollama',modelos:['mistral:latest','llama3.2:latest','qwen3.8:27b']});
 assert.equal(chamadas.filter(c=>c.url==='/api/modelos_ollama'||c.url.startsWith('/api/modelo_ollama')).length,0);
});

test('criar conversas exige seleção e limita quatro modelos antes de escrever',async()=>{
 const p=await painel();let chamadas=0;
 p.contexto.fetch=async()=>{chamadas++;return resposta(estado)};
 await p.obter('criar-chats-modelos').eventos.click();
 assert.equal(chamadas,0);assert.match(p.obter('aviso').textContent,/Marque os modelos/);
 const anterior=p.contexto.document.querySelectorAll;
 p.contexto.document.querySelectorAll=seletor=>seletor==='#equipe-modelos-ollama input:checked'?['a','b','c','d','e'].map(value=>({value})):anterior(seletor);
 await p.obter('criar-chats-modelos').eventos.click();
 assert.equal(chamadas,0);assert.match(p.obter('aviso').textContent,/no máximo quatro modelos/);
});

test('teste de resposta aguarda confirmação e envia uma consulta sem histórico',async()=>{
 const p=await painel(),chamadas=[];let confirmacao;
 p.obter('chat-modelo-ollama').value='qwen3.8:27b';
 p.contexto.confirm=texto=>{confirmacao=texto;return false};
 p.contexto.fetch=async(url,opt)=>{chamadas.push({url,opt});return resposta(opt.method==='POST'?{mensagem:'Resposta recebida nesta consulta; não mede saldo nem garante disponibilidade futura.'}:estado)};
 await p.obter('chat-testar-modelo').eventos.click();
 assert.equal(chamadas.length,0);
 assert.match(confirmacao,/qwen3\.8:27b.*consulta real/);assert.match(confirmacao,/sem histórico.*cota/);
 p.contexto.confirm=()=>true;
 await p.obter('chat-testar-modelo').eventos.click();
 const posts=chamadas.filter(c=>c.opt.method==='POST');
 assert.equal(posts.length,1);
 assert.deepEqual(JSON.parse(posts[0].opt.body),{acao:'modelo_testar',modelo:'qwen3.8:27b',confirmacao:'TESTAR MODELO'});
 assert.match(p.obter('teste-modelo-ollama').textContent,/não mede saldo nem garante disponibilidade futura/);
});

test('definir padrão usa o modelo listado e atualiza estado e catálogo sem repetir escrita',async()=>{
 const p=await painel(),chamadas=[];let liberar;
 p.executar("catalogoOllama={padrao:'ausente:3b',habilitado:true,modelos:[{nome:'mistral:latest',nuvem:false}]}");
 p.obter('chat-modelo-ollama').value='mistral:latest';
 p.contexto.centro={chats:[{id:'chat_a',titulo:'Conversa',provedor:'Ollama',modelo_ollama:''}],chat_ativo:{id:'chat_a',titulo:'Conversa',provedor:'Ollama',modelo_ollama:'',mensagens:[]},tarefas:[],contribuicoes:[]};
 p.contexto.fetch=async(url,opt)=>{
  chamadas.push({url,opt});
  if(opt.method==='POST')return new Promise(resolve=>{liberar=resolve});
  if(url==='/api/modelos_ollama')return resposta({padrao:'mistral:latest',habilitado:true,modelos:[{nome:'mistral:latest',nuvem:false}]});
  return resposta({...estado,colaboracao:p.contexto.centro});
 };
 const primeira=p.obter('chat-modelo-padrao').eventos.click();
 await p.obter('chat-modelo-padrao').eventos.click();
 assert.equal(chamadas.length,1);
 liberar(resposta({ok:true,mensagem:'Padrão alterado sem gerar resposta'}));await primeira;
 assert.deepEqual(chamadas.map(c=>c.url),['/api/acao','/api/estado','/api/modelos_ollama']);
 const pedido=chamadas[0];
 assert.deepEqual(JSON.parse(pedido.opt.body),{acao:'modelo_padrao',modelo:'mistral:latest'});
 assert.equal(pedido.opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(chamadas[2].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.match(p.obter('chat-modelo-ollama').children[0].textContent,/Padrão do \.env: mistral:latest/);
 assert.match(p.obter('aviso').textContent,/Padrão alterado sem gerar resposta/);
});

test('padrão exige catálogo e tag presente, inclusive ao usar a opção padrão',async()=>{
 const p=await painel(),posts=[];
 p.contexto.fetch=async(url,opt)=>{if(opt.method==='POST')posts.push(JSON.parse(opt.body));return resposta(url==='/api/modelos_ollama'?{padrao:'mistral:latest',habilitado:true,modelos:[{nome:'mistral:latest',nuvem:false}]}:opt.method==='POST'?{mensagem:'Padrão salvo'}:estado)};
 await p.obter('chat-modelo-padrao').eventos.click();
 assert.equal(posts.length,0);assert.match(p.obter('aviso').textContent,/Atualize a lista.*presente no catálogo/);
 p.executar("catalogoOllama={padrao:'ausente:3b',modelos:[{nome:'mistral:latest',nuvem:false}]}");
 p.obter('chat-modelo-ollama').value='salvo-mas-ausente:7b';
 await p.obter('chat-modelo-padrao').eventos.click();
 p.obter('chat-modelo-ollama').value='';
 await p.obter('chat-modelo-padrao').eventos.click();
 assert.equal(posts.length,0);
 p.executar("catalogoOllama.padrao='mistral:latest'");
 await p.obter('chat-modelo-padrao').eventos.click();
 assert.equal(posts.length,1);assert.equal(posts[0].modelo,'mistral:latest');
});

test('falha ao salvar padrão mantém aviso e não recarrega catálogo como se tivesse sucesso',async()=>{
 const p=await painel(),chamadas=[];
 p.executar("catalogoOllama={padrao:'antigo:3b',modelos:[{nome:'mistral:latest',nuvem:false}]}");
 p.obter('chat-modelo-ollama').value='mistral:latest';
 p.contexto.fetch=async(url,opt)=>{chamadas.push(url);return resposta({erro:'O modelo saiu do catálogo; atualize a lista.'},400)};
 await p.obter('chat-modelo-padrao').eventos.click();
 assert.deepEqual(chamadas,['/api/acao']);
 assert.match(p.obter('aviso').textContent,/modelo saiu do catálogo/);
 assert.equal(p.executar('catalogoOllama.padrao'),'antigo:3b');
});

test('falha Ollama 404 orienta definir um modelo listado no relatório e nos provedores',async()=>{
 const p=await painel();
 p.contexto.comFalha={...estado,provedores:{Ollama:'modelo não acessível (HTTP 404)'},autoanalise:{estado_local:'sem falhas locais',avisos_externos:[{provedor:'Ollama',codigo:404,orientacao:'Confira a conta e use reativar.'}]}};
 p.executar('render(comFalha)');
 const orientacao=p.obter('provedores').children[1].textContent;
 assert.match(orientacao,/Atualize|atualize/);assert.match(orientacao,/tag presente.*Definir como padrão do Ollama/);
 const relatorio=p.obter('resumo-analise').textContent;
 assert.match(relatorio,/Ollama retornou HTTP 404/);assert.match(relatorio,/Testar resposta deste modelo/);
 assert.doesNotMatch(relatorio,/Confira a conta e use reativar/);
});

test('mensagem natural mostra proposta como texto e só envia nonce após confirmar',async()=>{
 const p=await painel(),posts=[];
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  const corpo=JSON.parse(opt.body);posts.push({corpo,opt});
  return resposta(corpo.acao==='pergunta'?{ok:true,mensagem:'Entendi seu pedido.',pedido:{id:'pedido_opaco',descricao:'Abrir <img onerror=x> VS Code',acao:'ignorada',campos:{comando:'ignorado'}}}:{ok:true,mensagem:'Abertura do VS Code solicitada.'});
 };
 p.contexto.confirm=()=>{throw Error('A proposta já oferece os botões de confirmação')};
 p.obter('chat-texto').value='Abra o VS Code';await p.obter('chat-enviar').eventos.click();
 assert.equal(posts.length,1);assert.equal(posts[0].corpo.acao,'pergunta');
 assert.equal(p.obter('chat-resposta').textContent,'Entendi seu pedido.');
 const cartao=p.obter('chat-pedido').children[0];
 assert.equal(cartao.children[1].textContent,'Abrir <img onerror=x> VS Code');
 await cartao.children[3].children[0].eventos.click();
 assert.equal(posts.length,2);
 assert.deepEqual(posts[1].corpo,{acao:'pedido_confirmar',id:'pedido_opaco'});
 assert.equal(posts[1].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(p.obter('chat-pedido').children.length,0);
 assert.equal(p.obter('chat-resposta').textContent,'Abertura do VS Code solicitada.');
});

test('cancelamento de proposta envia só o identificador e remove o cartão',async()=>{
 const p=await painel(),posts=[];
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  const corpo=JSON.parse(opt.body);posts.push(corpo);
  return resposta(corpo.acao==='pergunta'?{mensagem:'Revise a movimentação.',pedido:{id:'financeiro_1',descricao:'Registrar saída de R$15,00 com almoço'}}:{mensagem:'Pedido cancelado.'});
 };
 p.obter('pergunta').value='Registre um gasto de 15 reais com almoço';await p.obter('consultar').eventos.click();
 const cancelar=p.obter('pedido-resposta').children[0].children[3].children[1];
 await cancelar.eventos.click();
 assert.deepEqual(posts,[{acao:'pergunta',texto:'Registre um gasto de 15 reais com almoço'},{acao:'pedido_cancelar',id:'financeiro_1'}]);
 assert.equal(p.obter('pedido-resposta').children.length,0);
 assert.equal(p.obter('resposta').textContent,'Pedido cancelado.');
});

test('confirmação não repete o nonce em duplo clique ou após falha expirada',async()=>{
 const p=await painel(),posts=[];let liberar;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  const corpo=JSON.parse(opt.body);posts.push(corpo);
  if(corpo.acao==='pergunta')return resposta({mensagem:'Confira a ação.',pedido:{id:'expirado',descricao:'Abrir calculadora'}});
  return new Promise(resolve=>{liberar=resolve});
 };
 p.obter('chat-texto').value='Abra a calculadora';await p.obter('chat-enviar').eventos.click();
 const botao=p.obter('chat-pedido').children[0].children[3].children[0];
 const primeira=botao.eventos.click();await botao.eventos.click();
 assert.equal(posts.length,2);
 liberar(resposta({erro:'Pedido expirado ou já utilizado.'},400));await primeira;
 await botao.eventos.click();assert.equal(posts.length,2);
 assert.equal(p.obter('chat-pedido').children.length,0);
 assert.match(p.obter('aviso').textContent,/expirado ou já utilizado/);
 assert.match(p.obter('chat-resposta').textContent,/Confira o aviso e o estado/);
});

test('resposta comum e proposta inválida não criam botões de execução',async()=>{
 const p=await painel();let pedido;
 p.contexto.fetch=async(_url,opt)=>resposta(opt.method==='POST'?{mensagem:'Posso ajudar a planejar seu dia.',pedido}:estado);
 p.obter('pergunta').value='Olá, pode me ajudar?';await p.obter('consultar').eventos.click();
 assert.equal(p.obter('resposta').textContent,'Posso ajudar a planejar seu dia.');
 assert.equal(p.obter('pedido-resposta').children.length,0);
 pedido={id:'qualquer',descricao:42,acao:'pc'};
 await p.obter('consultar').eventos.click();
 assert.equal(p.obter('pedido-resposta').children.length,1);
 assert.match(p.obter('pedido-resposta').children[0].textContent,/solicitação inválida/);
 assert.equal(p.obter('pedido-resposta').children[0].children.length,0);
});

test('trocar de conversa remove propostas visíveis da conversa anterior',async()=>{
 const p=await painel();
 p.contexto.centro={chats:[],chat_ativo:{id:'chat_a',titulo:'A',modo_conversa:true},tarefas:[],contribuicoes:[]};
 p.executar('renderColaboracao(centro)');
 p.executar("exibirPedidoConversa('chat-resposta',{id:'anterior',descricao:'Abrir VS Code'})");
 assert.equal(p.obter('chat-pedido').children.length,1);
 p.contexto.centro.chat_ativo={id:'chat_b',titulo:'B',modo_conversa:false};p.executar('renderColaboracao(centro)');
 assert.equal(p.obter('chat-pedido').children.length,0);
 assert.equal(p.obter('chat-modo-conversa').checked,false);
 assert.match(p.obter('chat-modo-status').textContent,/desativada nesta sessão/);
});

test('modo conversa usa a sessão ativa e o serviço existente de configuração',async()=>{
 const p=await painel(),posts=[];
 const centro={chats:[],chat_ativo:{id:'chat_a',titulo:'A',modo_conversa:true},tarefas:[],contribuicoes:[]};
 p.contexto.centro=centro;p.executar('renderColaboracao(centro)');
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){const corpo=JSON.parse(opt.body);posts.push(corpo);centro.chat_ativo.modo_conversa=corpo.ativo;return resposta({mensagem:'Modo atualizado.'})}
  return resposta({...estado,colaboracao:centro});
 };
 p.obter('chat-modo-conversa').checked=false;await p.obter('chat-modo-conversa').eventos.change();
 assert.deepEqual(posts,[{acao:'chat_modo',id:'chat_a',ativo:false}]);
 assert.equal(p.obter('chat-modo-conversa').checked,false);
});

test('captura confirmada aparece como imagem e não como HTML',async()=>{
 const p=await painel(),imagem='data:image/png;base64,AAAA';
 p.contexto.fetch=async(_url,opt)=>resposta(opt.method==='POST'?{mensagem:'Captura obtida.',imagem}:estado);
 p.executar("exibirPedidoConversa('chat-resposta',{id:'captura',descricao:'Capturar tela'})");
 await p.obter('chat-pedido').children[0].children[3].children[0].eventos.click();
 assert.equal(p.obter('chat-resposta').children.at(-1).src,imagem);
 assert.equal(p.obter('chat-resposta').children.at(-1).alt,'Captura de tela solicitada');
});

test('escritas enviam chave única por intenção e a versão do último estado',async()=>{
 const p=await painel(),posts=[];let versao=7;
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push({url,opt});versao++;return resposta({ok:true,mensagem:'Registrado',versao_estado:versao})}
  assert.equal(url,'/api/estado');return resposta({...estado,versao_estado:versao});
 };
 await p.executar('atualizar()');
 await p.executar("enviarAcao('agua')");await p.executar("enviarAcao('agua')");
 assert.equal(posts.length,2);
 assert.match(posts[0].opt.headers['X-Idempotency-Key'],/^[a-z0-9-]{36}$/i);
 assert.notEqual(posts[0].opt.headers['X-Idempotency-Key'],posts[1].opt.headers['X-Idempotency-Key']);
 assert.equal(posts[0].opt.headers['X-Estado-Versao'],'7');assert.equal(posts[1].opt.headers['X-Estado-Versao'],'8');
 assert.equal(posts[0].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
});

test('resposta HTTP perdida recupera pergunta e proposta sem repetir chamada à IA',async()=>{
 const p=await painel(),posts=[],consultas=[];let chave;
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push(JSON.parse(opt.body));chave=opt.headers['X-Idempotency-Key'];throw new TypeError('Conexão perdida depois de executar')}
  if(url.startsWith('/api/resultado_acao')){consultas.push({url,opt});return resposta({estado:'concluido',codigo_http:200,versao_estado:2,resposta:{ok:true,mensagem:'Entendi: abrir VS Code.',pedido:{id:'acao_aprovavel',descricao:'Abrir VS Code'}}})}
  return resposta({...estado,versao_estado:2});
 };
 p.obter('chat-texto').value='Abra o VS Code';await p.obter('chat-enviar').eventos.click();
 assert.deepEqual(posts,[{acao:'pergunta',texto:'Abra o VS Code'}]);
 assert.equal(consultas.length,1);assert.equal(consultas[0].url,'/api/resultado_acao?id='+chave);
 assert.equal(consultas[0].opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(consultas[0].opt.method,undefined);
 assert.equal(p.obter('chat-resposta').textContent,'Entendi: abrir VS Code.');
 assert.equal(p.obter('chat-pedido').children[0].children[1].textContent,'Abrir VS Code');
 assert.equal(p.obter('chat-texto').value,'');
});

test('HTTP202 consulta resultado até concluir e não reenvia o POST',async()=>{
 const p=await painel(),posts=[],consultas=[];let chave;
 p.executar('aguardarRecuperacao=async()=>{}');
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push(JSON.parse(opt.body));chave=opt.headers['X-Idempotency-Key'];return resposta({estado:'em_andamento',id:chave,versao_estado:1},202)}
  if(url.startsWith('/api/resultado_acao')){
   consultas.push(url);
   return resposta(consultas.length===1?{estado:'em_andamento',id:chave,versao_estado:1}:{estado:'concluido',codigo_http:200,versao_estado:2,resposta:{mensagem:'Contribuição salva.'}});
  }
  return resposta({...estado,versao_estado:2});
 };
 const resultado=await p.executar("agir('pergunta',{texto:'Planeje meu dia'})");
 assert.equal(posts.length,1);assert.equal(consultas.length,2);
 assert.equal(consultas[0],'/api/resultado_acao?id='+chave);assert.equal(consultas[1],consultas[0]);
 assert.equal(resultado.mensagem,'Contribuição salva.');
 assert.equal(p.obter('aviso').textContent,'Contribuição salva.');
});

test('estado obsoleto409 atualiza painel sem consultar resultado ou repetir a escrita',async()=>{
 const p=await painel(),chamadas=[];let versao=5;
 p.contexto.fetch=async(url,opt)=>{
  chamadas.push({url,opt});
  if(opt.method==='POST'){versao=6;return resposta({erro:'Estado mudou.',versao_estado:6},409)}
  assert.equal(url,'/api/estado');return resposta({...estado,versao_estado:versao});
 };
 await p.executar('atualizar()');chamadas.length=0;
 assert.equal(await p.executar("agir('agua')"),null);
 assert.deepEqual(chamadas.map(c=>c.url),['/api/acao','/api/estado']);
 assert.equal(chamadas[0].opt.headers['X-Estado-Versao'],'5');
 assert.equal(p.executar('versaoServidor'),6);
 assert.match(p.obter('aviso').textContent,/estado mudou.*ação não foi repetida/);
 assert.equal(p.obter('consultar').disabled,false);
});

test('resultado desconhecido mantém chave e novo clique igual só consulta o resultado',async()=>{
 const p=await painel(),posts=[],consultas=[];let recuperavel=false;
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push(opt.headers['X-Idempotency-Key']);const erro=Error('tempo esgotado');erro.name='AbortError';throw erro}
  if(url.startsWith('/api/resultado_acao')){consultas.push(url);return resposta(recuperavel?{estado:'concluido',codigo_http:200,versao_estado:2,resposta:{mensagem:'Um copo registrado.'}}:{erro:'Resultado desconhecido.',versao_estado:1},recuperavel?200:404)}
  return resposta({...estado,versao_estado:recuperavel?2:1});
 };
 assert.equal(await p.executar("agir('agua')"),null);
 assert.match(p.obter('aviso').textContent,/consultarão o resultado sem repetir a ação/);
 recuperavel=true;
 const d=await p.executar("agir('agua')");
 assert.equal(posts.length,1);assert.equal(consultas.length,2);assert.equal(consultas[0],consultas[1]);
 assert.equal(consultas[0],'/api/resultado_acao?id='+posts[0]);
 assert.equal(d.mensagem,'Um copo registrado.');
});

test('recuperação em andamento para após limite curto e preserva a intenção',async()=>{
 const p=await painel();let posts=0,consultas=0;
 p.executar('aguardarRecuperacao=async()=>{}');
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts++;return resposta({estado:'em_andamento'},202)}
  if(url.startsWith('/api/resultado_acao')){consultas++;return resposta({estado:'em_andamento',versao_estado:1})}
  return resposta({...estado,versao_estado:1});
 };
 assert.equal(await p.executar("agir('pergunta',{texto:'Objetivo longo'})"),null);
 assert.equal(posts,1);assert.equal(consultas,6);
 assert.equal(p.executar('resultadosPendentes.size'),1);
 assert.match(p.obter('aviso').textContent,/sem repetir a ação/);
 assert.equal(p.obter('consultar').disabled,false);
});

test('erro final recuperado conserva a mensagem do servidor e atualiza estado',async()=>{
 const p=await painel(),chamadas=[];
 p.contexto.fetch=async(url,opt)=>{
  chamadas.push(url);
  if(opt.method==='POST')throw new TypeError('Resposta perdida');
  if(url.startsWith('/api/resultado_acao'))return resposta({estado:'concluido',codigo_http:400,versao_estado:3,resposta:{erro:'A atividade informada é inválida.'}});
  return resposta({...estado,versao_estado:3});
 };
 assert.equal(await p.executar("agir('pergunta',{texto:'Cadastre atividade'})"),null);
 assert.equal(chamadas.filter(c=>c==='/api/acao').length,1);
 assert.equal(chamadas.at(-1),'/api/estado');
 assert.match(p.obter('aviso').textContent,/atividade informada é inválida/);
 assert.equal(p.executar('resultadosPendentes.size'),0);
});

test('corpo perdido apósHTTP200 também usa a consulta idempotente sem novoPOST',async()=>{
 const p=await painel();let posts=0,leituras=0;
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts++;return {ok:true,status:200,json:async()=>{throw SyntaxError('corpo incompleto')}}}
  if(url.startsWith('/api/resultado_acao')){leituras++;return resposta({estado:'concluido',codigo_http:200,versao_estado:4,resposta:{mensagem:'Movimentação registrada uma vez.'}})}
  return resposta({...estado,versao_estado:4});
 };
 const d=await p.executar("agir('financeiro',{tipo:'saida',valor:'15',descricao:'Almoço'})");
 assert.equal(posts,1);assert.equal(leituras,1);assert.equal(d.mensagem,'Movimentação registrada uma vez.');
});

test('snapshot mais antigo não reduz versão usada para autorizar a próxima escrita',async()=>{
 const p=await painel();let versao=10,header;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){header=opt.headers['X-Estado-Versao'];return resposta({mensagem:'Atualizado'})}
  return resposta({...estado,versao_estado:versao});
 };
 await p.executar('atualizar()');versao=9;await p.executar('atualizar()');
 assert.equal(p.executar('versaoServidor'),10);
 await p.executar("enviarAcao('agua')");assert.equal(header,'10');
});

test('primeira mutação aguarda um snapshot válido e envia os dois headers juntos',async()=>{
 const p=await painel(),chamadas=[];
 p.executar('estadoRecebido=false;versaoServidor=null;protocoloIdempotencia=null');
 p.contexto.fetch=async(url,opt)=>{
  chamadas.push({url,opt});
  return resposta(opt.method==='POST'?{mensagem:'Registrado'}:{...estado,versao_estado:12});
 };
 await p.executar("enviarAcao('agua')");
 assert.deepEqual(chamadas.map(c=>c.url),['/api/estado','/api/acao','/api/estado']);
 assert.equal(chamadas[1].opt.headers['X-Estado-Versao'],'12');
 assert.match(chamadas[1].opt.headers['X-Idempotency-Key'],/^[a-z0-9-]{36}$/i);
});

test('versão ausente ou inválida depois de observar protocolo novo impede nova escrita',async()=>{
 for(const versao of [undefined,-1,1.5,'8',false,Number.MAX_SAFE_INTEGER+1]){
  const p=await painel(),invalido={...estado};let posts=0;
  if(versao===undefined)delete invalido.versao_estado;else invalido.versao_estado=versao;
  p.contexto.fetch=async(_url,opt)=>{if(opt.method==='POST')posts++;return resposta(invalido)};
  await p.executar('atualizar()');
  assert.equal(await p.executar("agir('agua')"),null);
  assert.equal(posts,0,'Versão inválida não deve autorizar POST: '+String(versao));
  assert.equal(p.executar('versaoServidor'),0);
  assert.match(p.obter('aviso').textContent,/Nenhuma ação foi enviada/);
 }
});

test('snapshot legado é aceito sem enviar uma chave de idempotência isolada',async()=>{
 const legado={...estado};delete legado.versao_estado;
 const p=await painel({estadoInicial:legado});let headers;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){headers=opt.headers;return resposta({mensagem:'Registrado pelo servidor legado'})}
  return resposta(legado);
 };
 const d=await p.executar("enviarAcao('agua')");
 assert.equal(d.mensagem,'Registrado pelo servidor legado');
 assert.equal(headers['X-Idempotency-Key'],undefined);assert.equal(headers['X-Estado-Versao'],undefined);
 assert.equal(headers['X-Painel-Token'],'__PAINEL_TOKEN__');
});

test('equipe da conversa renderiza tags como texto sem iniciar consultas',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',modelo_ollama:'individual:latest',equipe_paralela:true,equipe_modelos:['qwen3.5:4b','<img onerror=x>','gemma4:31b-cloud']},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}});let chamadas=0;
 p.contexto.fetch=async()=>{chamadas++;return resposta(estado)};
 p.contexto.centro=centro;p.executar('renderColaboracao(centro)');
 assert.equal(chamadas,0);assert.equal(p.obter('chat-equipe-paralela').checked,true);
 assert.equal(p.obter('chat-equipe-paralela').disabled,false);assert.equal(p.obter('chat-atualizar-equipe').disabled,false);
 assert.match(p.obter('chat-equipe-status').textContent,/3 modelo\(s\): qwen3\.5:4b, <img onerror=x>, gemma4:31b-cloud/);
 assert.match(p.obter('chat-provedor').textContent,/equipe paralela \(3 modelo\(s\)\)/);
 assert.doesNotMatch(p.obter('chat-provedor').textContent,/individual:latest/);
 assert.match(p.obter('ia-chat-ativo').textContent,/equipe paralela/);
 assert.match(html,/Usar todos os modelos nesta conversa/);
 assert.match(html,/Ollama pode enfileirar conforme a memória disponível/);
});

test('equipe cooperativa mostra modo e síntese sem confundir chats legados',async()=>{
 const chat={id:'chat_cooperativa',titulo:'Cooperar',provedor:'Ollama',equipe_paralela:true,equipe_modo:'cooperativa',equipe_modelos:['llama3.2:latest','mistral:latest']};
 const centro={chats:[chat],chat_ativo:chat,tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}});
 assert.match(p.obter('chat-equipe-status').textContent,/Equipe cooperativa ativa · 2 modelo\(s\)/);
 assert.match(p.obter('chat-provedor').textContent,/equipe cooperativa \(2 modelo\(s\)\)/);
 assert.match(p.obter('ia-chat-ativo').textContent,/equipe cooperativa/);
 assert.match(p.obter('lista-chats').children[0].textContent,/equipe cooperativa/);
 assert.match(html,/um modelo por vez.*síntese final/);
 assert.match(html,/Falhas parciais.*sem repetir consultas/);
 assert.match(html,/ações exigem concordância de todos e sua confirmação/);
 const legado={...chat};delete legado.equipe_modo;
 p.contexto.centro={...centro,chats:[legado],chat_ativo:legado};p.executar('renderColaboracao(centro)');
 assert.match(p.obter('chat-provedor').textContent,/equipe paralela/);
 assert.match(p.obter('lista-chats').children[0].textContent,/equipe paralela/);
});

test('só conversa com equipe ativa recebe prazo de vinte minutos',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',equipe_paralela:true,equipe_modo:'cooperativa',equipe_modelos:['llama3.2:latest']},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}}),prazos=[],posts=[];
 p.contexto.setTimeout=(_fn,prazo)=>{prazos.push(prazo);return 0};
 p.contexto.fetch=async(_url,opt)=>{if(opt.method==='POST')posts.push(JSON.parse(opt.body));return resposta({ok:true})};
 await p.executar("api('/api/acao',{acao:'pergunta',texto:'Compare as propostas'})");
 await p.executar("api('/api/acao',{acao:'agua'})");
 await p.executar("api('/api/acao',{acao:'conexoes_ia'})");
 await p.executar("api('/api/acao',{acao:'equipe_ia'})");
 await p.executar("api('/api/estado')");
 p.contexto.centro={...centro,chat_ativo:{...centro.chat_ativo,equipe_paralela:false}};
 p.executar('renderColaboracao(centro)');
 await p.executar("api('/api/acao',{acao:'pergunta',texto:'Individual'})");
 await p.executar("api('/api/acao',{acao:'pergunta',texto:'Prazo explícito'},{timeout:1234})");
 assert.deepEqual(prazos,[1200000,180000,240000,540000,10000,180000,1234]);
 assert.equal(posts.filter(pedido=>pedido.texto==='Compare as propostas').length,1);
});

test('ativar e desativar equipe envia só configuração da conversa com idempotência',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',equipe_paralela:false,equipe_modelos:[]},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,versao_estado:12,colaboracao:centro}}),chamadas=[];
 p.contexto.confirm=()=>{throw Error('Ativar configuração não deve pedir uma inferência ou confirmação extra')};
 p.contexto.fetch=async(url,opt)=>{
  chamadas.push({url,opt});
  if(opt.method==='POST'){
   const corpo=JSON.parse(opt.body);centro.chat_ativo.equipe_paralela=corpo.ativo;centro.chat_ativo.equipe_modo=corpo.modo||'paralela';
   centro.chat_ativo.equipe_modelos=corpo.ativo?['mistral:latest','llama3.2:latest']:[];
   return resposta({mensagem:corpo.ativo?'Equipe ativada.':'Equipe desativada.'});
  }
  return resposta({...estado,versao_estado:13,colaboracao:centro});
 };
 p.obter('chat-equipe-paralela').checked=true;await p.obter('chat-equipe-paralela').eventos.change();
 const ativacao=chamadas[0];assert.equal(ativacao.url,'/api/acao');
 assert.deepEqual(JSON.parse(ativacao.opt.body),{acao:'chat_equipe',ativo:true,id:'chat_equipe',modo:'cooperativa'});
 assert.match(ativacao.opt.headers['X-Idempotency-Key'],/^[a-f0-9-]{36}$/);
 assert.equal(ativacao.opt.headers['X-Estado-Versao'],'12');assert.equal(ativacao.opt.headers['X-Painel-Token'],'__PAINEL_TOKEN__');
 assert.equal(p.obter('chat-equipe-paralela').checked,true);assert.match(p.obter('chat-equipe-status').textContent,/mistral:latest, llama3\.2:latest/);
 p.obter('chat-equipe-paralela').checked=false;await p.obter('chat-equipe-paralela').eventos.change();
 const posts=chamadas.filter(c=>c.opt.method==='POST');assert.equal(posts.length,2);
 assert.deepEqual(JSON.parse(posts[1].opt.body),{acao:'chat_equipe',ativo:false,id:'chat_equipe'});
 assert.notEqual(posts[1].opt.headers['X-Idempotency-Key'],ativacao.opt.headers['X-Idempotency-Key']);
 assert.equal(p.obter('chat-equipe-paralela').checked,false);assert.equal(p.obter('chat-atualizar-equipe').disabled,true);
 assert.match(p.obter('chat-equipe-status').textContent,/Equipe desativada/);
 assert.deepEqual(chamadas.map(c=>c.url),['/api/acao','/api/estado','/api/acao','/api/estado']);
});

test('atualizar equipe relê catálogo no servidor e renderiza a lista persistida',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',equipe_paralela:true,equipe_modelos:['mistral:latest']},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}}),posts=[];
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push(JSON.parse(opt.body));centro.chat_ativo.equipe_modelos=['mistral:latest','llama3.2:latest','qwen3.5:4b'];return resposta({mensagem:'Catálogo atualizado.'})}
  assert.equal(url,'/api/estado');return resposta({...estado,colaboracao:centro});
 };
 await p.obter('chat-atualizar-equipe').eventos.click();
 assert.deepEqual(posts,[{acao:'chat_equipe',ativo:true,id:'chat_equipe',modo:'cooperativa'}]);
 assert.equal(p.obter('chat-equipe-paralela').checked,true);assert.match(p.obter('chat-equipe-status').textContent,/3 modelo\(s\).*qwen3\.5:4b/);
});

test('mensagem em equipe continua um único pedido e preserva confirmação da ação proposta',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',equipe_paralela:true,equipe_modelos:['mistral:latest','llama3.2:latest']},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}}),posts=[];
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){posts.push(JSON.parse(opt.body));return resposta({mensagem:'Os modelos sugerem abrir o editor.',pedido:{id:'nonce_equipe',descricao:'Abrir VS Code'}})}
  return resposta({...estado,colaboracao:centro});
 };
 p.obter('chat-texto').value='Abra o VS Code';await p.obter('chat-enviar').eventos.click();
 assert.deepEqual(posts,[{acao:'pergunta',texto:'Abra o VS Code'}]);
 assert.equal(p.obter('chat-resposta').textContent,'Os modelos sugerem abrir o editor.');
 assert.equal(p.obter('chat-pedido').children[0].children[1].textContent,'Abrir VS Code');
 assert.equal(p.obter('chat-equipe-paralela').checked,true);
});

test('equipe aguarda a primeira configuração sem repetir escrita em duplo clique',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',equipe_paralela:false,equipe_modelos:[]},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}});let liberar,posts=0;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){posts++;return new Promise(resolve=>{liberar=resolve})}
  return resposta({...estado,colaboracao:centro});
 };
 p.obter('chat-equipe-paralela').checked=true;const ativar=p.obter('chat-equipe-paralela').eventos.change();
 assert.equal(p.obter('chat-equipe-paralela').disabled,true);assert.equal(p.obter('chat-atualizar-equipe').disabled,true);
 await p.obter('chat-atualizar-equipe').eventos.click();assert.equal(posts,1);
 centro.chat_ativo.equipe_paralela=true;centro.chat_ativo.equipe_modelos=['mistral:latest'];
 liberar(resposta({mensagem:'Equipe ativada.'}));await ativar;
 assert.equal(p.obter('chat-equipe-paralela').disabled,false);assert.equal(p.obter('chat-equipe-paralela').checked,true);
 assert.equal(p.obter('chat-atualizar-equipe').disabled,false);
});

test('falha na ativação restaura a configuração salva e mantém a mensagem do servidor',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',equipe_paralela:false,equipe_modelos:[]},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}});let posts=0;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){posts++;return resposta({erro:'O catálogo precisa ter entre um e oito modelos para ativar todos.'},400)}
  return resposta({...estado,colaboracao:centro});
 };
 p.obter('chat-equipe-paralela').checked=true;await p.obter('chat-equipe-paralela').eventos.change();
 assert.equal(posts,1);assert.equal(p.obter('chat-equipe-paralela').checked,false);
 assert.equal(p.obter('chat-atualizar-equipe').disabled,true);assert.match(p.obter('chat-equipe-status').textContent,/desativada/);
 assert.match(p.obter('aviso').textContent,/entre um e oito modelos/);
});

test('trocar de conversa ou salvar modelo individual acompanha a equipe do snapshot',async()=>{
 const centro={chats:[],chat_ativo:{id:'chat_equipe',titulo:'Equipe',provedor:'Ollama',equipe_paralela:true,equipe_modelos:['mistral:latest']},tarefas:[],contribuicoes:[]};
 const p=await painel({estadoInicial:{...estado,colaboracao:centro}}),posts=[];
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method==='POST'){
   posts.push(JSON.parse(opt.body));centro.chat_ativo={...centro.chat_ativo,modelo_ollama:'llama3.2:latest',equipe_paralela:false,equipe_modelos:[]};
   return resposta({mensagem:'Modelo individual salvo.'});
  }
  return resposta({...estado,colaboracao:centro});
 };
 p.obter('chat-modelo-ollama').value='llama3.2:latest';await p.obter('chat-salvar-modelo').eventos.click();
 assert.deepEqual(posts,[{acao:'chat_modelo',id:'chat_equipe',modelo:'llama3.2:latest'}]);
 assert.equal(p.obter('chat-equipe-paralela').checked,false);assert.match(p.obter('chat-provedor').textContent,/llama3\.2:latest/);
 p.contexto.centro={...centro,chat_ativo:{id:'chat_outra',titulo:'Outra',provedor:'Gemini'}};p.executar('renderColaboracao(centro)');
 assert.equal(p.obter('chat-equipe-paralela').checked,false);assert.doesNotMatch(p.obter('chat-equipe-status').textContent,/mistral/);
});

test('equipe sem conversa fica desabilitada e não escreve mesmo se evento for disparado',async()=>{
 const p=await painel();let chamadas=0;
 p.contexto.fetch=async()=>{chamadas++;return resposta(estado)};
 assert.equal(p.obter('chat-equipe-paralela').disabled,true);assert.equal(p.obter('chat-atualizar-equipe').disabled,true);
 p.obter('chat-equipe-paralela').checked=true;await p.obter('chat-equipe-paralela').eventos.change();
 assert.equal(chamadas,0);assert.equal(p.obter('chat-equipe-paralela').checked,false);
 assert.match(p.obter('aviso').textContent,/Crie ou selecione uma conversa/);
});
