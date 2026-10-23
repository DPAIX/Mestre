# Revisão v2.8.0 — dependências, manutenção e velocidade

## Problemas corrigidos

O assistente aguardava uma medição bloqueante de CPU de 100 ms por consulta de status e repetia leituras de vida/RoboTask no painel. Cumprimentos e testes simples aguardavam toda a equipe de modelos. No CPU, o catálogo podia iniciar pelo 27B, cujo tamanho público excede a RAM total reportada pelo usuário, levando a tentativas demoradas. Também faltava um fluxo único de atualização de bibliotecas e limpeza de arquivos gerados para uma instalação pronta.

## Implementação

- `nucleo.py`: CPU por delta de contadores agregados, cache de meio segundo compartilhado entre threads e primeira amostra N/D. Tratamento de falhas/contadores inválidos sem comprometer os dados. `assistente_pc.py` reutiliza snapshots de vida/RoboTask por requisição, sem guardar estado mutável em cache.
- `interpretacao_natural.py` e Telegram/painel: respostas sociais completas locais, sem consultar IA ou afirmar conectividade de modelos. Matches exatos evitam descartar tarefas compostas, citações ou comandos. O histórico da conversa é mantido, e autorização/confirmacão permanecem nas interfaces.
- `configurar_ia_local.py`: projeta tamanho público opcional do catálogo, sem hosts remotos ou prompts. `multi_ia.py` tem cache CPU de cinco segundos por configuração, cópias e invalidação em falhas/configuração, mantendo consultas explícitas frescas. Ordenação em `conversa_equipe.py` prioriza menores, mantendo seleção e ordem do relatório.
- A cooperação CPU adia antes da geração pesos que excedam RAM total menos 512 MiB. A categoria `recursos` explica a estimativa; desconhecidos continuam no caminho normal. Não aplica o guard ao individual/padrão nem reduz o consenso de ações. Um modelo adiado não conta como sucesso.
- `manutencao_assistente.py` e `atualizar_assistente.bat`: usam helpers de `preparar_inicio_automatico.py` para instalar requisitos da aplicação/voz/Google, executar `pip check`, reaproveitar pesos, limpar somente bytecode gerado e iniciar o bot. Trava de instância protege manutenção e primeira ativação; Startup é preservado na manutenção. Etapas são finitas e erros não exibem saída bruta do pip.
- Limpador limitado à raiz completa identificada do assistente e `testes`, recusando links/reparse points e preservando itens desconhecidos. Não busca documentos pessoais ou arquivos por tamanho/idade. Caches são regeneráveis; fontes, testes, documentação, ambiente, configuração, dados, pesos e backups não são lixo.

## Instalação e verificação

Baseline v2.7.1: 559 testes Python e compilação aprovados antes das mudanças. Resultado final local com as dependências reais instaladas: 606 testes Python, 59 verificações JavaScript, compilação e auditoria estática dos 28 módulos principais aprovados. As 47 novas regressões cobrem mensagens rápidas/compostas, snapshot HTTP, amostragem Windows/Linux, cache/ordenação/orçamento CPU, instalação com bot ativo, dependências, preservação e limites da limpeza. O resultado da matriz Windows/Linux consta no PR.

As dependências reais de `requirements.txt`, voz local e Google foram instaladas em `/workspace/work/validacao_voz_local_venv`, fora das fontes. `pip check` retornou sem conflitos; imports de Telegram, Gemini, Pillow, psutil, faster-whisper e bibliotecas Google passaram. PyAutoGUI está instalado, mas sua GUI precisa do Windows/ambiente gráfico. Não se declara que uma instalação remota foi executada no PC do usuário.

Após a validação, a limpeza segura neste ambiente removeu 195 arquivos de bytecode em dois caches, liberando 4.135.229 bytes. Nenhum item precisou de exclusão forçada. Esse número é da cópia de desenvolvimento; a manutenção no Windows mostrará o resultado próprio do PC.

Uma medição com cinco resumos, dados fictícios e psutil real neste ambiente passou de aproximadamente 0,502 s para 0,000383 s após remover a espera. Isso mede apenas a consulta de status; não é benchmark do Windows ou da geração de texto. As chamadas aos modelos nos testes são simuladas. Peso em disco/RAM é heurística, não prova da memória de inferência. Não houve inferência real, teste de credenciais ou ações Windows.

## Atualização, limites e reversão

Encerre o bot, copie o conteúdo interno do ZIP para a raiz em C: e abra `atualizar_assistente.bat`. Configuração/dados/pesos em F: e início automático pronto são reaproveitados. Bibliotecas ausentes precisam de rede; a agenda requer OAuth já autorizado. Confira as respostas locais e o relatório de participação, inclusive eventual adiamento do 27B.

Para reverter, encerre o bot e restaure todas as fontes v2.7.1, preservando configuração, dados e modelos, então abra o iniciador existente. Caches removidos não exigem restauração. A instalação de dependências é feita no ambiente virtual existente e pode atualizar versões dentro dos limites declarados; o resultado é conferido com pip check. [Guia de manutenção, limpeza, uso e recuperação](GUIA_MANUTENCAO.md).
