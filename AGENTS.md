# Orientações para o Codex — MeuControlePC v2.2.1

## Contexto e escopo
- Projeto Python para **Windows**: bot Telegram, painel HTTP local, integração RoboTask, rotina, finanças e conectores Multi-IA. Parte do núcleo e a suíte de testes também executam em Linux.
- Esta pasta é o **código-fonte** e contém somente dados iniciais fictícios. Dados reais ficam em `dados/` (ignorado no Git) e segredos no `.env` (também ignorado).
- Principais módulos: `assistente_pc.py` (Telegram), `nucleo.py` (persistência e logs), `multi_ia.py` (provedores), `automacao_pc.py` (ações locais), `evolucao_segura.py` (autoanálise e backups), `reinicio_seguro.py` (reinícios), `painel_rotina.html` (UI), `ponte_robotask.py` e `testes/`.

## Antes de alterar
1. Leia `README_CODEX.md`, `LEIA-ME.md` e os testes afetados.
2. Rode `python -m unittest discover -s testes -v` e `python -m compileall -q .`. Se algum teste falhar antes das alterações, registre o resultado.
3. Reproduza o bug e identifique a causa; se depender de Windows, Telegram, RoboTask ou API externa, separe testes simulados de validação real.

## Segurança e compatibilidade (obrigatório)
- NUNCA copie, divulgue, reintroduza, registre nem comite chaves de API ou tokens de bot. Não leia `.env`/`dados/` para respostas, PRs ou relatórios. Não envie históricos pessoais ao repositório.
- Não execute comandos perigosos, macros externas, reinício/desligamento do Windows, hotkeys ou acesso remoto durante testes automáticos.
- **Não adicionar opção de desligar o PC.** Preserve a reinicialização do *assistente*; reinício do Windows permanece separado, desativado por padrão e com dupla confirmação.
- Não aceite código retornado por LLM como patch autoexecutável. Mudanças no próprio código devem ocorrer por PR, testes, revisão humana, backup e reversão.
- Toda ação Windows/Telegram deve validar ID autorizado; painel apenas em loopback, sem exposição pública nem permissões anônimas de escrita.
- Nunca trate API configurada como API funcionando. Diferencie 404 (rota/modelo), 429 (cota), falta de créditos, erro de autenticação e falha transitória; evite loops e custos automáticos.
- Preserve os esquemas JSON legados, a migração não destrutiva, os botões/rotas do Telegram e as macros existentes. Não altere dados sem plano de migração.

## Estilo e entrega
- Prefira alterações pequenas, testes de regressão e nomes claros em português; evite dependências adicionais sem necessidade.
- Inclua em cada resposta ou PR: causa, arquivos alterados, testes e seus resultados, riscos, passos para validar no Windows, procedimento de rollback.
- Modificações do painel HTML devem validar JavaScript e segurança de chamadas HTTP.
- O Codex na nuvem não tem acesso ao RoboTask instalado no computador do usuário. Não declare integração validada sem teste real no PC.
