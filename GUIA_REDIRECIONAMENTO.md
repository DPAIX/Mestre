# Executar o código do GitHub com configuração e dados em F:

O redirecionador desta versão usa estes caminhos:

| Conteúdo | Caminho |
| --- | --- |
| Código executado | `C:\Users\Mestre\Documents\GitHub\Mestre` |
| Configuração ativa | `F:\MeuControlePC_v2\.env` |
| Dados, chats, logs, pausas e backups | `F:\MeuControlePC_v2\dados` |

O código continua em C: para você revisar e compartilhar pelo GitHub. O `.env` é lido diretamente em F:; não é copiado para C:. Os configuradores de Telegram, Ollama e Google também gravam no `.env` de F:. A pasta das fontes (`BASE`) permanece em C: para servir o HTML, exportar fontes e reiniciar a versão correta. Variáveis de configuração já definidas no processo continuam tendo prioridade sobre o `.env`, como nas versões anteriores.

## Preparar uma vez

1. Encerre o processo antigo do assistente. Uma instância usando o mesmo token/porta impede a nova de funcionar corretamente.
2. Coloque o conteúdo atualizado do pacote na raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`. Ali precisam estar `assistente_pc.py`, `caminhos_instalacao.py`, `redirecionar_assistente.py` e `iniciar_redirecionado.bat`, entre os demais módulos. Não crie uma subpasta adicional com esses arquivos.
3. Preserve `F:\MeuControlePC_v2\.env` e `F:\MeuControlePC_v2\dados`. Se os seus dados ativos estão hoje em C:, faça uma cópia preservada e leve a pasta completa para F: antes do primeiro início. O redirecionador não mescla nem apaga pastas. Se encontrar dados somente no código e o destino de F: não existir, ele interrompe a inicialização para evitar começar vazio. Se C: e F: possuem dados, a versão redirecionada usa somente F:.
4. No PowerShell, dentro da pasta do código, confira os caminhos sem iniciar o bot:

   ```powershell
   .\iniciar_redirecionado.bat --verificar
   ```

   Essa verificação usa metadados de caminhos. Não lê o conteúdo do `.env`, não consulta APIs e não testa credenciais/modelos.
5. Inicie:

   ```powershell
   .\iniciar_redirecionado.bat
   ```

O redirecionador prefere a `.venv` do código; se ela não existe, reaproveita `F:\MeuControlePC_v2\.venv\Scripts\python.exe`. Depois tenta o Python disponível no sistema, exigindo 3.11 ou superior. Isso permite usar as dependências já instaladas sem baixar outro modelo nem duplicar o ambiente. Se faltarem dependências no interpretador escolhido, use o instalador/reparo nessa instalação; não copie uma `.venv` de lugar, pois ela contém caminhos próprios.

Se preferir atualizar pelo clone Git, use **Fetch origin** no GitHub Desktop e selecione a branch `codex/correcoes-melhorias-v2.2.2`, que contém esta entrega enquanto o PR estiver em revisão. Preserve alterações locais antes de trocar de branch. O redirecionador não faz `git pull`, commit ou push, nem resolve conflitos automaticamente. Compartilhe os arquivos de código pelo seu fluxo normal do GitHub Desktop.

## Comandos disponíveis

Execute na pasta do código:

```powershell
.\iniciar_redirecionado.bat painel
.\iniciar_redirecionado.bat diagnostico
.\iniciar_redirecionado.bat telegram
.\iniciar_redirecionado.bat ollama --listar
.\iniciar_redirecionado.bat ollama --modelo mistral
.\iniciar_redirecionado.bat google
```

`painel` inicia sem Telegram; `diagnostico` executa o diagnóstico local; `telegram` abre o configurador com entrada oculta. `ollama --listar` consulta o catálogo do serviço no PC; escolha uma tag realmente presente antes de usar `--modelo`. Modelos cloud usam a conta e a cota do Ollama. Downloads só ocorrem com a opção explícita `ollama --baixar-modelo NOME`.

`google` usa o OAuth Desktop existente ou orienta a seleção do JSON. Um caminho relativo em `GOOGLE_OAUTH_CREDENTIALS`, assim como o fallback `credentials.json`, passa a ser resolvido em F: junto ao `.env`. Caminhos absolutos existentes são preservados. O token continua em `F:\MeuControlePC_v2\dados\token_google.json`; Google Calendar continua somente leitura.

Os scripts antigos, como `iniciar_windows.bat`, continuam disponíveis no modo convencional e **não selecionam F: por conta própria**. Use o novo redirecionador também para configurar as integrações. Reiniciar pelo bot preserva o código de C: e os seletores externos herdados.

## Iniciar com o Windows

Depois de conferir o funcionamento:

```powershell
.\iniciar_redirecionado.bat inicio-automatico --ativar
```

Isso atualiza o atalho gerenciado no Startup do seu usuário para chamar o código em C: com a configuração externa. Ele inicia após o login. Para remover esse atalho:

```powershell
.\iniciar_redirecionado.bat inicio-automatico --desativar
```

Atalhos próprios, tarefas agendadas e macros antigas que iniciem outra instalação precisam apontar para `iniciar_redirecionado.bat`. O redirecionador não encerra processos de outras instalações automaticamente.

## Outros caminhos e reversão

O bootstrap Python aceita caminhos absolutos explícitos. Exemplo com uma pasta de dados externa já existente:

```powershell
py -3 .\redirecionar_assistente.py --codigo "C:\Users\Mestre\Documents\GitHub\Mestre" --env "F:\MeuControlePC_v2\.env" --dados "F:\OutraPasta\dados" --verificar
```

`--python` seleciona um interpretador existente. `.env` e dados precisam ficar fora da árvore de código; um seletor inválido ou arquivo ausente interrompe a execução, sem usar uma configuração diferente silenciosamente. `MEUCONTROLEPC_ENV` e `MEUCONTROLEPC_DADOS` são seletores do processo definidos pelo redirecionador antes de importar a aplicação, não configurações para colocar dentro do próprio `.env`.

Para reverter, encerre a versão redirecionada, desative o atalho gerenciado se o tiver ativado e inicie a instalação anterior com sua cópia preservada dos dados. Nenhum arquivo de F: é movido ou apagado pelo redirecionador.
