'use strict';
// Regressões do JavaScript real do painel, sem navegador nem chamadas de rede.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const html=fs.readFileSync(path.join(__dirname,'..','painel_rotina.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const estado={vida:{rotina:[],kanban:{},habitos_saude:{},financeiro:{}},resumo:{},provedores:{},logs:[],robotask:[]};
const resposta=(body,status=200)=>({ok:status<400,status,json:async()=>body});
function elemento(id=''){
 return {value:'',reportValidity(){return true},id,disabled:false,textContent:'',style:{},dataset:{},children:[],eventos:{},classList:{toggle(){}},
  setAttribute(){},addEventListener(nome,fn){this.eventos[nome]=fn},
  append(...filhos){this.children.push(...filhos)},replaceChildren(){this.children=[]},
  set innerHTML(_valor){throw Error('HTML dinâmico não permitido neste teste')}};
}
async function painel(){
 const ids=new Map(),botoes=[];
 const obter=id=>{if(!ids.has(id))ids.set(id,elemento(id));return ids.get(id)};
 botoes.push(obter('consultar'),obter('cancelar-windows'));
 const contexto=vm.createContext({
  document:{getElementById:obter,createElement:tag=>{const e=elemento();if(tag==='button')botoes.push(e);return e},
   querySelectorAll:seletor=>seletor==='button:not([data-tab])'?botoes:[]},
  fetch:async()=>resposta(estado),AbortController,setTimeout,clearTimeout,setInterval:()=>0,
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
 const p=await painel();let liberar;
 p.contexto.fetch=async(_url,opt)=>{
  if(opt.method!=='POST')return resposta(estado);
  if(JSON.parse(opt.body).acao==='cancelar_reinicio_windows')return resposta({mensagem:'Cancelado'});
  return new Promise(resolve=>{liberar=resolve});
 };
 const pendente=p.executar("enviarAcao('pergunta',{texto:'teste'})");
 assert.equal(p.obter('cancelar-windows').disabled,false);
 const cancelado=await p.executar("enviarAcao('cancelar_reinicio_windows')");
 assert.equal(cancelado.mensagem,'Cancelado');
 assert.equal(p.obter('consultar').disabled,true);
 liberar(resposta({mensagem:'Fim'}));await pendente;
});

test('uma leitura antiga não sobrescreve o estado mais recente',async()=>{
 const p=await painel(),leituras=[];
 p.executar('render=s=>{globalThis.renderizado=s.valor}');
 p.contexto.fetch=()=>new Promise(resolve=>leituras.push(resolve));
 const antiga=p.executar('atualizar()'),recente=p.executar('atualizar()');
 leituras[1](resposta({valor:'recente'}));await recente;
 leituras[0](resposta({valor:'antiga'}));await antiga;
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
