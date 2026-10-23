> A v2.6.0 acrescenta a [equipe cooperativa](GUIA_EQUIPE_COOPERATIVA.md): `/chat equipe on` usa todas as tags sequencialmente, preservando o perfil CPU. Não repita a ativação do perfil depois da equipe, pois ela seleciona o modelo individual.

# Conversar usando o Llama em CPU — v2.5.2

O teste isolado de `llama3.2:latest` recebeu texto em 14,3 segundos no PC. Ele solicitou CPU, contexto 1024 e somente oito tokens. Isso comprova aquela geração curta; não comprova defeito de GPU nem o desempenho de uma conversa completa. O assistente agora oferece esse caminho por escolha explícita.

## Atualizar e ativar no Telegram

1. Encerre o assistente antigo. Atualize **todos os arquivos de código** do pacote na raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`, sem criar uma subpasta adicional. Preserve `.venv`, seu `.env` e todos os dados existentes. O pacote não inclui credenciais nem dados de uso.
2. Abra `iniciar_redirecionado.bat`. Confira no console o código em C:, configuração `F:\MeuControlePC_v2\.env`, dados `F:\MeuControlePC_v2\dados` e versão **2.5.2**. Mantenha o serviço Ollama aberto, fora do modo **Selecionar** do console.
3. No Telegram, envie `/modelos perfil cpu` e confirme com **Executar** em até 90 segundos. O pedido pertence ao usuário/chat que o criou e só pode ser executado uma vez. Se expirar, envie o comando novamente.
4. A confirmação verifica a tag local no catálogo e salva/aplica o perfil, seleciona `llama3.2:latest`, ativa a conversa individual com Ollama e desliga a equipe **desta conversa**. O histórico permanece. A configuração pelo Telegram é aplicada sem outro reinício e não faz geração ou download.
5. Envie uma mensagem curta, como “Olá, pode me ajudar?”. Aguarde o resultado antes de outro pedido. Pedidos de ações continuam passando pela interpretação e confirmação habituais; uma resposta do modelo não executa código arbitrário.

## O que muda nas chamadas

O `.env` ativo recebe `OLLAMA_PERFIL=cpu`, `OLLAMA_HABILITADO=1` e `OLLAMA_MODEL=llama3.2:latest`, preservando as demais linhas. Cada chamada Ollama confirma o modelo local no catálogo e solicita `num_gpu=0`, `num_ctx=1024`, `num_predict=128` e `keep_alive=0`. O limite de saída é maior que os oito tokens do diagnóstico para permitir frases curtas. O tempo do diagnóstico não prevê o tempo dessas respostas.

O perfil vale para **todas as próximas chamadas Ollama deste processo**, inclusive outras conversas/equipes. Outras equipes não são desligadas automaticamente; pare seus pedidos enquanto verifica o Llama. O perfil padrão de uma instalação existente continua inalterado até a ativação. Não há tentativa automática após erro nem fallback automático para CPU.

Contexto pequeno pode omitir partes de históricos longos, e o limite de saída pode cortar respostas extensas ou planos complexos. O serviço recebe a instrução de descarregar o modelo após cada chamada; carregar novamente pode aumentar a latência. Não foram alterados drivers, paginação, limites do servidor ou arquivos dos modelos.

## Usar o configurador com o bot parado

Na pasta do código, no PowerShell:

```powershell
.\iniciar_redirecionado.bat ollama --perfil-cpu
.\iniciar_redirecionado.bat
```

Depois, no Telegram, use `/chat equipe off`, `/chat provedor Ollama` e `/chat modelo padrao`. A configuração pelo terminal não modifica os chats; o bot precisa reiniciar para carregar a alteração do arquivo. Não use o configurador em paralelo a outro processo que esteja alterando o mesmo `.env`.

## Equipe e reversão

Os quatro modelos continuam no catálogo e `/chat equipe on` continua disponível por escolha explícita. Ativá-la envia uma chamada para cada modelo e pode gerar fila, consumo de memória e timeouts. Os pesos informados somam cerca de 25,6 GiB; não há garantia de manter todos residentes no PC de 16 GiB de RAM e 6 GiB de VRAM. O perfil CPU não torna o modelo de 27B menor.

Para voltar à escolha de CPU/GPU pelo próprio serviço, envie `/modelos perfil padrao` e confirme. Isso salva `OLLAMA_PERFIL=padrao`, mantém o modelo atualmente configurado e desliga a equipe desta conversa. **Não restaura o modelo anterior.** Para selecionar outro depois, use `/modelos padrao NOME` com uma tag instalada.

Com o bot parado, a alternativa é `iniciar_redirecionado.bat ollama --perfil-padrao` e reiniciar. Para reverter o código, restaure as fontes v2.5.1 e preserve o `.env`/dados de F:. Essa versão anterior ignora `OLLAMA_PERFIL`.
