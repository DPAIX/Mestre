# Recuperar a instalação após o patch externo — v2.8.2

O arquivo `aplicar_melhorias_v2_3_3.py` enviado instala um motor chamado v2.8.1 e altera fontes nas duas pastas C:/F:. Esta recuperação usa fontes completas auditadas e mantém os registros atuais. O instalador externo não faz parte deste pacote.

## Aplicar no Windows

1. Encerre a janela do bot para não misturar código carregado com arquivos novos. Preserve os backups que o patch já criou, a `.venv`, `F:\MeuControlePC_v2\.env`, `F:\MeuControlePC_v2\dados` e os modelos de voz/Ollama.
2. Extraia o ZIP v2.8.2 em uma pasta separada. Copie **o conteúdo da pasta interna** para a raiz de `C:\Users\Mestre\Documents\GitHub\Mestre`, substituindo os arquivos de código completos. Copiar apenas uma função ou acrescentar outro trecho deixa os wrappers antigos ativos.
3. Abra `atualizar_assistente.bat` na raiz em C:. Esse fluxo reutiliza o ambiente existente, confere dependências e pesos, limpa bytecode gerado e inicia o bot usando configuração/dados em F:. O pacote restaura também `iniciar_redirecionado.bat`, arquivado pelo patch.
4. Confira **v2.8.2** e o caminho de código em C: no console. O Startup configurado anteriormente é reaproveitado. Não execute o instalador externo novamente, pois ele reaplica as mudanças incompatíveis.

Os arquivos antigos `melhorias_v2_3_3.py` e `aplicar_melhorias_v2_3_3.py`, se ainda estiverem na pasta, não são importados pelas fontes recuperadas. Podem ser guardados com seus backups para comparação; não é necessário executá-los para iniciar o assistente.

## Conferir o resultado

- Envie **“me fale suas capacidades”**. A resposta deve listar os recursos reais localmente, sem aguardar modelos nem inventar o estado das contas.
- Envie “mostre minha rotina”. Deve consultar os registros já existentes em F:.
- Um pedido como “gastei 15,50 com almoço” deve apresentar um plano para confirmação, sem lançar o gasto antes dela.
- Conversas abertas continuam usando a configuração nativa da conversa/equipe. Modelos sem memória suficiente ou que falharem aparecem com o motivo; uma falha não é substituída por uma lista de capacidades.
- Se surgir outro erro, `/logs` mostra os eventos recentes e o detalhe redigido da última falha, com seu horário. Esse horário permite distinguir uma falha antiga do teste atual. Ao compartilhar o resultado, confira que não contém chaves ou conteúdo pessoal; não envie `.env` ou arquivos de dados completos.

## O que a recuperação preserva

Não restaura JSONs antigos automaticamente: o patch pode ter alterado registros ou pausas, e voltar um backup inteiro poderia descartar alterações legítimas posteriores. Histórico, finanças, rotina, modelos, configuração e backups permanecem no local atual. A seleção de equipe usa o estado válido já existente e suas escolhas manuais; não há migração em massa dos chats.

A pergunta exata da imagem funcionou na reprodução isolada do trecho do patch. Sem a exceção detalhada do Windows, não foi comprovada a causa específica daquele erro. Foi reproduzida uma incompatibilidade real no fallback: ele passa `chat_id` à função original, que não aceita esse argumento. A substituição completa das fontes elimina esses wrappers e a chamada incompatível.

Para reverter esta atualização, encerre o bot e restaure **todas as fontes do ZIP auditado v2.8.0**, preservando `.env`, dados e modelos, depois abra `iniciar_redirecionado.bat`. Os backups parciais do patch não cobrem todos os arquivos que ele alterou. A restauração e os testes automatizados não comprovam inferência real, credenciais, áudio, hotkeys ou logon do seu PC.
