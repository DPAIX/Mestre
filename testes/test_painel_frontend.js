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
 return {id,disabled:false,textContent:'',style:{},dataset:{},children:[],eventos:{},classList:{toggle(){}},
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
