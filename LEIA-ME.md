> **v2.5.0:** [Equipe paralela de modelos Ollama](GUIA_EQUIPE_PARALELA.md) · [Auditoria e correções](AUDITORIA_ASSISTENTE_V2_5_0.md) · [Mudanças, testes e reversão](REVISAO_V2_5_0.md). Para executar o código do GitHub em C: usando `.env` e dados de F:, inicie por `iniciar_redirecionado.bat`: [guia](GUIA_REDIRECIONAMENTO.md).

> **v2.4.0:** [Conversa e controle por linguagem natural](GUIA_CONVERSA.md) · [Google Agenda](GOOGLE_AGENDA.md) · [Mudanças, testes e reversão](REVISAO_V2_4_0.md).

> **v2.3.2:** [Relatório de Mistral, Llama e Qwen](REVISAO_V2_3_2.md).

> **v2.3.1:** [Relatório dos modelos por conversa e colaboração com Manus](REVISAO_V2_3_1.md).

> **v2.3.0:** [Relatório da implementação dos três modos de chats](REVISAO_V2_3_0.md).

> **Revisão v2.2.3:** veja [REVISAO_V2_2_3.md](REVISAO_V2_2_3.md). Diagnóstico local separado dos serviços de IA, orientação específica para 503 e testes sem os avisos de recursos abertos no Python 3.14.

> **Revisão v2.2.2:** consulte [REVISAO_V2_2_2.md](REVISAO_V2_2_2.md) para correções, testes, atualização e reversão.

> **Correção v2.2.1:** consulte [GUIA_CORRECAO_V2_2_1.md](GUIA_CORRECAO_V2_2_1.md). Corrige o botão Multi-IA, amplia a auditoria de código e melhora o bloqueio de desligamento remoto.

> **Atualização v2.2:** veja [GUIA_ATUALIZACAO_V2_2.md](GUIA_ATUALIZACAO_V2_2.md). O desligamento do computador não está disponível; o reinício do Windows permanece opcional.

# MeuControlePC v2 — bot Telegram e painel local

**Atualização v2.3.1:** escolha modelos Ollama por conversa, consulte uma equipe com vários modelos e leve o contexto para Manus e agentes de código. Se já tem modelos, use `configurar_ia_local.bat --listar` e `configurar_ia_local.bat --modelo qwen3.5:4b` com o nome do seu catálogo. Veja [o guia](GUIA_MULTIPLOS_CHATS.md) e [o relatório de testes e reversão](REVISAO_V2_3_1.md).

Revisão do projeto legado `assistente_pc.py`, destinada ao Windows. Código Python separado em núcleo, roteador de IA, controles locais e painel HTTP. **Não foram incorporadas as chaves originais; elas estavam expostas nos arquivos antigos e precisam ser revogadas e substituídas.** O projeto foi testado em ambiente isolado; o funcionamento real no seu computador depende da instalação e das novas credenciais.

## Instalar no Windows

1. **Faça uma cópia de segurança da pasta antiga**, especialmente `assistente_pc.py`, `gestao_vida.json`, `minhas_macros.json`, os arquivos `.tsk` do RoboTask e outros dados. Não envie arquivos `.env`, `token.json`, `credentials.json` ou chaves ao Telegram.
2. Descompacte **este ZIP em uma pasta nova** (por exemplo, `Desktop\MeuControlePC_v2`), sem substituir o diretório antigo. Verifique espaço em disco: os registros anteriores indicavam cerca de 1,2 GB livres.
3. Execute `instalar_windows.bat` (Python 3.11 ou mais recente necessário). O instalador cria `.venv`, instala pacotes **sem o cache global do pip** e copia `.env.exemplo` para `.env` somente se ainda não existir. Ele também executa os testes locais.
4. Revogue o token Telegram antigo por meio do **@BotFather** e gere um novo; substitua também as credenciais antigas de Gemini, OpenAI, Anthropic e Exa nas respectivas plataformas. Edite o arquivo `.env` com **as novas credenciais**. Nenhuma dessas chaves é obrigatória para os comandos locais, exceto `TELEGRAM_TOKEN` para o bot.
5. **Se aparecer `Token must contain a colon`**, execute `configurar_telegram.bat`. Ele solicitará um novo token do BotFather com entrada oculta, validará o formato e salvará no `.env` sem sobrescrever outras APIs. `iniciar_windows.bat` também oferece essa configuração ao detectar token inválido. Para obter `TELEGRAM_ALLOWED_USER_IDS`, inicie com o campo vazio e envie `/id` ao bot: nessa condição ele apenas informa o identificador, sem aceitar ações de controle. Copie o número para `.env` e reinicie. Alternativamente use um ID pessoal previamente conhecido.
6. **Antes de executar o bot pela primeira vez**, migre seus dados executando no Prompt/PowerShell, dentro da pasta nova:
   ```bat
   .venv\Scripts\python.exe migrar_legado.py "C:\Users\SEU_USUARIO\Desktop"
   ```
   Substitua a pasta se os seus arquivos antigos estiverem em outro lugar. A migração nunca sobrescreve dados já existentes na pasta `dados`.
