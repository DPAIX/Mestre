> **v2.2.1 (21/10/2026):** correção de `NameError` no menu Multi-IA registrada em `exportacao_20261021_134355.zip`; auditoria estática de nomes não definidos, falhas específicas exibidas na autoanálise, cobertura ampliada do bloqueio de desligamento e 46 testes locais aprovados. Referência: `GUIA_CORRECAO_V2_2_1.md`.

# Atualização v2.2

Veja o arquivo `GUIA_ATUALIZACAO_V2_2.md` para correções, limitações externas e passos de instalação.

# Relatório técnico de revisão — MeuControlePC v2

## Diagnóstico do sistema legado

Fontes examinadas: `assistente_pc.py`, `ponte_robotask.py`, `gestao_vida.json`, `robotask_conhecimento.json`, `base_auto_aprendizado.json`, logs de ações/telemetria e capturas de tela enviados no pedido.

1. **Comandos locais confundidos com pesquisa.** A pergunta «arrume» foi roteada à Exa e respondida como vocábulo. Correção: classificador de comandos locais antes do roteador de IA; Exa exige pesquisa explícita.
2. **Cascata de modelos indisponíveis.** Repetições de 404 de versões antigas do Gemini eram feitas durante falhas. Correção: modelo parametrizado, sem lista rígida de modelos antigos, e suspensão por erro em vez de retentativas repetidas.
3. **OpenAI/Claude sem saldo.** Logs registram falhas de créditos. Correção: identificar `insufficient_quota`/crédito insuficiente separadamente de limite temporário 429 e não afirmar disponibilidade sem consulta.
4. **RoboTask Unicode.** Erro `unicodeescape` no processamento de `ponte_robotask.py`. Correção: leitura com codificações alternativas de `.tsk`, sem execução automática nem transformação dinâmica de scripts.
5. **Auto-reparo com falso sucesso.** Execução concluída era confundida com correção validada. Correção: diagnóstico seguro com relatório verificável, sem alterar código e sem apagar arquivos de usuário.
6. **Credenciais expostas no código e JSON.** Correção: novos arquivos não contêm tokens; credenciais por variáveis do ambiente/.env, saída de log/exportação redigida. **Revogação das chaves antigas é obrigatória**, pois redigir o novo código não invalida chaves já expostas.
7. **Autorreprogramação sem aprovação.** Código anterior reescrevia `assistente_pc.py` a partir de respostas de IA. Correção: rotinas analíticas com sugestões; nenhuma substituição de código gerada automaticamente.
8. **Painel desatualizado e chamadas GET modificadoras.** Correção: painel dinâmico vinculado ao mesmo núcleo, GET somente leitura e POST com token/origem verificados.
9. **Persistência e integridade.** Arquivos JSON são gravados atomicamente, importados sem sobrescrever a versão anterior, e operações de usuário geram eventos de auditoria.

## Limitações e validação

A suíte inclui 14 testes automatizados para funcionalidades sem acesso remoto/credenciais, incluindo um servidor HTTP local real. Esses testes passaram no ambiente de preparação. **Não houve teste no Windows do usuário, autenticação real no Telegram nem chamadas autenticadas de produção às APIs.** RoboTask remoto, Google OAuth e modelos precisam ser validados após instalar, autorizar e configurar novas chaves.

Os dados históricos incluídos em `dados_iniciais/` são instantâneos do material fornecido. Não devem ser confundidos com dados ou saldo atualizados automaticamente. Os arquivos legados originais permanecem necessários para uma migração integral do estado mais recente.

## Referências técnicas externas

- [OpenAI — Solução de problemas de rate limits e erros 429](https://help.openai.com/pt-br/articles/5955604-troubleshooting-api-rate-limits-and-429-errors)
- [Google — Documentação do método models.generateContent](https://ai.google.dev/api/generate-content)
- [Google Gen AI SDK — Listar modelos](https://googleapis.github.io/python-genai/)
- [Anthropic — Autenticação da API](https://platform.claude.com/docs/en/manage-claude/authentication)

## Revisão do instalador após captura Screenshot_94

O instalador da revisão inicial falhou no PC Windows ao instalar o pacote `pyautogui`, com `Permission denied` dentro de `AppData\Local\pip\cache\wheels`. A mensagem indica falha de acesso ao cache, **não demonstra erro no código do bot**. A revisão substituiu a instalação com cache por `pip install --no-cache-dir --prefer-binary`, acrescentou recuperação do `pip` com `ensurepip` quando necessário e uma rotina de instalação/reparo que preserva `.env` e `dados/`. A etapa de testes locais permite diferenciar instalação de dependências e validação do núcleo. O instalador `.bat` ainda precisa ser executado em um Windows real para confirmar a correção.

- Documentação oficial do pip: https://pip.pypa.io/en/stable/topics/caching/

### Revisão 3 — Telegram token/owner ID

Adicionados `configurar_telegram.py` e `.bat` para configuração local interativa, validação antecipada do token e de IDs, mensagens de erro amigáveis, fluxo de reparo na inicialização e testes de persistência. A configuração preserva o restante de `.env` e não grava tokens em logs. Não realiza teste de rede nem cria credenciais.

## Alterações v2.1 (21/10/2026)

- Inclusão de motor `evolucao_segura.py`: auditoria local da integridade dos arquivos do projeto, registros e espaço livre, armazenamento do diagnóstico e agendamento somente de leitura.
- Execução confirmada de melhorias pré-definidas, com backup antes de atualizar CSV, Jupyter e catálogo RoboTask; não modifica código nem executa automações arbitrárias.
- Comandos Telegram `/melhorar`, `/evoluir`, `/reiniciar`, `/reiniciar_windows`, `/confirmar_windows` e `/cancelar_reinicio`; confirmação em duas etapas para reboot do Windows.
- Reinício separado do assistente por `reiniciar_assistente.py`, aguardando o processo anterior encerrar antes de reabrir painel/Telegram.
- Reinicialização Windows opcional via `shutdown /r /t <segundos>` (mínimo 60 s). ATENÇÃO: /t positivo implica /f no Windows, com risco de perda de dados não salvos; cancelamento por `/a`. Padrão desabilitado no `.env`.
- Painel: nova aba para diagnóstico, melhorias permitidas e reinicializações com confirmação explícita.
- Scripts opcionais para iniciar após logon e desabilitar essa funcionalidade.
- Testes de diagnóstico, persistência, whitelist de melhorias, bloqueio do reboot e rotas HTTP.

Os testes executados em ambiente isolado não comprovam que Windows reboot, RoboTask e APIs externas funcionam no computador do usuário.
