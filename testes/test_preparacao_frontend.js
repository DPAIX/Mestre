'use strict';
// Executa o script verdadeiro do instalador num DOM local simulado, sem rede.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const html=fs.readFileSync(path.join(__dirname,'..','preparacao_autonoma.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1].replace('__PREPARACAO_TOKEN__','sessao-ficticia');
const estado={executando:false,itens:[],pendencias:[],modelos_9router:[],bot_iniciado:false};
const resposta=(body,status=200)=>({ok:status<400,status,json:async()=>body});
function elemento(tag='',id=''){
 return {tag,id,value:'',disabled:false,hidden:false,textContent:'',children:[],eventos:{},
  reportValidity(){return true},addEventListener(tipo,fn){this.eventos[tipo]=fn},
  append(...filhos){this.children.push(...filhos)},replaceChildren(){this.children=[]},
  set innerHTML(_valor){throw Error('HTML dinâmico indevido')}
 };
}
async function janela(inicial=estado){
 const ids=new Map(),todos=[],chamadas=[],intervalos=[];
 const obter=id=>{if(!ids.has(id)){const e=elemento('',id);ids.set(id,e);todos.push(e)}return ids.get(id)};
 for(const id of ['retomar','etapa','resumo','itens','painel','aviso','pendencias-caixa','pendencias','modelo-form','modelo','chave-form','nome-chave','valor-chave'])obter(id);
 const controles=['retomar','modelo','nome-chave','valor-chave'].map(obter);
 const contexto=vm.createContext({document:{getElementById:obter,createElement:tag=>{const e=elemento(tag);todos.push(e);return e},querySelectorAll:()=>[...controles,...todos.filter(e=>e.tag==='button')]},fetch:async(url,opt)=>{chamadas.push({url,opt});return resposta(inicial)},setInterval:(fn,ms)=>intervalos.push({fn,ms})});
 vm.runInContext(script,contexto,{filename:'preparacao_autonoma.html'});
 await new Promise(setImmediate);
 return {contexto,obter,chamadas,intervalos,executar:codigo=>vm.runInContext(codigo,contexto),tick:()=>new Promise(setImmediate)};
}
const evento={preventDefault(){}};

test('progresso consulta só loopback relativo, com token e sem cache',async()=>{
 const p=await janela();assert.equal(p.chamadas.length,1);
 assert.equal(p.chamadas[0].url,'/api/estado');
 assert.equal(p.chamadas[0].opt.headers['X-Preparacao-Token'],'sessao-ficticia');
 assert.equal(p.chamadas[0].opt.cache,'no-store');
 assert.equal(p.intervalos[0].ms,1500);
 await p.intervalos[0].fn();assert.equal(p.chamadas.length,2);
});

test('dados de serviço contendo HTML são texto, sem URLs arbitrárias',async()=>{
 const ataque='<img src=x onerror=alert(1)>';
 const p=await janela({...estado,itens:[{nome:ataque,estado:'pendente',detalhe:ataque}],pendencias:[{texto:ataque,servico:'gemini_chave'}]});
 const li=p.obter('itens').children[0];
 assert.equal(li.children[0].textContent,ataque+' · pendente');
 assert.equal(li.children[1].textContent,ataque);
 assert.equal(p.obter('pendencias').children[0].children[0].textContent,ataque);
 await p.obter('pendencias').children[0].children[1].eventos.click();await p.tick();
 const post=p.chamadas.find(c=>c.opt.method==='POST');assert.equal(post.url,'/api/acao');
 assert.deepEqual(JSON.parse(post.opt.body),{tipo:'abrir',servico:'gemini_chave'});
});

test('segredo é limpo antes do POST e nunca anexado à URL',async()=>{
 const p=await janela({...estado,pendencias:[{texto:'Chave necessária'}]});
 p.obter('nome-chave').value='GEMINI_API_KEY';p.obter('valor-chave').value='segredo-ficticio';
 let capturado;
 p.contexto.fetch=async(url,opt)=>{
  if(opt.method==='POST'){assert.equal(p.obter('valor-chave').value,'');capturado={url,opt};return resposta({mensagem:'Guardada localmente.'})}
  return resposta(estado);
 };
 p.obter('chave-form').eventos.submit(evento);await p.tick();
 assert.equal(capturado.url,'/api/acao');
 assert.equal(capturado.opt.headers['Content-Type'],'application/json');
 assert.equal(capturado.opt.headers['X-Preparacao-Token'],'sessao-ficticia');
 assert.deepEqual(JSON.parse(capturado.opt.body),{tipo:'chave',nome:'GEMINI_API_KEY',valor:'segredo-ficticio'});
 assert.doesNotMatch(p.obter('aviso').textContent,/segredo-ficticio/);
});

