# Revisão v2.10.2 — recuperar os fluxos removidos no merge

A execução de CI `40144275473` falhou nos seis ambientes após o commit `0409d3a2a5ff35c21ddc9ffe53070032fa78c65f`, que integrou `main` na branch de trabalho. A comparação de fontes identificou remoções em três módulos; os testes anteriores eram de outro commit. A base atual foi reproduzida localmente: 923 testes, seis falhas, um teste específico Windows ignorado no Linux.

## Correções

- `assistente_pc.py`: restaura `/api/resultado_acao`, com validação de host, token, origem e ID antes da consulta do resultado. Recupera o resultado de uma ação após perda da resposta sem reenviar o POST. Restaura também a orientação `/modelos padrao NOME` na ajuda.
- `painel_rotina.html`: restaura a função e o vínculo do botão de modelo Ollama padrão e a orientação usada em HTTP 404. O botão relê catálogo/estado após sucesso; falhas não são tratadas como gravações concluídas.
- `colaboracao_chats.py`: restaura componentes da exportação de contexto e a escolha individual de modelo quando uma conversa legada é reaproveitada. Preserva histórico e ID da conversa.
- `testes/test_colaboracao_chats.py`: acrescenta regressões para o reaproveitamento de conversa legada e a presença de componentes de conversa/interpretação/idempotência no ZIP de contexto. Os testes HTTP e JavaScript existentes já reproduzem as falhas da captura; não foram enfraquecidos nem removidos.
- Documentação, versão, notebook opcional e pacote completo atualizados. O novo guia explica endpoint local, chave obrigatória, modelo/combo, estado das CLI e limites dos exemplos de áudio mostrados nas capturas.

As alterações foram aplicadas sobre o merge atual. Não foi feito reset da branch, merge da PR ou mudança em `main`. Os arquivos de configuração, dados e caches já existentes na árvore remota foram preservados por SHA, sem ler seu conteúdo. O pacote de distribuição exclui `.env`, dados reais, caches e pesos.

## Validação e limites

Validação local final: 925 testes Python aprovados, com um teste específico Windows ignorado no Linux; 87 testes JavaScript aprovados; compilação e análise estática de 39 fontes sem globais indefinidos. A matriz de seis ambientes Windows/Linux com Python 3.11, 3.12 e 3.14 consta nos checks da PR. Incluem recuperação HTTP, autenticação antes do acesso ao cache, replay de imagens, botões JavaScript e exportação de contexto. Compilação e análise estática permanecem obrigatórias. Não são usadas contas reais nem executadas macros, túneis ou reinícios do Windows.

O ambiente desta sessão não tem um dispositivo Windows conectado. As capturas provam acesso ao dashboard local, mas não uma geração com cada modelo, configuração de todas as CLI ou execução de TTS/STT. A falha do túnel público não determina falha da API local. [Concluir a conexão 9Router no PC](GUIA_CONCLUIR_9ROUTER.md).

## Atualizar e reverter

Encerre bot/painel, guarde as fontes atuais e copie as fontes completas v2.10.2 em C:, preservando configuração/dados/modelos em F:. Inicie com `iniciar_redirecionado.bat`; use `retomar_configuracao.bat` somente para as escolhas ainda pendentes.

Para reverter o código, restaure as fontes do pacote v2.10.1 do commit `453e65ae9e6ac2ffb80e218a4179f30fd3b0e5bb`, preservando `.env`, dados e pesos. A versão v2.10.2 não altera DNS, hosts, proxy, Firefox, firewall, Tailscale nem contas externas.
