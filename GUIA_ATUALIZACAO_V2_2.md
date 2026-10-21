# MeuControlePC v2.2 — correções e instalação sem perda de dados

## Resumo do que foi alterado

- **Sem desligamento remoto do computador:** comandos de desligar são bloqueados localmente. **O reinício do Windows continua disponível apenas porque foi solicitado anteriormente**, desabilitado por padrão no `.env` e sujeito a confirmações adicionais. Não existe botão para desligar o PC.
- **Falhas ativas versus históricas:** autoanálise considera *ativas* somente as falhas dos últimos 10 minutos; erros antigos permanecem nos logs, sem criar falsos alarmes ativos.
- **Melhorias idempotentes:** pressionar repetidamente o botão sem alterar dados ou tarefas RoboTask não gera outro ZIP/CSV/notebook. Uma alteração real permite a próxima atualização; backups manuais ainda podem ser feitos.
- **Multi-IA transparente:** estado separa `sem chave`, `configurado; não testado`, `sem créditos`, `limite temporário`, `servidor ocupado` e `modelo não acessível`. Uma pausa de API é lembrada quando o assistente reinicia. Nenhum status indica internet disponível sem teste real.
- **Recuperação após recarga:** `/reativar_ias` ou **Limpar pausas locais das IAs** no painel apaga somente os bloqueios *locais*. Não compra créditos nem evita limites remotos.
- **Diagnóstico offline:** botão na aba Multi-IA, comando `/verificar` no Telegram, ou `diagnosticar_offline.bat` no Windows. Não chama provedores externos.
- **Controle de custos:** mensagens livres não são encaminhadas automaticamente às APIs; escreva `/ia pergunta` ou `/pesquisar tema` para usar serviços externos.
- **Segurança:** nenhuma credencial antiga foi incluída. O próprio código do assistente continua protegido contra edição automática não supervisionada.

## Atualizar a instalação existente em F:\MeuControlePC_v2

1. Encerre o assistente (feche o prompt que executa `iniciar_windows.bat`). **Não reinicie nem desligue o PC para atualizar.**
2. Faça cópia de segurança de sua pasta antes da atualização, especialmente `dados` e `.env` (mantenha a cópia protegida, pois `.env` contém segredos).
3. Extraia **Atualizacao_MeuControlePC_v2_2.zip** *dentro de* `F:\MeuControlePC_v2`, mantendo a estrutura das pastas.
4. Execute `aplicar_atualizacao_v2_2.bat` dentro dessa pasta. O instalador criará backup **do código antigo** em `dados\backups_codigo_v2_1\...` e substituirá apenas os arquivos necessários. `.env`, `.venv`, `dados` e seus arquivos pessoais não serão substituídos.
5. Execute `diagnosticar_offline.bat` para conferir o ambiente. Depois execute `iniciar_windows.bat`.
6. No Telegram, teste `/start`, `/verificar`, `/modelos`, `/evoluir` e `/melhorar`. Para perguntar às IAs, use explicitamente `/ia Qual é ...` ou `/pesquisar ...`. No painel, acesse `http://127.0.0.1:8765` no próprio computador.

## Sobre o comando Reiniciar Windows

Ele **não desliga** o PC definitivamente: solicita reinício do sistema operacional. Continua **desabilitado por padrão** com `REINICIO_WINDOWS_HABILITADO=0`. Caso habilitado e confirmado, o Windows poderá forçar o fechamento de aplicativos no fim do prazo, levando à perda de dados não salvos. Quem não quiser usar esse recurso deve manter `0`.

## O que ainda exige validação no Windows

- Autenticação real do Telegram com token renovado e ID autorizado.
- Chamadas Gemini, OpenAI, Claude e Exa com chaves e créditos válidos; o programa não pode criar créditos nem contornar quotas.
- Teclas RoboTask F8/F9/F10 e acessibilidade da sessão gráfica.
- Google Calendar OAuth, dependente de `credentials.json` legítimo.
- Reinício do assistente e, se deliberadamente habilitado, reinício do Windows. **Os testes não reiniciam o computador.**

## Referências técnicas

- Modelos Gemini: https://ai.google.dev/gemini-api/docs/models
- Guia da API Telegram: https://core.telegram.org/bots/api
- Documentação do pip: https://pip.pypa.io/en/stable/
- Comando `shutdown` no Windows: https://learn.microsoft.com/en-us/windows-server/administration/windows-commands/shutdown
