# Revisão v2.7.0 — voz e equipe padrão, início automático

## Resultado

O usuário pediu um transcritor padrão, uso de todos os modelos sem comandos de ativação e início automático. A voz agora usa Whisper base local em CPU/int8. Conversas padrão, inclusive legadas sem política explícita, consultam todos os modelos do catálogo Ollama em cooperação. Uma preparação inicial por duplo clique instala os componentes, prepara os pesos, registra o Startup do usuário e inicia o bot; os logons seguintes usam a instalação pronta.

## Implementação

- `transcritor_local.py` usa subprocesso com prazo total de 120 segundos, cache externo, Hub offline na inferência, decodificação limitada a três minutos/8 MB, saída limitada e limpeza de temporário. Preparação é separada e limitada; só ela pode baixar os pesos públicos. O download usa a API pública `snapshot_download`, evitando um argumento legado removido em versões recentes do Hub. Gemini permanece uma escolha explícita, sem fallback pago.
- `equipe_politica` distingue padrão automático e escolha manual. O catálogo é lido antes de cada pergunta de IA, fora da trava do JSON; antes de aplicar, o núcleo verifica se conversa/política continuam iguais. Histórico e configuração CPU são preservados. Leituras locais e menus não geram respostas de modelos. Desligar a equipe ou escolher modelo/provedor explicitamente na versão atual salva a opção manual.
- `preparar_inicio_automatico.py` e `ativar_assistente_automatico.bat` reutilizam o Python externo/do projeto, preparam requisitos/pesos e usam o redirecionador existente. A instalação não divulga o `.env`; a preparação do modelo carrega a configuração ativa e encaminha somente opções públicas necessárias ao worker. `startup_windows.py` registra atomicamente uma entrada, preservando arquivo alheio. Não há nova confirmação de autorização, pois o início automático foi solicitado explicitamente.
- `iniciar_servicos_locais.py` verifica o serviço de loopback e inicia apenas o Ollama já instalado, com uma tentativa e leituras limitadas. Reaproveita os modelos existentes, sem download/kill. `instancia_assistente.py` mantém trava de arquivo Windows/POSIX durante toda a execução; diagnóstico não adquire essa trava nem inicia serviços.
- Painel identifica equipe automática antes da primeira pergunta, com o prazo correto. A confirmação de ações e os controles de autorização permanecem. O início normal não executa pip, download de pesos, macros ou reinícios do Windows.

## Verificação

A base v2.6.0 passou com 474 testes antes das mudanças. Novas regressões cobrem padrão sem comandos, escolhas manuais, troca de conversa durante catálogo, voz sem Gemini, processo/timeout/offline/limpeza, preparação idempotente, falhas preservando arquivos, Startup, singleton entre processos e início de serviço limitado. Os resultados finais da suíte, JavaScript e matriz Windows/Linux constam no PR.

As dependências reais de voz foram instaladas em ambiente Linux isolado; assinaturas das APIs e decodificação PyAV de áudio sintético foram conferidas. O ambiente não conseguiu acessar o Hub por DNS para obter os pesos: não se declara transcrição real validada. Os testes de transcrição usam fixtures/mocks, sem áudio pessoal, API paga ou download automático de pesos nos testes. Startup/logon e microfone reais não foram exercitados.

## Ativação, limites e reversão

Copie as fontes em C:, preserve configuração/dados em F: e abra `ativar_assistente_automatico.bat` uma vez. Depois, envie texto ou áudio normalmente; o próximo logon inicia o assistente. A primeira preparação exige internet e espaço para os pesos/bibliotecas. Modelos grandes ainda podem não responder por recursos; usar todos não garante qualidade superior.

Para desativar o logon, use `desabilitar_inicio_com_windows.bat`. Para reverter as fontes, desative o Startup e restaure a v2.6.0, preservando configuração, dados e pesos. [Guia de uso, preparação e recuperação](GUIA_AUTOMATICO.md).
