# Diagnóstico Telegram por duplo clique

1. Extraia **Diagnostico_Telegram_v1.zip** em uma pasta de Downloads.
2. Abra **DIAGNOSTICAR_TELEGRAM.bat**.
3. Aguarde a consulta. O resultado abre no Bloco de Notas e fica em **RESULTADO_TELEGRAM.txt**.
4. Envie somente o conteúdo desse arquivo: duas linhas `TELEGRAM_4` e `TELEGRAM_6`.

Não é necessário colar comandos no PowerShell ou nos terminais do 9Remote. Esse pacote é separado da instalação do bot.

## Consulta anterior que não respondeu ao Ctrl+C

O iniciador primeiro tenta interromper somente a sonda Python conhecida que consultava `getMe` e `getWebhookInfo`. Também é possível abrir **ENCERRAR_TESTE_TELEGRAM.bat** para solicitar apenas essa interrupção.

O código inteiro do argumento `python -c` precisa corresponder ao teste publicado. São aceitas diferenças de formatação e a representação equivalente do caminho F:. Antes de encerrar, o programa confere executável, argumentos, criação, proprietário e HANDLE. O argumento relativo `.\.venv\Scripts\python.exe` só é aceito quando o diretório de trabalho absoluto comprova o executável correspondente. Bots, outros programas Python, o host 9Remote e tarefas pessoais não correspondem a esse teste.

Se não puder comprovar a identidade, a sonda antiga é preservada. O novo diagnóstico usa outro processo e pode continuar independentemente. A interrupção exige `--confirmar`, fornecido pelos dois iniciadores por solicitação do proprietário.

## O que o novo teste faz

- Consulta `https://api.telegram.org/` separadamente por IPv4 e IPv6, com a verificação TLS normal e sem seguir redirecionamentos.
- Registra em qual etapa houve resposta ou espera: DNS, conexão TCP, TLS ou HTTP.
- Compara as respostas de DNS do Windows com consultas públicas a 1.1.1.1 e 8.8.8.8 somente dentro do processo de teste. Não modifica o DNS configurado no Windows.
- Registra somente os endereços públicos desse serviço, códigos de erro e tempos. Endereços locais/privados são substituídos por `LOCAL_OU_PRIVADO`.
- Usa um prazo interno de 12 segundos. Um supervisor externo limita a execução do próprio Node filho a 16 segundos, além da conferência inicial de versão, limitada a cinco segundos.

O novo teste não lê `.env`, tokens, histórico ou dados do bot. Não consulta mensagens, não modifica webhook e não altera hosts, proxy, firewall, adaptadores, modelos ou configuração do Telegram. HTTP 302 também comprova resposta do endpoint; o acesso público não valida autenticação ou recebimento de mensagens pelo bot.

Requer Windows, Python existente do assistente e Node.js 22 ou superior. O encerramento da consulta antiga usa o psutil já presente no ambiente do assistente. Não instala bibliotecas. A publicação e os testes automatizados não equivalem à execução no computador real.

## Resultado e reversão

O relatório fica somente na pasta extraída. O Node da consulta é encerrado ao concluir ou esgotar o prazo; arquivos temporários próprios são removidos. Não há configuração para reverter. Para remover o pacote, feche o relatório e exclua a pasta extraída.

A sonda antiga, se encerrada com identidade comprovada, não é relançada. Ela era apenas uma consulta de leitura; o bot e seus dados continuam sob os controles existentes.
