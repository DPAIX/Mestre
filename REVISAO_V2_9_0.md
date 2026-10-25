# Revisão v2.9.0

## Problema e resultado

A frase exata “me diga quais as suas capacidades” não estava na lista local e acionava uma equipe. O fluxo cooperativo podia aguardar o timeout inteiro de cada participante sequencialmente, mesmo após uma requisição expirar sem cancelamento confirmado. A v2.9.0 reconhece paráfrases completas localmente, apresenta a primeira contribuição provisória e limita novos envios pelo orçamento compartilhado. Não há evidência de loop infinito no serviço Ollama nem prova da causa dos timeouts reais do Windows.

Os modelos locais continuam selecionados. O 27B excedente ao orçamento de RAM permanece explicitamente adiado; não é declarado funcionando. A autorização de nuvem no perfil CPU permite incluir Gemma cloud/aliases remotos confirmados pelo catálogo sem aplicar `num_gpu=0` ao backend remoto. A ordem prioriza um local pequeno, nuvem autorizada e demais locais. Uma contribuição cloud recebida pode ser usada se outra consulta expirar; isso não garante superioridade do modelo.

## Composição e integrações

- `interpretacao_natural.py`: gramática limitada de perguntas completas, planos literais de agentes/9stack/notas e recusa desses planos quando sugeridos por LLM. Alterações continuam exigindo confirmação.
- `conversa_equipe.py`, `multi_ia.py`: orçamento, callback provisório sem planos, categoria `tempo_esgotado`, pausa por configuração, seleção e relatórios preservados. O orçamento ajusta o timeout de socket e a decisão de novos envios; não é promessa de cancelamento ou prazo absoluto.
- `integracoes_agentes.py`: catálogo de 14 aplicativos e abertura/configuração oficial pelo Ollama, com allowlist, conferência de ajuda e ambiente filho filtrado. Não são SDKs de delegação autônoma.
- `roteador_9router.py`: cliente OpenAI-compatible real, catálogo antes da ativação, endpoint loopback, JSON estrito, limites, Bearer opcional e redação. O gateway é preferido em conversas automáticas apenas quando habilitado com modelo/combo; escolhas manuais permanecem.
- `integracoes_9stack.py`: instalação isolada e operações separadas de instalação, abertura e início. Pacotes 9Router 0.5.109/9Remote 3.0.43, Node.js 22+, npm sem shell. Portas ocupadas não provocam kill. O host/túnel 9Remote exige ação remota explícita; chaves de pareamento não são capturadas. Não se afirma que a rede do produto 9Remote seja isolada em loopback.
- `configurar_9router.py`, `servicos_chat.py`: configuração atômica, segredo somente no console por entrada oculta, política automática reversível e notas como dados no prompt, preservando a mensagem atual.
- `memoria_assistente.py`: notas manuais confirmadas, isoladas por usuário/chat/tópico/conversa interna, recuperação lexical limitada, esquema/tamanho estritos, links recusados e gravação atômica. Nenhum template de terceiros foi copiado.
- `assistente_pc.py`, `painel_rotina.html`: Telegram e endpoints autenticados, cartões confirmáveis por nonce para agentes/9stack/notas, recuperação de ações e estados que distinguem configuração de disponibilidade. A equipe de propostas suporta cinco provedores e até oito participantes, com concorrência de quatro.

O início automático e o transcritor local existentes são preservados. Os novos aplicativos não passam a iniciar remotamente no logon. Os arquivos externos e credenciais dos produtos permanecem sob controle de suas interfaces. Não há alteração automática de drivers, RAM, modelos locais, macros ou arquivos do usuário.

## Verificação

Baseline v2.8.2: **621 testes Python** e compilação aprovados. Final: **802 testes Python**, **80 verificações JavaScript**, compilação e auditoria estática dos **33 módulos principais**. As 181 novas regressões Python incluem linguagem, confirmações/isolação, prazos, contribuição provisória, CPU/cloud, clientes HTTP, assinatura de configuração, instaladores simulados, memória e fluxo integrado. A matriz Windows/Linux e o hash do pacote constam no PR da entrega.

Foram consultadas fontes oficiais dos quatro projetos e contratos reais do CLI/API. Os vídeos YouTube não puderam ser transcritos nesta sessão; não se afirma que tenham sido assistidos. A arquitetura de memória é uma implementação própria inspirada na separação de memória durável e histórico curto. O instalador/voz do fullstack-agent não foi aplicado sobre este assistente.

Não foram lidos `.env`, históricos, bancos de terceiros ou dados privados. Não foram executados npm dos novos produtos, instalação em Windows, acesso remoto, login, pareamento, inferência, Telegram real ou testes de GUI. Processos/navegadores/portas/modelos dos testes são simulados, exceto servidores HTTP de fixtures em loopback. Nenhuma conta/cota é comprovada por esses resultados.

## Aplicação, limites e reversão

Use o [guia de integração](GUIA_INTEGRACOES_V2_9.md). Aplique as fontes completas em C: e execute `atualizar_assistente.bat`; preserve configuração e dados em F:. Instalação/login dos produtos adicionais dependem da execução local e das contas do usuário. A instalação por npm fixa os pacotes de topo, não todas as transitivas da primeira resolução. Um timeout não comprova encerramento de processamento remoto ou de scripts filhos.

Para reverter, encerre o bot e restaure todas as fontes v2.8.2, mantendo dados, notas e pesos. O 9Router deve ser desativado antes se quiser retirar sua seleção. Encerramento/desautorização dos produtos externos ocorre em suas interfaces; a reversão das fontes não mata processos nem restaura registros antigos.
