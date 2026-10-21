# MeuControlePC v2.2.1 — correção do menu Multi-IA e da auditoria

## Diagnóstico sustentado pelo ZIP das 13:43:55

No último evento em `log_acoes_e_erros.json`, às 13:43:50, há `comando / falha` com detalhe `name 'chat' is not defined`. Em `assistente_pc.py`, a função `menu_secundario(chat_id, ...)` enviava `BOT.send_message(chat, mostrar_ias())` na opção Multi-IA, embora `chat` não estivesse definida nesse escopo.

## Corrigido

- Rota do botão **Multi-IA, Exa & Logs** agora utiliza `chat_id`.
- Autoanálise inspeciona, sem executar, referências globais não definidas nos módulos-fonte, evitando que apenas a sintaxe seja considerada suficiente.
- Falhas recentes mostram também a ação e o detalhe relevante (com filtragem de credenciais), em vez de exibir apenas uma contagem.
- Variantes como **“desligar meu computador”** também são bloqueadas pelo interpretador. **Não há opção de desligamento remoto.**
- A versão aparece como **v2.2.1** no painel e no menu do Telegram.
- A aplicação controlada de melhorias, o backup idempotente, o bloqueio de APIs sem crédito e a confirmação de reinício do Windows permanecem como na v2.2.

## Como instalar sem perder seus dados

1. Feche a janela do bot e do painel local. Não basta fechar a aba do navegador: encerre `iniciar_windows.bat`.
2. Faça, se possível, uma cópia da pasta inteira `F:\MeuControlePC_v2` (incluindo `.env` e `dados`) em local privado.
3. Extraia **Atualizacao_MeuControlePC_v2_2_1.zip** diretamente em `F:\MeuControlePC_v2`, mantendo as pastas. Substitua somente os arquivos do pacote de atualização, se o Windows perguntar.
4. Execute `aplicar_atualizacao_v2_2_1.bat`. O atualizador salva versões antigas do código em `backups_codigo`, testa e reverte se necessário.
5. Inicie com `iniciar_windows.bat`, teste o botão **Multi-IA, Exa & Logs** e depois **Auto-Análise & Evolução**.

O instalador **não copia nem altera** `.env`, `.venv` ou `dados/`. Não envia chaves para nenhuma API. A verificação local de código é uma ferramenta de apoio: ela **não substitui testes reais das integrações com Telegram, RoboTask ou serviços pagos**.

## Interpretação da autoanálise

Uma falha recente pode permanecer no histórico mesmo depois de corrigida. Mensagens anteriores sobre Gemini 503, OpenAI 429 ou Claude 400 foram verificadas nos logs e dependem da disponibilidade/créditos do provedor. Nenhum código pode adicionar crédito ou garantir disponibilidade externa.

O botão **Reiniciar Windows** não equivale a desligar o computador. Ele continua desabilitado por padrão; se for habilitado no `.env`, exige duas confirmações e pode encerrar aplicativos ao reiniciar. Para reiniciar só o bot, use **Reiniciar Assistente**.

**Importante:** se você compartilhou chaves em capturas ou arquivos antigos, revogue-as nas plataformas respectivas e gere outras; nunca envie `.env` para suporte.