test('execução bloqueia controles e submissão não apaga segredo ainda não enviado',async()=>{
 const p=await janela({...estado,executando:true});
 p.obter('valor-chave').value='ainda-nao-enviado';
 for(const id of ['retomar','modelo','nome-chave','valor-chave'])assert.equal(p.obter(id).disabled,true);
 p.obter('chave-form').eventos.submit(evento);await p.obter('retomar').eventos.click();
 assert.equal(p.obter('valor-chave').value,'ainda-nao-enviado');
 assert.equal(p.chamadas.some(c=>c.opt.method==='POST'),false);
});

test('duplo clique mantém uma ação até atualização concluir',async()=>{
 const p=await janela();let resolverPost,resolverEstado,posts=0;
 p.contexto.fetch=(_url,opt)=>opt.method==='POST'?(posts++,new Promise(r=>{resolverPost=r})):new Promise(r=>{resolverEstado=r});
 const primeira=p.executar("acao({tipo:'retomar'})");
 await p.executar("acao({tipo:'retomar'})");assert.equal(posts,1);
 resolverPost(resposta({mensagem:'Em preparação.'}));await p.tick();
 await p.executar("acao({tipo:'retomar'})");assert.equal(posts,1);
 assert.equal(p.obter('retomar').disabled,true);
 resolverEstado(resposta({...estado,executando:true}));await primeira;
 assert.equal(p.obter('retomar').disabled,true);
});

test('resposta de polling antiga não libera controles da execução recente',async()=>{
 const p=await janela(),respostas=[];
 p.contexto.fetch=()=>new Promise(r=>respostas.push(r));
 const antiga=p.executar('atualizar()'),recente=p.executar('atualizar()');
 respostas[1](resposta({...estado,executando:true,etapa:'Etapa recente'}));await recente;
 respostas[0](resposta({...estado,executando:false,etapa:'Etapa antiga'}));await antiga;
 assert.equal(p.obter('etapa').textContent,'Etapa recente');
 assert.equal(p.obter('retomar').disabled,true);
});

test('modelo escolhido precisa pertencer ao catálogo apresentado',async()=>{
 const p=await janela({...estado,modelos_9router:['combo-local',{id:'provedor/flash'}]});
 assert.equal(p.obter('modelo-form').hidden,false);
 assert.deepEqual(p.obter('modelo').children.map(e=>e.value),['combo-local','provedor/flash']);
 p.obter('modelo').value='injetado';p.obter('modelo-form').eventos.submit(evento);await p.tick();
 assert.equal(p.chamadas.some(c=>c.opt.method==='POST'),false);
 p.obter('modelo').value='provedor/flash';p.obter('modelo-form').eventos.submit(evento);await p.tick();
 assert.deepEqual(JSON.parse(p.chamadas.find(c=>c.opt.method==='POST').opt.body),{tipo:'retomar',modelo:'provedor/flash'});
});

test('catálogo e estado fora dos limites não criam controles ilimitados',async()=>{
 const p=await janela({...estado,modelos_9router:Array.from({length:1200},(_,i)=>'combo-'+i)});
 assert.equal(p.obter('modelo').children.length,1000);
 p.contexto.fetch=async()=>resposta({...estado,itens:Array(101).fill({nome:'excesso'})});
 await p.executar('atualizar()');assert.match(p.obter('aviso').textContent,/Não foi possível ler/);
 assert.equal(p.obter('itens').children.length,0);
});

test('link do assistente só aparece para loopback e porta válida após início',async()=>{
 for(const url of ['https://evil.example','http://127.0.0.1:0','http://127.0.0.1:65536','http://127.0.0.1:8765@evil.example','javascript:alert(1)']){
  const p=await janela({...estado,bot_iniciado:true,painel_url:url});assert.equal(p.obter('painel').hidden,true,url);
 }
 const p=await janela({...estado,bot_iniciado:true,painel_url:'http://127.0.0.1:8765'});
 assert.equal(p.obter('painel').hidden,false);assert.equal(p.obter('painel').href,'http://127.0.0.1:8765');
});

test('falha de ação informa erro e libera os controles para retomar',async()=>{
 const p=await janela();p.contexto.fetch=async()=>{throw Error('Conexão local interrompida')};
 await p.executar("acao({tipo:'retomar'})");
 assert.equal(p.obter('retomar').disabled,false);
 assert.match(p.obter('aviso').textContent,/Conexão local interrompida/);
});

test('abertura de conta não é apresentada como conta conectada',async()=>{
 const p=await janela({...estado,pendencias:[{texto:'Faça login na conta',servico:'gemini_chave'}]});
 p.contexto.fetch=async(_url,opt)=>resposta(opt.method==='POST'?{mensagem:'Etapa oficial aberta. Confirme o login.'}:{...estado,pendencias:[{texto:'Faça login na conta',servico:'gemini_chave'}]});
 await p.obter('pendencias').children[0].children[1].eventos.click();await p.tick();
 assert.match(p.obter('aviso').textContent,/Confirme o login/);
 assert.equal(p.obter('pendencias-caixa').hidden,false);
});
