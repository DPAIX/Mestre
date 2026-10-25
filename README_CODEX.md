# MeuControlePC v2.11.0 — Projeto para Codex

Este pacote contém o código-fonte, documentação, testes e instruções do Codex (`AGENTS.md`). Os arquivos `dados_iniciais/` são exemplos genéricos. O pacote de distribuição exclui `.env`, dados pessoais, credenciais, ambientes virtuais e modelos.

## Instalação no Windows em um clique

Extraia o pacote completo em Downloads, fora da pasta instalada, e abra **`INSTALAR_E_INICIAR.bat`**. O iniciador confere e implanta as fontes em C: com backup, reaproveita a configuração e os dados externos, prepara os componentes faltantes e solicita o início do assistente. O `iniciar_redirecionado.bat`, sem argumentos, também usa esse fluxo.

A janela local começa a preparação automaticamente. Ela oferece somente as pendências de conta e o botão **Retomar**. O 9Router pode criar sua nova chave dedicada pela autenticação oficial da CLI existente; login, 2FA, CAPTCHA e consentimentos ainda são concluídos pelo proprietário. Chaves são salvas apenas pelo campo oculto local, sem devolução ao chat ou à página de estado.

Consulte [Instalação automática](GUIA_INSTALACAO_AUTONOMA.md) para os caminhos, contas, conferência no PC e reversão. [A revisão v2.11.0](REVISAO_V2_11_0.md) descreve a implementação e os limites da validação. RoboTask é detectado sem executar tarefas desconhecidas; a nuvem não acessa o Windows apenas por ele estar instalado.

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
   git commit -m "Importar fontes publicas do MeuControlePC"
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
| `preparacao_autonoma.py` | Preparação com progresso e pendências locais |
| `implantacao_assistente.py` | Implantação de fontes verificadas com backup |
| `configurar_gateway_automatico.py` | Configuração local pela API oficial 9Router |

## Atenção
- Não publique `.env`, backups privados ou dados pessoais ao atualizar o repositório. O manifesto público enumera somente arquivos distribuíveis.
- As chaves antigas presentes no projeto legado foram expostas anteriormente: **revogue-as e crie outras**, mantendo-as apenas no seu `.env` local.
- GitHub Actions não é uma prova de funcionamento no Windows real com RoboTask e Telegram.

**Documentação:** https://help.openai.com/pt-br/articles/20001545-using-codex-cloud
