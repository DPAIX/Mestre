# MeuControlePC v2.3.0 — conversas e colaboração funcional

Esta revisão implementa os três modos de colaboração pedidos: chats independentes, contribuições de chats externos e equipe de provedores por API. O documento de memória anexado foi usado como contexto histórico; seus valores pessoais e suas afirmações de funcionamento não foram copiados como configuração nem tratados como validação real.

## Entrega

- `colaboracao_chats.py`: histórico persistente isolado, conversas selecionáveis, tarefas compartilhadas, importação de propostas inertes, decisões e ZIP de contexto com fontes e hashes, sem dados operacionais ou históricos pessoais.
- `servicos_chat.py`, `equipe_ia.py`, `assistente_pc.py`: integração HTTP/Telegram, conversas contínuas opcionais, importação de documentos e equipe finita com uma chamada por provedor após confirmação. Propostas não se tornam código executado.
- `multi_ia.py`: contexto para Gemini/OpenAI/Claude, seleção de provedor, inferência Ollama real por HTTP loopback, teste explícito de conexão e correção da classificação de cota gratuita Gemini. Mensagens genéricas sobre billing não geram sozinhas um bloqueio de créditos por 24 horas.
- `configurar_ia_local.py` e scripts `.bat`: verificação do serviço/modelo, download solicitado pelo usuário, atualização atômica somente da configuração local e instalação Ollama por `winget` quando disponível. Nenhuma instalação foi executada no PC durante esta preparação.
- `rotina_ativa.py`: cadastro/edição/remoção de atividades, movimentação Kanban e lembretes opt-in com deduplicação, confirmação de entrega, limite de tentativas e fuso brasileiro.
- `painel_rotina.html`: central com chats, histórico, tarefas, importação, decisões, exportação, equipe e teste de conexões. Renderização usa texto, sem executar conteúdo importado.
- Testes de persistência, autorização, isolamento, roteamento, cota, configuração, lembretes e fluxo completo HTTP. O CI permanece em Linux/Windows e Python 3.11/3.12/3.14, com base de fusos instalada.

## Validação e limites

Baseline: 115 testes passaram antes desta rodada. Resultado final local: **174 testes passaram em cada versão Python 3.11, 3.12 e 3.14**, sem ResourceWarning. Os **16 testes JavaScript** também passaram. Compilação e verificação de whitespace passaram. A suíte integrada verifica operações de arquivos em diretórios temporários e simula serviços externos. Um servidor HTTP local simula o protocolo de inferência Ollama para testar o caminho completo painel → roteador → histórico/propostas. Esse teste não é um teste de um modelo instalado no seu PC.

A conexão real de Telegram, modelos de nuvem, saldo das contas, Google OAuth, execução das hotkeys/RoboTask e instalação do Ollama dependem do computador e das respectivas contas. Esses serviços não foram acessados com suas credenciais. A leitura Google Calendar opcional existente foi preservada; escrita de eventos, leitura automática dos chats web e execução arbitrária de scripts/macros não são anunciadas como funcionalidades desta entrega.

## Instalar e usar

Extraia em pasta nova, execute `instalar_windows.bat` e, para não depender de créditos de API, `instalar_ia_local.bat`. Migre os dados conforme `LEIA-ME.md` antes da primeira inicialização. Encerre o bot antigo e inicie a nova pasta. Comece com `/chat novo Desenvolvimento`, `/chat provedor Ollama` e `/ia sua pergunta`; use `/contexto` para os chats web ou `/equipe objetivo` para os provedores por API. Detalhes completos em [GUIA_MULTIPLOS_CHATS.md](GUIA_MULTIPLOS_CHATS.md).

As chaves e os dados existentes são preservados. No GitHub, arquivos de `dados/` já versionados não foram editados por esta rodada; o pacote de distribuição contém somente fontes e exemplos genéricos. Novos arquivos operacionais continuam em `dados/`, fora do ZIP de distribuição.

## Reversão

Encerre o assistente e volte à pasta anterior. Preserve `.env`, `dados/`, backups e tarefas `.tsk`; os dados antigos da rotina/finanças mantêm o mesmo formato. Os novos arquivos de colaboração e lembretes podem ficar guardados para reutilização. No GitHub, reverta o commit desta rodada sem apagar dados pessoais. A instalação do modelo local é opcional e independente do código anterior.