7. Execute `iniciar_windows.bat`. Acesse `http://127.0.0.1:8765` **no próprio PC** para o painel; o bot Telegram usa os botões e comandos descritos em `/ajuda`.
8. Se quiser apenas o painel local, sem Telegram, execute `iniciar_somente_painel.bat`.

## Correção de `Permission denied` durante o pip no Windows

Se o instalador anterior parou com `ERROR: Could not install packages due to an OSError: [Errno 13] Permission denied` envolvendo `AppData\Local\pip\Cache\wheels\...\pyautogui-...whl`, não apague os arquivos de rotina nem o ambiente virtual. Este é um problema de acesso ao **cache do instalador**, e a revisão usa `--no-cache-dir` para evitá-lo. Você pode executar `corrigir_instalacao_windows.bat` diretamente na pasta já extraída; ele reaproveita `.venv`, não sobrescreve `.env` nem a pasta `dados/` e verifica a suíte local.

Alternativamente, no Prompt de Comando aberto na pasta do projeto:

```bat
.venv\Scripts\python.exe -m pip install --no-cache-dir --disable-pip-version-check -r requirements.txt
.venv\Scripts\python.exe -m unittest discover -s testes -v
```

Se o erro persistir, feche outros terminais/instaladores Python, verifique se o antivírus bloqueou o arquivo e compartilhe **apenas a nova mensagem de erro, sem tokens ou `.env`**. Não é necessário executar o prompt como administrador ou apagar indiscriminadamente o cache global. Não foi possível validar o `.bat` no Windows nesta preparação; os testes Python são executados em ambiente isolado.

## Funcionalidades integradas

| Área | O que esta versão faz |
| --- | --- |
| Telegram | Proprietários autorizados, menu unificado e comandos de texto, confirmação antes de ações no computador, captura de tela após confirmação |
| Windows | Status de espaço/CPU/RAM (via `psutil`), gerenciador de tarefas, desktop, Enter, Explorer, Calculadora, Bloco de Notas, VS Code |
| RoboTask | Catálogo `.tsk` com decodificação Unicode, hotkeys F8 (NesTask), F9 e F10 com confirmação |
| Multi-IA | Gemini (modelo configurável), OpenAI e Claude para perguntas; Exa para pesquisa explícita; tratamento distinto de 404, limite, falta de saldo e autenticação |
| FURG/rotina | Atividades, conclusão de tarefas, Kanban, links FURG e agenda, registros de horários |
| Finanças | Entradas, saídas, saldo preservado dos dados antigos e projeção do custo RU **sem lançamento automático** |
| Saúde/foco | Água e Pomodoro, registro ao completar o tempo; painel com hábitos |
| VS Code/Jupyter | Exportação de `analise_autonoma_rotina.ipynb` e `tabela_rotina.csv` |
| Logs/aprendizado | Logs rotativos, histórico de frequência de comandos, sugestões de evolução somente analíticas, exportação com redação de chaves |
| Painel local | HTTP em `127.0.0.1`, autenticação de ações por token de sessão e validação de origem, abas dinâmicas atualizadas dos JSONs |

O comando `arrume` é tratado como pedido de diagnóstico local, não como pergunta de dicionário. O estado **"não verificado" de uma API não significa que ela esteja operacional**. Os erros de falta de crédito/credencial não são solucionáveis apenas por código. O **modo de evolução não reescreve os próprios arquivos Python**; a revisão de código deve passar por testes e aprovação humana.

### Comandos úteis

`/status`, `/pc`, `/print`, `/robotask`, `/f8`, `/reparar`, `/logs`, `/exportar`, `/rotina`, `/concluir r1`, `/agua`, `/financas`, `/gasto 15,50 almoço`, `/entrada 30 reembolso`, `/ru 5`, `/kanban`, `/tarefa Concluir relatório`, `/pomodoro`, `/evoluir`, `/ia explique Cálculo II`, `/pesquisar automação industrial`, `/notebook`, `/agenda`, `/macros`, `/macro <nome>`, `/ecossistema` e `/reiniciar`.

As macros importadas são **preservadas**. Execução de comandos de terminal, código arbitrário e macros com múltiplos passos não verificados é bloqueada. Macros antigas de abertura de hubs e ações explicitamente reconhecidas são compatíveis. Não há acesso remoto ao painel HTTP pela internet; o acesso remoto é pelo Telegram autenticado.

## Google Agenda (opcional)

O botão da Agenda abre o serviço web. Para ler efetivamente os próximos eventos, habilite a integração OAuth:

