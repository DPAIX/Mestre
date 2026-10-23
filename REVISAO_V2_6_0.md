# Revisão v2.6.0 — cooperação entre todos os modelos Ollama

## Problema e comportamento resultante

O Llama individual CPU respondeu, mas os quatro modelos simultâneos tinham expirado no PC. A equipe anterior apenas apresentava respostas separadas. O novo modo consulta todas as tags selecionadas, uma por vez, com papéis e contribuições anteriores limitadas, e faz no máximo uma síntese extra por um coordenador que respondeu. Falhas parciais são apresentadas e não provocam retries. Não há declaração de geração real validada para toda a equipe.

`/chat equipe on` e a ativação no painel escolhem o novo modo cooperativo. `/chat equipe paralelo` preserva a opção anterior. Chats legados sem o novo campo continuam paralelos até a escolha explícita do novo modo. Ativação lê somente catálogo, sem geração/download. Perfil CPU, histórico e isolamento por usuário/chat/tópico permanecem.

Cooperação usa contexto 4096 e saída de até 384 tokens, com descarregamento após a chamada. CPU continua solicitando GPU zero; outras chamadas individuais mantêm as opções anteriores. Consenso de todos os participantes e síntese compatível são exigidos antes de preparar uma ação; a confirmação do proprietário continua necessária. Não há execução automática de código retornado pelos modelos.

Também foi reproduzida a frase da imagem “Mostre a minha rotina da semana”: antes caía na IA e solicitava dados que já existiam. Agora ela e variantes seguras usam a leitura local. Negativas, pedidos compostos e alterações não são capturados como mera consulta. Instruções orientam o modelo a não presumir objetivos da pergunta “você me entende?”.

O áudio dependia de Gemini e recebia uma falha genérica. Foi separado em um módulo de transcrição em memória com validação de configuração/pausa antes do download, MIME e limite de 8 MB, uma tentativa e mensagens específicas. Texto transcrito passa pelo mesmo fluxo natural/confirmado do texto digitado. Não se adicionou transcrição fictícia aos modelos Ollama de texto.

## Arquivos e validação

`conversa_equipe.py`, `multi_ia.py`, `servicos_chat.py`, `colaboracao_chats.py`, `assistente_pc.py`, `interpretacao_natural.py`, `voz_assistente.py`, autoanálise, painel e testes. Os testes cobrem ordem/isolamento, todas as tentativas, síntese única, falhas parciais, consenso/divergência, kwargs CPU, autorização, persistência/compatibilidade, rotina e áudio sem execução direta. O painel mantém POST único, idempotência e consulta de recuperação, com prazo ampliado somente para conversa com equipe.

A base anterior passou com 423 testes Python antes das alterações. A compilação, a suíte final, as verificações JavaScript e a matriz Windows/Linux são conferidas antes da entrega; os resultados finais constam no PR. As verificações usam arquivos temporários, serviços simulados e sockets locais. Nenhum modelo real, Telegram, API paga ou ação do Windows foi executado nos testes.

## Limites, ativação e reversão

Mais modelos podem aumentar latência e não garantem qualidade superior. Os modelos maiores continuam exigindo memória; a sequência não resolve sua capacidade física. Contexto, resumos e saída são limitados. Voz continua dependente da conta Gemini. O perfil CPU real conhecido funcionou em Llama individual; toda a equipe precisa de teste no PC.

Atualize as fontes em C:, preserve `.env` e dados em F:, inicie pelo redirecionador e ative `/chat equipe on`. Teste um objetivo curto e acompanhe o progresso/participantes. Para voltar à conversa individual use `/chat equipe off`. Para reverter as fontes, desative a equipe e restaure a v2.5.2, preservando dados e configuração. [Guia completo](GUIA_EQUIPE_COOPERATIVA.md).
