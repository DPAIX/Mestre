# MeuControlePC v2.2.3 — diagnóstico e instalação

Esta revisão atende aos problemas mostrados nas capturas enviadas após a v2.2.2. As correções anteriores permanecem disponíveis no [relatório da v2.2.2](REVISAO_V2_2_2.md).

## O que as capturas mostram

A instalação terminou com `Ran 87 tests` e `OK`. As mensagens de JSON inválido vieram de testes que criam arquivos temporários corrompidos para verificar a proteção dos dados. Elas não comprovam corrupção dos arquivos da instalação.

Os `ResourceWarning` eram falhas reais de limpeza dos próprios testes: cinco exceções `HTTPError` não tinham sua resposta HTTP fechada. O Python 3.14 passou a tornar isso visível através do wrapper interno de `tempfile`. O problema foi reproduzido em Python 3.14.8 Linux, sem depender do Windows.

O Gemini respondeu HTTP 503 com alta demanda. Essa é uma falha temporária do serviço registrada naquela consulta. Os estados de falta de créditos exibidos para OpenAI e Claude vêm de evidências desses próprios provedores; não explicam a sobrecarga do Gemini e não comprovam o saldo atual das contas.

As melhorias locais concluíram backup, CSV/Notebook e catálogo. Repetir a operação com entradas idênticas pode corretamente retornar “já atualizado”. Essa operação não instala código novo nem modifica a disponibilidade das APIs.

## O que mudou

| Arquivos | Correção |
| --- | --- |
| `evolucao_segura.py`, `testes/test_diagnostico_provedores.py` | Diagnóstico separa problemas locais de avisos externos. Ocorrências recentes são contagens de logs, sem serem chamadas de incidentes ativos. Uma falha antiga não gera orientação de recarga para outro provedor. O fim de uma pausa não é tratado como recuperação. Uma consulta válida posterior supera a evidência antiga. |
| `multi_ia.py`, `testes/test_multi_ia_regressoes.py` | Falha geral identifica causas e pausas de todos os provedores de resposta, inclusive os que já estavam bloqueados. HTTP 503 orienta aguardar; falta de crédito tem orientação própria. Exa continua separado em `/pesquisar`. Snapshot local registra códigos, momentos das falhas e sucesso da sessão, sem chaves, prompts ou rede. |
| `assistente_pc.py`, `testes/test_relatorios.py` | Autoanálise do Telegram, HTTP e agendador usa o snapshot. Mensagens distinguem o programa dos provedores e os arquivos locais da conectividade. O menu Multi-IA preserva a evidência de falha mesmo quando a pausa termina. |
| `painel_rotina.html`, `testes/test_painel_frontend.js` | Painel mostra estado local, evidências e orientações externas separadas. Relatórios legados pedem nova análise e não repetem sugestões antigas de recarga. A ação local chama-se “Backup e arquivos locais”. |
| `testes/test_painel.py` | As cinco respostas `HTTPError` agora são fechadas. |
| `testes/test_evolucao_reinicio.py`, `testes/test_nucleo_regressoes.py`, `testes/test_painel_regressoes.py` | Logs esperados dos JSONs de teste são capturados e verificados com `assertLogs`; o logger de produção permanece intacto. |
| `.github/workflows/testes.yml`, `README.md`, `LEIA-ME.md` | Matriz de CI inclui Python 3.14 em Linux e Windows, além de 3.11 e 3.12. Documentação atualizada. |

Não foram adicionadas dependências. Não houve uso de credenciais, consultas reais, execução de tarefas RoboTask, hotkeys ou reinícios. Arquivos reais de `.env`, `dados/` e tarefas `.tsk` não foram alterados. O pacote de fontes contém somente exemplos genéricos.

## Validação

- Baseline desta rodada: **87 testes passaram**.
- **115 testes passaram em cada versão local Python 3.11, 3.12 e 3.14** no Linux, com `-W always::ResourceWarning`.
- Os três logs finais não contêm `ResourceWarning` nem mensagens de erro dos JSONs temporários.
- **13 testes JavaScript passaram**, também incluídos pelo wrapper na suíte Python.
- Compilação Python, sintaxe JavaScript e `git diff --check` passaram.
- Os resultados de CI em Linux e Windows constam nos checks da proposta no GitHub. CI usa somente dados temporários e serviços simulados.

## Atualizar no Windows

1. Extraia o ZIP da v2.2.3 em uma pasta nova. Mantenha a instalação anterior para reversão.
2. Execute `instalar_windows.bat`. A suíte deverá terminar com `Ran 115 tests` e `OK`. Node é opcional para uso normal; se estiver ausente, o teste de JavaScript será explicitamente ignorado.
3. Para reaproveitar dados, siga a migração não destrutiva descrita no `LEIA-ME.md` antes da primeira inicialização. Configure o `.env` localmente e preserve os valores escolhidos para seus modelos.
4. Encerre o processo do bot antigo e inicie a nova pasta com `iniciar_windows.bat`. Instalar dependências ou aplicar backup no Telegram não substitui o processo que já estava em execução.
5. Abra **Multi-IA** ou use `/modelos`; confira a última evidência de cada provedor. Execute `/autoanalise` para gerar um relatório com o formato novo.
6. Para verificar o Gemini novamente, aguarde a pausa indicada e envie uma nova consulta explícita `/ia`. Isso pode consumir créditos e é o que fornece uma nova evidência de resposta ou falha. Para OpenAI/Claude, confira a situação na plataforma antes de usar `/reativar_ias`. A revisão não executa essas consultas automaticamente.
7. “Backup e arquivos locais” deve informar somente suas operações locais. Um 503 não deve virar instrução de corrigir o Windows ou recarregar outro provedor.

Não é necessário reiniciar o Windows para instalar esta revisão. A disponibilidade real do Gemini, os créditos de cada conta e a integração RoboTask continuam dependendo do computador e dos serviços externos.

## Reversão

A proposta permanece em branch separada. Antes da integração, basta continuar na instalação anterior. Depois de instalar, encerre o bot novo e execute a pasta anterior, preservando `.env`, `dados/`, `.tsk` e seus backups. No GitHub, reverta o commit desta rodada para voltar à v2.2.2. Os metadados adicionais de estado das APIs são opcionais e compatíveis com a leitura anterior; não exigem conversão de dados.