1. Na Google Cloud, gere um `credentials.json` OAuth **Desktop app** com Google Calendar API habilitada; não publique esse arquivo.
2. Adicione ao `.env`: `GOOGLE_OAUTH_CREDENTIALS=C:\caminho\credentials.json`.
3. Execute `autorizar_google.bat`; faça login no navegador na janela local. O token de leitura fica em `dados\token_google.json` e **não** é incluído no pacote de exportação.
4. Use `/agenda`. O programa acessa somente os eventos do calendário principal, com escopo `calendar.readonly`.

A sincronização de escrita no Google Agenda, integração com arquivos privados do Google Drive e controle real de serviços externos **não** foram ativados sem autorização e credenciais apropriadas.

## Provedores de IA

Modelos padrão no `.env`: `GEMINI_MODEL=gemini-3.8-flash`, `OPENAI_MODEL=gpt-4o-mini`, `ANTHROPIC_MODEL=claude-sonnet-4-5`. Esses nomes são **configuráveis**, já que os catálogos e as permissões mudam; um nome no `.env` não prova que a sua conta tem acesso. O roteador não envia comandos sensíveis do PC às APIs. Quando faltar cota/crédito, registra a falha, aplica suspensão temporária e **não anuncia um reparo fictício**. Não há cobrança nem compra automática de créditos.

## Diagnóstico e testes

Após a instalação, use:

```bat
.venv\Scripts\python.exe assistente_pc.py --diagnostico
.venv\Scripts\python.exe -m unittest discover -s testes -v
.venv\Scripts\python.exe ponte_robotask.py
```

Os testes automatizados verificam operações locais, JSON, finanças, Unicode, segurança, roteamento de erros e painel HTTP. **Eles não validam** sua conexão Telegram, o clique das hotkeys no seu Windows, seus arquivos RoboTask reais ou o saldo das APIs. Esses itens devem ser testados no computador-alvo.

## Segurança e manutenção

- Exclua/revogue as credenciais antigas e nunca copie `config_apis.json` para `.env` sem higienizá-lo. Os arquivos legados continham chaves em texto puro.
- Não execute os arquivos `funcoes_autonomas.py` ou versões antigas de `ponte_robotask.py` sem revisão. Eles não são importados pela versão v2.
- O painel é acessível **somente no próprio computador**. Não exponha a porta 8765 via roteador, túnel ou proxy público.
- Dados são gravados atomicamente em `dados/`; o diretório legado não é apagado. Faça backups antes de modificações importantes.
- Se tiver problema no Windows, anote a mensagem do console e os registros de `dados/assistente_v2.log` (retire qualquer dado sensível antes de compartilhar).

## Arquivos do pacote

`assistente_pc.py` (Telegram/painel), `nucleo.py` (dados e funções locais), `multi_ia.py` (APIs), `automacao_pc.py` (Windows), `agenda_google.py`, `painel_rotina.html`, `ponte_robotask.py` (consulta), `migrar_legado.py`, `.env.exemplo`, `dados_iniciais/` (cópias higienizadas de estado, rotina, macros e catálogo), `testes/`, arquivos `.bat` e requisitos.

## Erro: Token must contain a colon (início do Telegram)

Esse erro indica token do Telegram ausente, placeholder ou formato inválido em `.env`. **Não é falha de instalação do Python nem de dependência.** Abra `configurar_telegram.bat` e cole na janela, sem enviar a ninguém, um token **novo** gerado pelo `@BotFather`. Ele tem a forma geral `numeros:codigo` e não deve conter aspas, espaços ou comentários. O assistente valida apenas a sintaxe: você precisa iniciar o bot para verificar se o token é aceito pelo Telegram. Quando o bot iniciar, envie `/id`; preencha `TELEGRAM_ALLOWED_USER_IDS` com o número obtido e reinicie. Sem o ID, somente `/id` pode ser usado via Telegram; para trabalhar sem bot, execute `iniciar_somente_painel.bat`. A ferramenta preserva as demais configurações e a pasta `dados`. Nunca envie o `.env` ao chat.

## Atualização v2.1: autoanálise, melhorias e reinicialização

Consulte **`GUIA_ATUALIZACAO_V2_1.md`** para instalar sobre a v2 sem substituir `.env`, `.venv` ou `dados`. A nova aba **Autoanálise & reinício** do painel oferece diagnóstico agendado, aplicação de melhorias pré-definidas mediante confirmação, reinício controlado apenas do assistente e reinício completo do Windows com dupla confirmação, desabilitado por padrão. A execução da última opção pode forçar o fechamento de aplicativos (ver documentação Microsoft no guia). Para iniciar automaticamente após logon, use os scripts `habilitar_inicio_com_windows.bat` e `desabilitar_inicio_com_windows.bat` (opt-in).
