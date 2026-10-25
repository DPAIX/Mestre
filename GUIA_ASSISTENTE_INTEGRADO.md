# Assistente integrado v2.10.2

Se você já executou a preparação e quer concluir somente as pendências, use [retomar a configuração](GUIA_RETOMAR_CONFIGURACAO.md). Não é necessário reinstalar bibliotecas ou reconfigurar Telegram/Startup.

Esta versão reúne os recursos do MeuControlePC e adiciona Gemini Interactions e agentes gerenciados. O código e os fluxos foram validados com dados fictícios, serviços HTTP locais e transporte simulado do SDK Google. Instalação, geração com suas contas, RoboTask e pareamento remoto ainda precisam ser verificados no seu Windows.

## Atualizar no seu computador

1. Encerre o bot e o painel atuais. Guarde uma cópia das fontes v2.9.2 para reversão.
2. Extraia o pacote completo e copie **o conteúdo da pasta MeuControlePC_v2_10_2** para `C:\Users\Mestre\Documents\GitHub\Mestre`, onde está `assistente_pc.py`. Não crie uma segunda pasta do projeto dentro dessa raiz.
3. Preserve `F:\MeuControlePC_v2\.env`, `F:\MeuControlePC_v2\dados`, as `.venv` existentes e `F:\Models`. O ZIP não contém configurações pessoais, dados nem pesos. **Não substitua seu .env pelo exemplo.**
4. Abra `preparar_assistente_completo.bat`. As etapas são independentes: confirme no console as que deseja executar. A etapa de bibliotecas prepara dependências Google/Telegram/voz, verifica o ambiente e baixa somente os pesos de voz escolhidos. Exige Internet e espaço; o bot deve estar encerrado. Ela não inicia o bot.
5. Configure Telegram, Ollama, Node.js, 9Router, 9Remote e Gemini nas etapas correspondentes. As credenciais são digitadas no console local, com entrada oculta; não cole chaves na conversa ou no GitHub.
6. Abra `iniciar_redirecionado.bat`. Se faltar Telegram, use `iniciar_somente_painel.bat`. No painel `http://127.0.0.1:8765`, abra **Integrações & memória** e confira o estado de cada recurso. A sondagem de serviços é explícita e não gera respostas.

O início gerenciado é uma etapa opcional. A consolidação guarda apenas o atalho legado exato `assistente_pc.py - Atalho.lnk` fora de Startup e registra o lançador atual. Não reabilita Ollama, OpenClaw ou Tailscale nem altera o estado desses aplicativos no Gerenciador de Tarefas. Confira a habilitação da entrada gerenciada na aba Inicializar antes de esperar que ela execute após logon.

## Recursos e requisitos

| Recurso | Uso | O que precisa estar pronto |
| --- | --- | --- |
| Rotina, lembretes, finanças, Kanban, água e Pomodoro | Menu, painel e linguagem natural; alterações confirmadas | Telegram autorizado ou painel local |
| Windows e RoboTask | Programas permitidos, captura e atalhos confirmados | Windows, dependências e macros instaladas; executar no PC |
| Agenda Google | Consulta autorizada | OAuth pelo `autorizar_google.bat` |
| Texto e áudio | Mensagens e áudios de até três minutos; Whisper local por padrão | Dependências e pesos de voz; não envia áudio para nuvem por padrão |
| Memória | Notas explícitas, listagem, exclusão confirmada e exportação Markdown por conversa | `MEMORIA_HABILITADA=1`; nenhum aprendizado silencioso de arquivos |
| Modelos Ollama | Catálogo, seleção individual, perfil CPU e equipe | Ollama instalado, serviço respondendo e tags existentes |
| Equipe cooperativa Ollama | Até 32 participantes selecionados; sequência e síntese | Recursos físicos/conta suficientes; orçamento finito por rodada |
| Equipe paralela Ollama | Até oito participantes; opção manual | Memória/GPU suficientes; não é o padrão para PC com pouca RAM |
| Equipe de propostas | Até oito participantes, com até quatro tags Ollama e quatro modelos/combos 9Router, dentro desse total | Provedores configurados e consulta explícita; resultados entram no projeto para revisão |
| 9Router | Modelo/combo global e escolha por conversa; catálogo e teste explícitos | Node.js 22+, npm, pacote gerenciado, contas e modelo/combo no dashboard |
| 9Remote | Instalação gerenciada e abertura da interface oficial | Node.js 22+, conta/pareamento e autorização na própria interface |
| 14 aplicativos de agentes | Abrir/configurar pelo lançador oficial Ollama | Instalação, modelo e login próprios de cada aplicativo |
| Gemini Interactions | Conversa pelo modelo configurado, `store=False` | `google-genai>=2.9,<3`, chave e acesso ao modelo |
| Gemini Managed Agents | Criar perfis, iniciar/continuar tarefas, consultar, cancelar, excluir e trazer resultado ao projeto | Chave/projeto com acesso ao agente e cota Gemini API |

