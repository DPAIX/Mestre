# MeuControlePC v2.2.1 — Projeto para Codex

Este pacote foi organizado a partir da **versão completa v2.2.1** do MeuControlePC. Ele contém o código-fonte, documentação, testes e instruções do Codex (`AGENTS.md`). Os arquivos `dados_iniciais/` foram substituídos por **exemplos genéricos sem registros pessoais**; a pasta `dados/` real não foi incluída. Não contém `.env` com credenciais.

## Usar no Codex desktop ou CLI (Windows)
1. Descompacte a pasta do projeto (não sobrescreva sua instalação em funcionamento).
2. Abra a pasta `MeuControlePC_Codex` no Codex desktop, VS Code com Codex ou no terminal do Codex.
3. Peça: `Leia AGENTS.md, execute os testes e faça uma auditoria de segurança e estabilidade sem alterar credenciais nem dados.`
4. Use um diretório de trabalho/branch separado para testar mudanças antes de atualizar a instalação real.

## Usar no Codex Cloud (GitHub)
1. Crie um **repositório privado** no GitHub, sem inicializar README (o pacote já contém arquivos).
2. Coloque o conteúdo da pasta na raiz do repositório, com `.gitignore`, `.env.exemplo`, `AGENTS.md` e `testes/`. Não inclua `.env`, `dados/`, `token.json` ou `credentials.json`.
3. Para publicar usando Git (instalado e autenticado):

   ```powershell
   cd C:\CAMINHO\MeuControlePC_Codex
   git init
   git add .
   git status --short
   git commit -m "Importar MeuControlePC v2.2.1 para Codex"
   git branch -M main
   git remote add origin https://github.com/SEU_USUARIO/SEU_REPOSITORIO.git
   git push -u origin main
   ```

4. Abra https://chatgpt.com/codex (ou o Codex desktop), conecte o repositório GitHub ao **ambiente Codex Cloud** e publique o ambiente seguindo as instruções do produto.
5. Sem Windows/RoboTask, use a nuvem para análise, documentação e testes unitários. Valide ações de GUI e hotkeys no seu PC, sob supervisão.

## Testes sem segredos

```powershell
python -m unittest discover -s testes -v
python -m compileall -q .
```

Opcional: `python -m pip install -r requirements.txt` no ambiente Windows, para testar a interface. O CI executa somente testes locais e não faz chamadas a Telegram nem serviços de IA.

## Arquitetura resumida

| Arquivo | Função |
|---|---|
| `assistente_pc.py` | Interface Telegram e comandos |
| `nucleo.py` | Dados JSON, logs, migração e rotinas |
| `multi_ia.py` | Provedores, erros e cotas |
| `evolucao_segura.py` | Autoanálise e melhorias com backup |
| `reinicio_seguro.py` | Reinício do assistente e reinício condicionado do Windows |
| `automacao_pc.py` | Ações locais com confirmação |
| `ponte_robotask.py` | Catálogo RoboTask |
| `painel_rotina.html` | Painel local |

## Atenção
- Nada foi publicado automaticamente no GitHub a partir deste ZIP. Publicar exige criar/selecionar o repositório privado e permitir seu acesso ao Codex.
- As chaves antigas presentes no projeto legado foram expostas anteriormente: **revogue-as e crie outras**, mantendo-as apenas no seu `.env` local.
- GitHub Actions não é uma prova de funcionamento no Windows real com RoboTask e Telegram.

**Documentação:** https://help.openai.com/pt-br/articles/20001545-using-codex-cloud
