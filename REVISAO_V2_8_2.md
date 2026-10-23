# Revisão v2.8.2 — recuperação de patch externo e capacidades locais

## Evidência e diagnóstico

Foi analisado o anexo `aplicar_melhorias_v2_3_3.py`, de 1624 linhas e SHA-256 `0dda0b57b22060e254649ddb2d8ecaa1286470caa2cefce832eaeb7f305729cd`. O instalador não foi executado nem importado na cópia de trabalho. Somente um recorte revisado de definições/hooks foi reproduzido em ambiente isolado com módulos, registros e serviços substituídos por fixtures, sem rede ou escrita na instalação.

A sintaxe do anexo é válida. A frase “me fale suas capacidades” responde no recorte isolado; a captura de tela mostra apenas “comando falha”, sem a exceção. Não se atribui a causa específica da imagem a uma hipótese não reproduzida. Uma quebra concreta foi reproduzida no fallback: linha 1333 passa `chat_id` para a assinatura original `preparar_pedido_natural(texto, contexto, *, progresso=None)`, causando `TypeError` quando esse ramo é alcançado.

Outras incompatibilidades encontradas no anexo:

- Linhas 1288–1293 incluem mutações de finanças/rotina/água/Kanban entre as leituras, e o executor 856–1014 grava diretamente, removendo confirmações. Regex não ancoradas/sem negação podem reconhecer ações citadas ou negadas, como “não apague r1”.
- A lista de limpeza inclui `iniciar_redirecionado.bat` (linha 112), movido em 1145–1149, embora necessário ao fluxo C:/F:. `rglob`/`rmtree` em 1153–1155 alcança caches recursivos, inclusive ambientes virtuais.
- A migração em 1184 procura `chats` na raiz, mas a base usa `contextos`. Isso é coerente com as “0 conversas otimizadas” da captura. Mesmo assim regrava JSON e limpa pausas em 1198–1205, sem gravação atômica ou backup completo dos dados afetados.
- O Turbo 759–811 contorna o roteador, histórico, perfil CPU e validação de endpoint/resposta. O fallback 1097–1103 pode pesquisar com Exa sem pedido de pesquisa. Falhas podem virar mensagens de capacidades ou integridade não comprovada em 834–853 e 1107–1111.
- O backup cobre cinco fontes, mas também são reescritos módulos fora dessa lista. O fallback de rotina 548–591 pode gravar diretamente sem a validação/trava/limite do núcleo. As promessas de latência do patch não são resultados medidos no PC.

Esses achados descrevem comportamento do código, sem inferir intenção do autor ou afirmar que todos os caminhos foram executados no Windows.

## Recuperação implementada

A entrega v2.8.2 contém a base auditada v2.8.0 completa, sem importar o motor externo ou acrescentar wrappers. Ao substituir as fontes completas em C:, restaura assinaturas, iniciadores, roteamento, histórico por conversa, seleção de equipe e confirmações. A recuperação não sobrescreve configuração/dados/modelos ou tenta migrar registros reais.

`interpretacao_natural.py` incorpora a parte útil de forma nativa: capacidades respondidas por função pura e reconhecimento de frases completas. A descrição usa somente funções existentes e informa dependências/autorizações necessárias, sem estatísticas privadas ou alegações de conta conectada. Negativas, citações e pedidos compostos seguem o fluxo normal; exemplos de alteração continuam como planos para confirmação.

`assistente_pc.py` melhora `/logs`: além dos eventos recentes, apresenta o detalhe da última falha com horário, redação e limites para Telegram. Detalhes de sucessos não são despejados. A autorização existente permanece antes da leitura. Uma falha de IA continua explícita, sem ser mascarada por uma apresentação do assistente.

## Verificação e limites

Baseline v2.8.0: 606 testes Python e compilação aprovados antes das alterações. Resultado final local: 621 testes Python, 59 verificações JavaScript, compilação e auditoria dos 28 módulos principais aprovados. As 15 novas regressões cobrem a frase da captura/variantes, ausência de IA/dados no descritivo, rejeição de compostos/negações, preservação de planos/assinatura, falha explícita e diagnóstico redigido/autorizado. O resultado da matriz Windows/Linux consta no PR.

Não foram lidos `.env` ou dados privados. Não houve execução do instalador anexo, pip dele, limpeza dele, Telegram real, inferência, ações Windows ou restauração de registros. O teste de fallback é uma reprodução controlada; o erro específico da captura permanece sem diagnóstico definitivo até existir seu detalhe.

[Aplicação no Windows, validação e reversão](GUIA_RECUPERACAO_PATCH.md). Para reverter, use o pacote completo auditado v2.8.0 e preserve os registros atuais; não misture backups parciais do instalador com fontes de outras versões.
