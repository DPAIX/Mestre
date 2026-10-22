# MeuControlePC v2.5.0 — equipe paralela e auditoria de estabilidade

Mensagens que precisam de IA podem consultar todos os modelos registrados no Ollama em paralelo e apresentar a contribuição identificada de cada um. O arquivo `assistente_pc.py` enviado pelo usuário também foi revisado integralmente; falhas reproduzidas de HTTP, estados de Pomodoro, relatórios, voz e confirmação foram corrigidas.

## Causa e comportamento

Selecionar uma tag por chat, como na v2.4.1, enviava somente uma consulta. Agora `/chat equipe on` captura o catálogo do Ollama e salva até oito tags naquela conversa. Quatro workers podem iniciar consultas simultâneas às quatro tags do catálogo informado. O modo persiste e pode ser desligado ou atualizado explicitamente. Não há download, geração na ativação, fallback para APIs externas nem repetição automática. A configuração do serviço Ollama não é alterada.

As respostas permanecem separadas e identificadas, com falhas parciais visíveis. Um plano de ação só é preparado quando todos os modelos responderem com a mesma ação/campos validados; as confirmações existentes continuam obrigatórias para alterações. Leituras locais reconhecidas continuam independentes da IA.

No arquivo enviado, as 982 linhas tinham sintaxe válida. Os problemas eram operacionais: leitura HTTP ilimitada, aceitação de corpo curto após EOF, JSON ambíguo, marcador de Pomodoro sem limpeza após erro, rede dentro de trava, fallbacks de relatório avaliados indevidamente e cliente Gemini sem fechamento na falha. A [auditoria integral](AUDITORIA_ASSISTENTE_V2_5_0.md) explica as correções e cobre os blocos do original. `serve_forever` e polling são laços deliberados de serviço, não busy loops.

## Arquivos alterados

- `conversa_equipe.py`: fan-out limitado, cópias de histórico, contribuições, falhas por modelo, consenso e redação. Uma equipe ativa por processo e uma chamada por tag.
- `colaboracao_chats.py`, `servicos_chat.py`: campos opcionais por conversa, ativação/desativação, compatibilidade com chats antigos e retorno ao modo individual ao selecionar outro modelo/provedor.
- `assistente_pc.py`: comando Telegram e correções de estabilidade; servidor loopback com 16 conexões e prazo de leitura total de 10 segundos; validação JSON antes da execução; preservação da idempotência HTTP.
- `nucleo.py`: validação das estruturas usadas pelo assistente, sem reparo destrutivo dos JSONs.
- `painel_rotina.html`: controles da equipe por conversa, tags via textContent e chamadas pelo fluxo idempotente existente.
- `evolucao_segura.py`, exportação de contexto, guias e testes: inclusão do módulo e documentação nova na lista de fontes permitidas, sem exportar configuração ou histórico.

## Verificação

Baseline: 322 testes Python e compilação aprovados antes das alterações. A entrega contém 364 testes Python e 56 verificações comportamentais JavaScript. A suíte completa passou localmente em Python 3.11 e 3.12, assim como as 56 verificações JavaScript. A matriz CI cobre Windows/Linux com Python 3.11, 3.12 e 3.14; os resultados da matriz ficam no PR.

Foram usados sockets loopback temporários, fixtures JSON e mocks de Telegram/Gemini/Ollama. Barrier comprova início concorrente das quatro consultas; há regressões para falhas parciais/totais, liberação de travas, histórico/contextos isolados, consenso sem execução, autorização, replay HTTP, corpo truncado, conexões incompletas, números não finitos, limpeza de Pomodoro, fechamento do cliente de voz e ack expirado.

Compilação de fontes, sintaxe JavaScript, 84 IDs únicos/72 referências do painel e análise estática de 22 módulos sem nomes globais indefinidos foram verificados. ZIP validado por leitura e comparação byte a byte com as fontes. Nenhuma ação real do Windows, consulta a modelos, OAuth ou API paga foi executada.

## Instalação, riscos e reversão

Atualize o pacote completo em `C:\Users\Mestre\Documents\GitHub\Mestre`, incluindo o módulo novo; preserve `.env` e dados em `F:\MeuControlePC_v2`. Encerre o assistente antigo e inicie por `iniciar_redirecionado.bat`. O redirecionamento existente permanece. Confira v2.5.0 em `/start`, envie `/modelos ollama`, `/chat equipe on` e uma pergunta. O [guia da equipe](GUIA_EQUIPE_PARALELA.md) detalha a validação no Windows.

Enviar consultas em paralelo não garante inferência simultânea no servidor. A GTX 1660 de 6 GB pode exigir RAM/CPU e fila, especialmente com o modelo de 27B. O serviço pode retornar falta de memória ou timeout. Tags cloud usam internet/conta/cota se incluídas explicitamente pela ativação. Para reduzir carga, desative a equipe e selecione um modelo individual. O Manus web continua no fluxo de exportação/importação de contexto.

Nenhum arquivo de dados foi migrado ou sobrescrito pela auditoria. Estrutura inválida exige revisão manual do arquivo original. Google Calendar continua somente leitura e o reinício do Windows permanece separado, desativado por padrão e com dupla confirmação. O cache de idempotência do painel continua na memória do processo e sujeito aos limites/expiração da v2.4.1.

Para reverter, encerre a v2.5.0 e restaure todas as fontes da v2.4.1, preservando uma cópia dos dados externos. Os campos novos de equipe são opcionais. O PR permanece em revisão, sem merge. O pacote não inclui segredos ou dados de uso; blobs de dados já rastreados no GitHub foram preservados sem leitura de conteúdo.
