# Revisão v2.11.0 — instalação automática

O usuário precisava copiar fontes e executar configuradores separados, mesmo depois de abrir `iniciar_redirecionado.bat`. A v2.11.0 reúne implantação, componentes, configuração local e início do aplicativo em uma preparação com progresso no navegador. O novo `INSTALAR_E_INICIAR.bat` também funciona a partir do pacote extraído, sem a cópia manual para C:.

## Alterações

| Arquivos | Resultado |
| --- | --- |
| `INSTALAR_E_INICIAR.bat`, `iniciar_redirecionado.bat` | Entrada de um clique; o início redirecionado sem argumentos passa pela preparação. |
| `preparacao_autonoma.py`, `preparacao_autonoma.html` | Orquestração, reutilização de componentes, progresso, pendências de conta, seleção de modelo e formulário local oculto. |
| `implantacao_assistente.py`, `manifesto_instalacao.json` | Verificação de fontes por SHA256, backup externo, implantação atômica por arquivo e reversão em caso de falha. |
| `controlar_instancia_preparacao.py` | Encerramento apenas do bot desta instalação com identidade comprovada, antes da atualização. |
| `configurar_gateway_automatico.py` | Leitura de metadados e criação de uma chave 9Router dedicada pela API oficial, com autenticação existente da CLI e trava para evitar duplicação. |
| `iniciar_servicos_locais.py` | Diagnóstico da porta Ollama ocupada sem disparar um segundo servidor ou encerrar o processo que escuta nela. |
| `ponte_preparacao_windows.py` | Abertura de páginas oficiais por IDs fixos e detecção de RoboTask sem execução de macros desconhecidas. |
| `roteador_9router.py`, `painel_rotina.html` | Limites de catálogo ampliados para os catálogos locais maiores, mantendo os limites de resposta. |

A preparação reaproveita credenciais locais quando disponíveis. Quando o serviço não permite criar uma credencial pela integração autenticada existente, apresenta a página oficial e o campo local necessário. O proprietário ainda conclui login, 2FA, CAPTCHA e consentimentos. A instalação não declara que saldo, geração ou agentes estão operacionais apenas porque um catálogo respondeu.

Configuração e dados externos, modelos, macros existentes e ambientes virtuais são preservados. A preparação não altera a rede do Windows nem o início de aplicativos de terceiros. Chaves que apareceram em capturas de tela não são reutilizadas pela nova configuração automática do gateway.

## Validação e limites

Os testes de instalação usam diretórios temporários, servidores locais e respostas simuladas. Verificam integridade do pacote, preservação e reversão, identidade do processo, travas, isolamento da interface e contratos de configuração. Não executam macros pessoais, instaladores Windows reais, sessões remotas nem geração em contas externas.

O relatório de entrega e o resultado do CI registram as quantidades e os resultados finais da suíte. A validação no computador-alvo continua necessária: não havia dispositivo Windows conectado ao ambiente de desenvolvimento nesta entrega.

Um timeout do Ollama com porta ocupada é uma pendência observável; não autoriza encerrar um processo sem identidade comprovada. Abrir o 9Remote ou detectar o RoboTask também não comprova pareamento ou execução de uma macro.

## Instalação, conferência e reversão

Siga [Instalação automática](GUIA_INSTALACAO_AUTONOMA.md). Extraia o pacote e abra `INSTALAR_E_INICIAR.bat`; conclua somente as pendências de conta indicadas e use **Retomar**. Depois confira o painel, `/status`, uma conversa e um áudio no Windows.

As fontes anteriores ficam em `backups_codigo\implantacao_<identificador>`, junto do índice de reversão. A cópia privada do `.env` fica em `backups_codigo\configuracao`. O guia detalha a restauração somente das fontes e opções afetadas, sem substituir dados ou modelos.