Os aplicativos integrados são Claude Code, OpenCode, Hermes Agent, Hermes Desktop, Copilot CLI, Cline, DeepSeek Harness, Pi, OpenClaw, ChatGPT Desktop, Codex CLI, Oh My Pi, Droid e Qwen Code. Sua integração abre o terminal oficial para configuração e execução interativa. Eles não se tornam modelos Ollama nem executores automáticos de código recebido pelo Telegram. As tarefas gerenciadas Gemini usam a API de agentes de fato, em ambiente remoto.

## Ollama e o computador com cerca de 16 GiB

O painel inicia antes da preparação Ollama. Se a porta já está ocupada e a API ainda não responde, o assistente não abre outro `ollama serve`. `OLLAMA_INICIAR_SERVICO=0` permite usar o serviço já aberto, sem iniciá-lo quando estiver ausente; a etapa de política do configurador salva essa escolha.

Para começar com menos carga, escolha o perfil CPU compacto no configurador, se Llama estiver no catálogo. No Telegram, `/modelos perfil cpu` pede confirmação e desativa a equipe desta conversa. Para uma única resposta use `/chat equipe off`; `/chat modelo NOME` escolhe uma tag existente. O perfil CPU estima se os pesos excedem a RAM física e explica o adiamento. Ele não transforma um modelo de 27B em um modelo pequeno nem remove sua tag.

`/chat equipe on` ativa cooperação; `/chat equipe paralelo` é a opção simultânea. A rodada tem orçamento e interrompe novos envios se houver timeout; isso não garante o cancelamento da geração já recebida pelo Ollama. Catálogos maiores que o limite são recusados com mensagem explícita, sem descartar modelos silenciosamente. Modelos cloud, como os mostrados nas capturas, exigem login, acesso e cota próprios; não são baixados automaticamente pelo assistente.

## 9Router e 9Remote

No configurador, prepare Node.js, instale o pacote e inicie o 9Router. O dashboard só é aberto depois de o serviço responder ao catálogo ou à autenticação. Conecte as contas e crie o modelo/combo no dashboard; depois configure o cliente do assistente. Mesmo em loopback, o gateway pode enviar mensagens e histórico aos provedores conectados e consumir cota.

No painel, **Atualizar catálogo 9Router** permite escolher modelos/combos. **Usar nesta conversa** salva uma escolha isolada, sem mudar o padrão global. **Testar modelo** envia uma única pergunta curta, sem histórico. No Telegram use `/chat gateway IDENTIFICADOR` e confirme. Seleções manuais são preservadas. Para mudar o provedor use `/chat provedor Ollama` ou o seletor do painel.

O 9Remote oferece instalação, abertura e pareamento na interface oficial. Esta versão não inventa uma API de controle do 9Remote e não inicia um túnel automaticamente. A sessão remota e suas permissões são controladas pelo 9Remote. O painel MeuControlePC permanece em loopback. O suporte a ambos usa versões oficiais fixadas no módulo `integracoes_9stack.py`.

## Gemini Interactions e Managed Agents

Abra `configurar_gemini.bat` ou a etapa Gemini do configurador. Escolha `1`/`interactions` ou Enter, informe um modelo disponível à sua chave e salve. O exemplo usa `gemini-3.8-flash`; não há seleção automática de alternativa paga se um ID ou a cota falhar. Configurações antigas sem `GEMINI_API_MODO` continuam usando `generate_content` até você mudar essa opção. Reinicie o assistente após salvar.

