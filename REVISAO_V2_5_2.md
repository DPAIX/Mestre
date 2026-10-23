# Revisão v2.5.2 — perfil CPU explícito para Ollama

## Evidência e mudança

O catálogo respondia, mas a geração padrão do bot e um teste pelo CLI expiravam. Uma geração curta do Llama em CPU/contexto pequeno terminou com sucesso em 14,3 segundos. Isso fornece um perfil de recuperação para testar, sem identificar a causa definitiva da falha padrão.

O novo `/modelos perfil cpu`, após confirmação do proprietário, verifica a tag local, salva o `.env` selecionado pelo redirecionador e aplica o perfil no processo. Seleciona Llama na conversa, preserva o histórico e desativa sua equipe. `/modelos perfil padrao` reverte as opções, mantendo o modelo selecionado. Configurador CLI oferece `--perfil-cpu` e `--perfil-padrao` sem inferência/download.

CPU envia contexto 1024, até 128 tokens, GPU zero e `keep_alive=0`; o diagnóstico usa oito tokens. Consultas CPU validam os metadados para impedir tags cloud, inclusive aliases sem sufixo. O perfil padrão mantém o payload anterior. Configurações concorrentes por perfil/modelo são serializadas no processo para manter disco e ambiente consistentes. A assinatura das pausas considera o perfil sem invalidar pausas de outros provedores.

O diagnóstico independente v2 também preserva variáveis públicas do perfil Windows necessárias aos executáveis locais; a filtragem anterior podia impedir a consulta CLI/GPU. Falhas podem informar o código de saída numérico, sem stderr, caminhos do perfil ou segredos. O resultado “consulta indisponível” da ferramenta não diagnostica defeito da GPU.

## Arquivos

`multi_ia.py`, `configurar_ia_local.py`, `servicos_chat.py`, `assistente_pc.py`, `redirecionar_assistente.py`, `.env.exemplo`, `diagnostico_ollama.py`, exportação de fontes, identificação de versão no HTML e testes de regressão. [Guia de ativação](GUIA_PERFIL_CPU.md) e [diagnóstico](GUIA_DIAGNOSTICO_OLLAMA.md).

## Validação e limites

Testes de payload, catálogo local/cloud, gravação externa/atômica, configuração concorrente, isolamento de pausas, confirmação/autorização/expiração e reversão usam serviços simulados e arquivos temporários. A suíte completa, compilação e comportamento JavaScript são verificados antes da entrega; resultados finais constam no PR.

Não se iniciou Ollama, Telegram, ações do Windows, download ou API paga nos testes. O sucesso real conhecido é o teste CPU curto executado pelo usuário. A conversa completa com o novo perfil ainda precisa da validação manual descrita no guia. Contexto e saída reduzidos limitam conversas longas; paralelismo não garante recursos para todos os modelos. Não há retry automático, alteração de driver ou migração de dados.

## Atualização e reversão

Atualize as fontes em C: e execute `iniciar_redirecionado.bat`, preservando `.env` e dados em F:. Ative pelo comando confirmado e teste uma mensagem curta. Para reverter o perfil use `/modelos perfil padrao`; para reverter as fontes restaure v2.5.1. Detalhes e alternativa CLI no [guia](GUIA_PERFIL_CPU.md).
