# MeuControlePC v2.9.0 — modelos, agentes, 9Router, 9Remote e memória

## Atualizar a instalação existente

1. Encerre o bot. Preserve `.venv`, backups, `F:\MeuControlePC_v2\.env`, `F:\MeuControlePC_v2\dados` e `F:\Models`.
2. Extraia o ZIP em uma pasta separada e copie **o conteúdo da pasta interna** para `C:\Users\Mestre\Documents\GitHub\Mestre`, substituindo as fontes completas.
3. Abra `atualizar_assistente.bat`. Ele confere as dependências Python, reutiliza a voz preparada e inicia o assistente. Confira **v2.9.0** no console; o Startup existente continua funcionando.
4. No painel local, abra **Integrações & memória**. Também pode pedir as ações por texto no Telegram. Cada instalação ou abertura apresenta sua descrição antes de executar.

Esta atualização não executa novamente o patch externo. Não exige apagar os registros ou reinstalar os modelos locais. A instalação de aplicativos adicionais acontece separadamente, na janela do PC, e requer rede e **Node.js 22+ com npm** para 9Router/9Remote. O gerenciador confere esse requisito; se faltar, instale o LTS em [nodejs.org](https://nodejs.org/en/download), reabra o terminal e repita a operação. Nenhum pacote listado no catálogo é declarado funcionando apenas por estar presente.

## Corrigir a espera e usar os modelos

“Me diga quais as suas capacidades” e suas paráfrases completas agora têm resposta local, sem esperar uma equipe. Pedidos locais de rotina/finanças continuam consultando os registros existentes; alterações continuam exigindo confirmação.

Na equipe cooperativa, o primeiro modelo que responder pode apresentar uma contribuição **provisória** no Telegram. A resposta final continua separada e é a única que pode preparar um plano. A rodada compartilha orçamento padrão de 90 segundos, com até 30 segundos por consulta CPU. Se um prazo expirar, não são enviados novos pedidos ou síntese naquela rodada. Os demais participantes ficam identificados como adiados, continuam selecionados e não contam como sucesso.

Esses limites controlam novos envios e timeouts de socket; não comprovam cancelamento no serviço nem um limite absoluto de relógio. O painel aguarda até quatro minutos pela pergunta em equipe, mantendo a recuperação de resultados sem repetir a ação.

O Qwen 27B registrado com 16,52 GiB continua acima do orçamento físico reportado de 15,96 GiB. O assistente mantém a tag e informa o adiamento. Não altera memória virtual, drivers ou pesos para simular capacidade disponível.

Para o **Gemma `gemma4:31b-cloud`** mostrado nas imagens:

1. Abra `adicionar_gemma_nuvem.bat` e confirme o registro no Ollama. Esse fluxo não altera o modelo padrão do assistente ou envia histórico.
2. Atualize os modelos no painel. Na aba Multi-IA, revise **Permitir nuvem no perfil CPU**: consultas poderão enviar mensagens e o histórico usado na resposta à conta Ollama, usando Internet e cota.
3. A equipe automática inclui os modelos registrados. No perfil CPU autorizado, consulta o menor local, depois a nuvem e os demais locais. Se outra consulta expirar, uma contribuição cloud já recebida pode ser aproveitada na resposta final.

A autorização vale para a exceção de nuvem no perfil CPU. O perfil padrão do serviço e os aplicativos externos mantêm configurações próprias. Uma escolha manual por conversa permanece manual. `OLLAMA_NO_CLOUD=1` prevalece nas consultas CPU. Registro, conta e cota não são garantia de resposta.

## Aplicativos de agentes do Ollama

O catálogo inclui Claude Code, OpenCode, Hermes Agent, Hermes Desktop, Copilot CLI, Cline, DeepSeek Harness, Pi, OpenClaw, ChatGPT Desktop, Codex CLI, Oh My Pi, Droid e Qwen Code.

Use **Chats e projeto → Agentes pelo Ollama**, o botão Telegram **Agentes e integrações** ou `gerenciar_agentes.bat`. Exemplos: “abra o agente Claude Code” e “configure o OpenCode com o modelo gemma4:31b-cloud”.

Esses nomes representam aplicativos. Os modelos são escolhidos separadamente. Após confirmar, o assistente abre o fluxo oficial `ollama launch` em outra janela; instalação, login e permissões são acompanhados ali. A compatibilidade é conferida na ajuda do Ollama instalado. O processo filho não herda as chaves carregadas pelo bot, e nenhum histórico é passado como argumento. Não há execução autônoma de tarefas por SDK dos 14 aplicativos ou consenso entre suas ferramentas.

## 9Router

1. No painel **Integrações & memória**, selecione 9Router e prepare **Instalar**; confirme e aguarde o resultado na outra janela. A versão gerenciada é **0.5.109**, em `%LOCALAPPDATA%\MeuControlePC\integracoes\9router`.
2. Prepare **Iniciar** e confirme. O wrapper solicita `127.0.0.1:20128`, sem atualização automática e sem encerrar um processo que já ocupe a porta.
3. Prepare **Abrir** para acessar o dashboard. Configure suas contas, modelos e combos **no próprio 9Router**.
4. No formulário do assistente, consulte os modelos/combos e salve o ID escolhido com a ativação. Se o gateway exigir chave, use `configurar_9router.bat`: entrada oculta no console, preservando o `.env` externo. Não envie a chave pelo Telegram. Reinicie o bot após alterar credenciais pelo console.

O cliente usa `/v1/models` e `/v1/chat/completions`, aceita somente endpoint loopback literal e bloqueia redirecionamento/proxy externo. Loopback não significa inferência local: o gateway pode encaminhar mensagens e histórico a provedores, conforme contas/combos/cotas configurados nele. A consulta explícita de catálogo também pode consultar provedores.

Quando habilitado com modelo/combo, o 9Router passa a atender **conversas automáticas**. Conversas manuais mantêm sua escolha. Ao desativá-lo, a política automática volta à equipe Ollama, sem apagar histórico. A equipe de propostas aceita até oito participantes, com concorrência de quatro; selecionar 9Router junto com provedores diretos pode consultar contas coincidentes em caminhos diferentes.

O cliente faz uma requisição, sem retries próprios. Fallbacks internos, cobranças e escolha de backends são políticas do 9Router; o assistente não afirma usar todos os provedores sem que o combo esteja configurado para isso. Não são ativados MITM, interceptação de IDEs ou túneis do gateway.

## 9Remote

Instale a versão gerenciada **3.0.43** no mesmo painel ou use `gerenciar_9stack.bat`. Os pacotes ficam em `%LOCALAPPDATA%\MeuControlePC\integracoes\9remote`, separados das fontes e das credenciais do bot.

- **Abrir** solicita `9remote ui`, sem solicitar o início do túnel. A interface pode ser acessada no PC em `http://127.0.0.1:2208`.
- **Iniciar** é uma ação distinta: solicita o host e túnel de acesso **remoto**. A descrição informa acesso a terminal, arquivos e tela pelos dispositivos autorizados. Exige pedido explícito e confirmação.
- Faça o login, pareamento e gestão de dispositivos no aplicativo oficial. Chaves, QR codes e URLs de pareamento não são capturados nem enviados pelo assistente. Encerre ou revogue acessos pela interface do 9Remote; não foi inventado um comando `stop` ou `revoke` ausente no CLI analisado.

As interfaces de rede e permissões do 9Remote pertencem ao produto oficial. Seu servidor não foi comprovado como restrito a loopback; não confunda a URL usada para abrir a UI com uma garantia de isolamento. O painel do MeuControlePC permanece em loopback e não é publicado automaticamente. O 9Remote não entra no Startup gerenciado do assistente.

Os instaladores usam versões exatas dos dois pacotes e npm oficial, sem shell, em janela própria e com espera de dez minutos. Dependências transitivas não ficam totalmente congeladas na primeira instalação. Um timeout do instalador não comprova encerramento de scripts filhos; confira a janela antes de tentar novamente.

## Memória por notas explícitas

Inspirada na separação entre histórico curto e memória durável do [AI Memory Vault](https://github.com/jaredrhod/ai-memory-vault), esta implementação é própria e usa os mecanismos atômicos do núcleo.

Peça “guarde na memória Estudos: estudar cálculo às 20h” e confirme. Também há formulário na aba Integrações & memória. “Mostre minhas notas” ou `/memoria` mostra somente as notas da conversa interna ativa; outras conversas/tópicos não as recebem. Um título igual atualiza a nota após nova confirmação.

São até 50 notas, título de 80 e texto de 800 caracteres. Uma busca lexical recupera notas relevantes, até 1500 caracteres, identificadas no prompt como **dados, não instruções**. `MEMORIA_HABILITADA=0` desativa seu uso nas respostas, sem apagar os arquivos. Não há extração automática de preferências, gravação de respostas de modelos ou busca semântica vetorial. Os novos arquivos `memoria_<hash>.json` ficam nos dados externos e não são publicados.

O [site de Jared](https://jaredrhod.com/) e o repositório [fullstack-agent](https://github.com/jaredrhod/fullstack-agent) foram consultados como referências. Não copiamos templates/licenças nem executamos seus instaladores. A voz baseada no SDK Claude, o visualizador e o controle por gestos não substituem a voz local existente. Não foi possível obter a transcrição dos vídeos enviados; a implementação foi conferida nas fontes primárias dos projetos.

## Validar e reverter

Depois de atualizar, teste a frase da imagem, a leitura da rotina e uma nota confirmada. Instale/abra uma integração por vez e confira seu resultado na janela do PC. Somente uma resposta real comprova aquela consulta; os testes automatizados usam fixtures.

Para reverter as fontes, encerre o bot e restaure o ZIP completo auditado v2.8.2, preservando `.env`, dados, pesos e notas. Desative o 9Router no formulário antes da reversão se quiser voltar ao Ollama. Os aplicativos externos devem ser encerrados no próprio produto; não são desinstalados ou mortos ao reverter o bot. Configurações, contas e dispositivos criados neles não são desfeitos por uma troca de fontes.

Fontes oficiais: [9Router](https://github.com/decolua/9router), [documentação 9Router](https://docs.9router.com/), [9Remote](https://github.com/decolua/9remote), [lançador Ollama](https://docs.ollama.com/cli), [Gemma cloud](https://ollama.com/library/gemma4:31b-cloud).