**Colab Pro não inclui automaticamente créditos da Gemini API.** A chave deve pertencer a um projeto Google com acesso ao modelo/agente e cota ou faturamento necessário. A preparação local não comprova acesso à conta. A conversa com modelo usa histórico explícito e `store=False`; tarefas gerenciadas precisam de `background=True` e `store=True` e seguem a retenção da API Google.

No painel, escolha a conversa, leia suas tarefas locais e escreva uma tarefa para o agente. O padrão da documentação atual é `antigravity-preview-09-2026`. Também há sugestões Deep Research. Prepare, revise e confirme: somente então ocorre o envio. O sandbox Antigravity fica sem rede externa por padrão; a caixa de rede é uma autorização explícita para aquele envio. Agentes Deep Research mantêm as capacidades próprias do serviço e não usam essa opção de sandbox.

Você pode criar um perfil com título e instruções, usar esse perfil, continuar uma tarefa concluída do mesmo agente, atualizar o estado remoto manualmente, pedir cancelamento, excluir uma interação encerrada e importar seu texto como contribuição para revisão. Não há polling automático, anexação automática de arquivos/notas/histórico local nem execução do resultado no computador.

No Telegram:

```text
/integracoes
/integracoes testar
/gemini
/gemini tarefa Compare duas soluções para meu projeto.
/gemini consultar ID_LOCAL
/gemini cancelar ID_LOCAL
/gemini contribuir ID_LOCAL
/gemini excluir ID_LOCAL
/gemini perfil Revisor | Revise propostas e sugira testes sem executar código.
/memoria exportar
```

Os IDs locais começam com `g`; consulte os IDs exibidos pelo assistente. Consultar exige a conversa proprietária. Cancelamento é uma solicitação à API: o estado devolvido é exibido, sem presumir que parou. Em timeout após criação, o registro fica `resultado_incerto`; confira o AI Studio antes de repetir. O transporte impede uma segunda saída da mesma operação mesmo em versões do SDK que normalizam a opção de tentativas. Rejeições conhecidas, como chave ausente ou cota, permitem remover o registro local sem chamar a API. Limites por conversa: 25 tarefas e dez perfis.

O exemplo [Gemini no Colab](exemplos/gemini_agentes_assistente.ipynb) usa o mesmo adaptador e pede a chave por entrada oculta. Ele não importa dados pessoais e não foi executado em sua conta. Não é necessário executar um notebook para usar o assistente.

## Rede, limites e reversão

Esta atualização não altera DNS, proxy, Firefox, hosts, adaptadores, firewall, Tailscale ou a inicialização de aplicativos externos. Mantenha a configuração de navegação que voltou a funcionar e o backup do hosts. Não execute a substituição de hosts proposta anteriormente apenas para instalar esta versão. A origem da falha de rede não foi comprovada como sendo o Ollama.

Para reverter, encerre bot/painel e restaure as fontes v2.9.2; preserve `.env`, dados e modelos. A opção Gemini pode voltar para `generate_content` pelo configurador. Tarefas/perfis remotos não são apagados ao trocar o código; consulte ou encerre-os no Gemini antes de remover seu acompanhamento local. Os registros locais `gemini_*.json` são separados dos esquemas legados. Se consolidou Startup, restaure o atalho guardado e remova somente o `.cmd` gerenciado se quiser desfazer aquela etapa. Não restaure atalhos antigos em paralelo com o gerenciado.

## Referências

- [Google: Interactions overview](https://ai.google.dev/gemini-api/docs/interactions-overview?hl=pt-br)
- [Google: agentes personalizados](https://ai.google.dev/gemini-api/docs/custom-agents)
- [Notebook oficial solicitado](https://colab.research.google.com/github/google-gemini/cookbook/blob/main/quickstarts/Get_started_managed_agents.ipynb)
- [Ollama CLI](https://docs.ollama.com/cli)
- [9Router](https://github.com/decolua/9router) e [9Remote](https://github.com/decolua/9remote)
- [Memória e integrações anteriores](GUIA_INTEGRACOES_V2_9.md), incluindo as referências de memória solicitadas no histórico.
