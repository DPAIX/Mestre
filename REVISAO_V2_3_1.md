# MeuControlePC v2.3.1 — modelos Ollama e colaboração com Manus

## Causa e comportamento

A v2.3.0 usava somente `OLLAMA_MODEL` para todas as conversas. O launcher Ollama pode mostrar agentes com modelos diferentes, mas isso não configura o MeuControlePC. Além disso, as mensagens de configuração chamavam qualquer modelo de local, mesmo tags cloud. O usuário informou Qwen, Gemma cloud e acesso ao aplicativo Manus.

Agora o painel e o Telegram consultam explicitamente `/api/tags` no serviço loopback. É possível selecionar um modelo por conversa, manter históricos independentes e formar uma equipe com vários modelos. A seleção verifica a presença no catálogo, sem gerar resposta, baixar modelo ou alterar `.env`. Falhas de uma escolha explícita não pausam outros modelos nem apagam o estado do padrão. Cada pergunta explícita faz uma tentativa sem fallback; o estado geral de Ollama continua se referindo ao modelo padrão.

O catálogo identifica nuvem por `-cloud`, `:cloud` e metadados remotos informados pelo serviço. Não é auditoria de rede nem prova de capacidade da conta. O instalador reutiliza modelos locais existentes; não seleciona cloud automaticamente. O usuário pode configurar um modelo cloud explicitamente.

## Arquivos alterados

- `multi_ia.py`: leitura autenticada via painel do catálogo e inferência com modelo explícito, mantendo o endpoint restrito a IP loopback sem proxy/redirecionamentos.
- `colaboracao_chats.py` e `servicos_chat.py`: configuração por conversa compatível com dados antigos, identificação do modelo nas novas respostas e prompts externos para Manus e agentes de código.
- `assistente_pc.py`: `/modelos ollama`, `/chat modelo NOME`, `/chat modelo padrao`, `/equipe modelos A,B | Objetivo` e GET autenticado `/api/modelos_ollama`.
- `equipe_ia.py`: até quatro participantes entre provedores/modelos, uma consulta por participante, modelos Ollama em sequência na equipe, propostas com origem identificada.
- `painel_rotina.html`: atualização explícita do catálogo, seleção por conversa e seleção de modelos para a equipe. Conteúdo dinâmico continua tratado como texto.
- `configurar_ia_local.py` e `instalar_ia_local.bat`: catálogo local/cloud, `--listar`, `--usar-existente` e reaproveitamento de modelos; configuração atômica preserva outras credenciais.
- Testes de protocolo HTTP local, roteador, Telegram, equipe, configuração, privacidade da exportação e JavaScript. Guias/README atualizados.

O Manus participa por exportação/importação: prompt próprio no ZIP, tarefas com hashes e proposta revisável. Não há conector API Manus nem acesso automático à conta ou ao navegador. Claude Code, OpenCode e Cline recebem prompts próprios, sem serem iniciados pelo assistente. O pacote continua excluindo históricos, credenciais e dados operacionais.

## Validação

A versão anterior foi conferida isoladamente: 174 testes aprovados antes desta mudança. A nova suíte tem 199 testes Python e 20 testes comportamentais JavaScript aprovados, além de `compileall`. A matriz Windows/Linux com Python 3.11, 3.12 e 3.14 é registrada no CI do PR.

Os testes usam fontes/dados temporários, mocks e um servidor HTTP local que simula Ollama; não usam inferência de modelos reais, saldo de provedores, conta Manus ou ações Windows. Os scripts `.bat` de instalação/configuração tiveram revisão estática; não foram executados no computador do usuário.

## Validar no Windows

1. Extraia em uma pasta nova, preserve a instalação anterior e siga o LEIA-ME para manter seus dados e `.env` locais.
2. Execute `instalar_windows.bat`. Depois `configurar_ia_local.bat --listar` e `configurar_ia_local.bat --modelo qwen3.5:4b`, usando uma tag realmente presente no catálogo. Nenhum novo download é necessário se o modelo já estiver disponível.
3. Encerre o processo antigo e inicie o assistente da nova pasta. Use `/modelos ollama`, `/chat novo Código` e `/chat modelo qwen3.5:4b`; faça uma pergunta. Crie outra conversa para `gemma4:31b-cloud`, se registrado e autorizado na conta Ollama.
4. Teste a equipe de dois modelos e confira duas propostas distintas no projeto. Teste Manus anexando o ZIP exportado e importando a resposta. Os modelos precisam responder no seu PC/conta; lista ou instalação não confirma inferência.

## Riscos e reversão

Modelos locais dependem da RAM/GPU/CPU do PC; modelos cloud dependem de conta, internet e cota. Uma equipe com vários modelos sequenciais pode demorar alguns minutos. Trocar o modelo na mesma conversa preserva e envia seu histórico ao novo motor escolhido; crie outra conversa para separar contextos. Não há execução automática das propostas.

Para reverter, encerre a nova versão e volte a iniciar a pasta anterior v2.3.0. Preserve uma cópia dos dados antes de alternar; os campos novos são adicionais, sem mudança na versão do JSON. Reconfigure o modelo padrão na pasta anterior se necessário. Não apague modelos nem credenciais para reverter.

Referências de protocolo: https://docs.ollama.com/api/tags e https://docs.ollama.com/cloud.
