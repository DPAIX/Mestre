# Conversar com todos os modelos Ollama — v2.5.0

Com o Ollama aberto e `ollama list` mostrando seus modelos, reinicie o assistente atualizado e envie no Telegram:

```text
/chat equipe on
Explique como organizar minhas atividades de hoje.
```

A ativação consulta o catálogo e salva todas as tags disponíveis nessa conversa, até oito. No catálogo informado nesta sessão, são `qwen3.8:27b`, `mistral:latest`, `llama3.2:latest` e `qwen3.5:4b`. O assistente não inventa tags nem baixa modelos. Ativar não gera respostas.

Cada mensagem que precisar de IA envia uma consulta simultânea a cada tag salva, com cópias do mesmo histórico. A resposta identifica a contribuição de cada modelo e eventuais falhas. Não há segunda chamada automática para síntese ou substituição por APIs pagas. Se todos falharem, o erro é apresentado; não há repetição automática. Consultas locais reconhecidas, como mostrar rotina ou saldo, continuam usando diretamente os dados do assistente.

As respostas dos modelos não executam ferramentas. Um pedido de ação só é preparado quando todos responderem com o mesmo plano válido; alterações continuam exigindo a confirmação do proprietário. Em caso de divergência ou falha de um participante, esclareça o pedido. Não há votação que autorize executar uma ação.

O modo fica salvo por conversa e por contexto Telegram/tópico/painel. `/chat equipe off` volta ao modelo individual. Salvar outro provedor ou modelo individual também desativa a equipe. Para incluir novos modelos instalados depois, envie novamente `/chat equipe on` ou use **Atualizar equipe pelo catálogo** no painel. O catálogo não é alterado silenciosamente durante a conversa.

No painel local, abra **Chats e projeto**, escolha a conversa e marque **Usar todos os modelos nesta conversa**. O status mostra as tags salvas. A equipe de propostas do projeto, acionada por `/equipe`, continua sendo um recurso separado.

## Memória e limites

O cliente envia as consultas em paralelo; o serviço Ollama decide quantas inferências consegue executar simultaneamente. Na GTX 1660 de 6 GB informada, o modelo de 27B não cabe inteiramente na VRAM. RAM disponível, carga e configuração do servidor podem causar fila, lentidão ou falta de memória. A implementação não aumenta limites de carga nem garante que os quatro modelos fiquem residentes juntos.

Há no máximo uma equipe respondendo por processo, com até oito workers. As consultas usam o timeout HTTP existente do Ollama, entre 5 e 120 segundos. Não são feitas tentativas adicionais. Tags `cloud`, se presentes no catálogo ativado, dependem de conta, internet e cota Ollama. Os quatro modelos listados acima foram informados como locais.

## Atualizar e validar no Windows

1. Encerre a instância antiga. Atualize o pacote completo na raiz `C:\Users\Mestre\Documents\GitHub\Mestre`, incluindo `conversa_equipe.py` e os demais módulos. Atualizar apenas `assistente_pc.py` não instala o recurso.
2. Preserve `F:\MeuControlePC_v2\.env` e `F:\MeuControlePC_v2\dados`. Use `iniciar_redirecionado.bat --verificar`, depois `iniciar_redirecionado.bat`.
3. Confirme v2.5.0 em `/start`, liste `/modelos ollama`, ative `/chat equipe on` e envie uma pergunta. Confira as quatro tags na resposta e no log do serviço Ollama.
4. Teste uma leitura local e, depois, um pedido pequeno que exija confirmação. Verifique que a ação é preparada uma única vez. Use `/chat equipe off` para comparar com o modo individual.

Os testes automatizados usam modelos simulados. A geração real, o tempo de resposta e a memória precisam ser verificados nesse PC. O acesso web ao Manus continua pelo fluxo de exportar/importar contexto; uma sessão web não é uma API configurada no roteador.

Para reverter, encerre a v2.5.0 e restaure as fontes da v2.4.1. Os novos campos de equipe são opcionais e os dados permanecem no mesmo destino externo; versões anteriores ignoram esses campos. Preserve uma cópia dos dados antes de trocar de versão.
