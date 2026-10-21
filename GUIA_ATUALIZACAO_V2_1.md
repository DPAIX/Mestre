# MeuControlePC v2.1 — Atualização sem apagar dados

## O que foi identificado

Nas capturas, o painel local em `127.0.0.1:8765` carrega o histórico acadêmico e a conta do RU; o bot responde aos menus e exporta logs; o RoboTask lista 56 tarefas catalogadas. Os resultados de `Auto-Análise & Evolução` anteriores só contavam falhas e listavam ações, sem diagnóstico aprofundado ou execução controlada de melhorias. A exportação de 21/10/2026 continha `gestao_vida.json`, `minhas_macros.json`, `base_auto_aprendizado.json`, `robotask_conhecimento.json` e `log_acoes_e_erros.json`. Não é necessário importar esses arquivos se já estão na pasta `dados` do Windows.

## Instalar atualização incremental (preferível)

1. Pare o bot **fechando o console** em execução. Interrompa também a instância iniciada com `iniciar_somente_painel.bat`, se houver.
2. Faça uma cópia da pasta `F:\MeuControlePC_v2` em outro local como medida de segurança.
3. Extraia o ZIP **`Atualizacao_MeuControlePC_v2_1.zip`** sobre **`F:\MeuControlePC_v2`**. Substitua os arquivos do programa quando perguntado. Atenção: o ZIP incremental tem os arquivos na raiz, não crie outra subpasta.
4. **Não apague nem substitua** a pasta `dados`, o arquivo `.env` e a pasta `.venv`. O ZIP incremental não contém esses itens.
5. Abra seu `.env` atual e adicione, se desejar:

```ini
AUTOANALISE_INTERVALO_MIN=360
REINICIO_WINDOWS_HABILITADO=0
REINICIO_WINDOWS_ATRASO_SEG=120
```

6. Execute `iniciar_windows.bat` normalmente. Se quiser só painel, use `iniciar_somente_painel.bat`. Nenhuma instalação de pacotes novos é necessária em relação à v2.
7. Execute os testes na pasta da aplicação: `.venv\Scripts\python.exe -m unittest discover -s testes -v`.

O ZIP completo serve para uma instalação em pasta nova; **não substitua uma instalação com dados e `.env` em uso por extração cega**.

## Autoanálise e melhorias

No Telegram: menu **🧠 Auto-Análise & Evolução**, `/evoluir` ou `/autoanalise` para verificar sintaxe dos módulos, integridade dos JSON, espaço em disco e falhas recentes. O relatório é salvo como `dados\ultima_autoanalise.json`. Após iniciar, o sistema executa apenas a análise a cada 360 minutos (configurável de 15 minutos a 7 dias). Pode ser solicitado a qualquer momento.

Para executar melhorias pré-definidas, use `/melhorar` e confirme no botão; no painel local, abra a aba **🧠 Autoanálise & reinício**, clique em **Aplicar melhorias seguras** e confirme. O procedimento cria um ZIP de backup em `dados\backups`, exporta CSV/Jupyter e atualiza o catálogo de tarefas RoboTask sem executá-las. O resultado fica em `dados\ultima_melhoria.json`. **Não há edição autônoma de código-fonte nem instalação automática de dependências, modelos ou extensões.**

## Reiniciar o assistente

Use `/reiniciar` no Telegram (confirmação), o botão **🔄 Reiniciar Assistente** do menu ou **Reiniciar MeuControlePC** no painel. Isso reinicia o processo Python que fornece Telegram e painel; não reinicia o Windows. Um processo auxiliar espera o antigo encerrar antes de iniciar uma nova instância, evitando conflito na porta 8765.

## Reiniciar o Windows inteiro (opcional, desabilitado)

> **Risco de perda de trabalho não salvo.** O comando Windows `shutdown.exe /r /t 120` agenda a reinicialização, e a Microsoft informa que, quando `/t` é maior que zero, o fechamento forçado (`/f`) fica implícito. **Salve tudo antes de aceitar.**

1. Para permitir essa função, altere conscientemente no `.env`: `REINICIO_WINDOWS_HABILITADO=1` e reinicie o assistente.
2. Telegram: `/reiniciar_windows` → botão de confirmação → digite `/confirmar_windows CODIGO_RECEBIDO` dentro de 90 segundos. Painel: botão **Reiniciar Windows** → primeira confirmação → digite `REINICIAR WINDOWS`.
3. A reinicialização só será agendada após essas confirmações. Há no mínimo 60 segundos de contagem; o padrão recomendado é 120 segundos. Para cancelar durante a contagem, use `/cancelar_reinicio` no Telegram ou **Cancelar reinício agendado** no painel; isso aciona `shutdown.exe /a`.
4. Se deseja que o MeuControlePC volte a iniciar ao entrar na sua sessão, execute manualmente `habilitar_inicio_com_windows.bat` e confirme. Para desfazer, `desabilitar_inicio_com_windows.bat`. É inicialização **após logon**, não serviço em segundo plano antes do login.

**Nunca publique seu `.env`, as chaves de API, o token do Telegram ou capturas contendo essas chaves. Revogue credenciais antigas já expostas.** Os recursos dependentes de APIs externas e o reinício real do Windows precisam ser validados no seu computador; testes automatizados não executam reboot nem verificam saldos de API.

Documentação de referência: [Microsoft — shutdown](https://learn.microsoft.com/pt-br/windows-server/administration/windows-commands/shutdown).
