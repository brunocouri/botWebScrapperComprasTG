# Implementação e validação das melhorias

Data: 29/10/2026. Referência: PLANO-MELHORIAS.md. Implementação autorizada pelo usuário; preço ambíguo com faixa deve ser filtrado, conforme resposta explícita durante a execução.

## Entregas por etapa

| Etapa | Implementado | Limites e decisões preservadas |
|---|---|---|
| E0 | Cenários de regressão, testes isolados e medição sintética | Não foi medida latência real de Telegram nem feita comparação física antes/depois |
| E1 | Lock do SO, compatibilidade conservadora com PID antigo, exclusão em watch/listagem/autorização, cleanup, timeout, parada cooperativa e estados operacionais | Trava exercitada em processos locais Windows; recuperação física de rede permanece manual |
| E2 | Configuration central, escrita atômica, revisão esperada, JSON inválido explícito, seleção preservada, migração com backup e IDs estáveis | Arquivos reais não foram migrados durante os testes; conflito exige revisão pelo usuário |
| E3 | IPC restrito por origem/frame, CSP, navegação bloqueada, UTF-8 incremental, validação runtime, limite de linha, snapshot aplicado e timestamps | Allowlist de desenvolvimento é localhost:5173; build usa arquivo local |
| E4 | Matching antes do parser, associação conservadora, ambiguous_price, FloodWait tipado, contadores confirmados, histórico com desfecho, replay preservado e correção de links de grupos básicos | Sem NLP/OCR; alguns formatos ambíguos são filtrados; entrega continua at-most-once |
| E5 | Grupos filtrados, rascunhos globais, prioridade explícita, simulador Python sem efeitos, validação de configuração, autorização código/2FA e prevenção de perda no fechamento | Autenticação real não foi exercitada; troca destrutiva de conta não foi introduzida |
| E6 | Feed separado do App, lotes, limite de 800 registros por modo, filtros, detalhes, cópia com feedback, pausa de rolagem e rotação de logs | Sem virtualização adicionada por hipótese; seen/offers não são apagados automaticamente |
| E7 | Labels associados, foco visível, contraste corrigido, português, teclado e navegação recolhida em janela menor | Não é certificação WCAG nem validação integral com leitor de tela |
| E8 | Assets relativos, main/preload/helpers CommonJS, dev com compilação prévia, smoke de build e documentação atualizada | Build local requer Python no PATH; instalador, assinatura e runtime empacotado não fazem parte desta entrega |

## Contratos de dados e segurança

- Os arquivos existentes continuam no diretório original. COMPRAS_DATA_DIR permite isolamento explícito, sem migração ou exclusão automática.
- O arquivo de lock permanece. A existência do arquivo não indica processo ativo; não apagá-lo para forçar uma segunda conexão.
- Toda mutação operacional de JSON/.env passa pelo Python. O Electron não mantém um migrador concorrente escrevendo os mesmos arquivos.
- A configuração aplicada inclui regras, grupos e credenciais da mesma leitura coordenada. Apenas digest/contagens atravessam a fronteira do snapshot.
- Código de autenticação e senha não são colocados em argv, eventos ou arquivos. A UI aguarda resposta antes de aceitar outra entrada.
- JSON corrompido e revisão divergente são erros visíveis; não são convertidos em listas vazias.
- Histórico recebe colunas aditivas delivery_status/delivery_error; não há limpeza destrutiva nem expiração de seen.
- A marcação de seen vem antes do envio. Uma queda nesse intervalo pode perder um alerta. Não foi prometida entrega garantida.
- O simulador não importa bot.py, conecta ao Telegram, migra configuração ou abre seen.db/session.session.

## Testes e checks executados

Os testes foram escritos por comportamento, com reproduções que falharam antes das correções. Novas integrações usam processos locais, temporários, streams falsos e TelegramClient falso. Não foram usadas credenciais reais nem Playwright. Antes dos comandos de testes foi verificada a presença de artisan: inexistente neste workspace, portanto a limpeza de config Laravel é inaplicável.

Últimas seleções relevantes:

| Verificação | Resultado |
|---|---|
| pytest: test_monitor_runtime, test_product_prices, test_f3 e test_safety | 45 passaram |
| pytest: test_prices, test_rules, test_promos, test_f4 e test_persist | 76 passaram |
| Vitest: App, Activity, protocol, process, activity, keywords e rules-file | 44 passaram |
| Lint de fontes | Sem avisos/erros |
| TypeScript e build Vite/Electron | Passaram |
| Smoke do build compilado | Renderer → preload → IPC → configuração/simulador Python, com dados temporários |
| Detector estático de UI | Nenhum achado nos três arquivos inspecionados |
| Auditoria npm após correções compatíveis | Zero vulnerabilidades |

As duas seleções Python acima são disjuntas e somam 121 casos; não representam todas as formas de operação real. Houve ainda regressão de matching/merge em etapas anteriores. Os comandos foram direcionados aos arquivos afetados, sem uma execução genérica e repetitiva de toda a suíte.

O smoke abre uma janela oculta, exercita a bridge real e confirma que nenhum session.session/seen.db foi criado. Dados temporários são limpos ao terminar. Ele não confirma conexão MTProto ou envio real.

Dependências efetivamente instaladas após correção compatível: Electron 44.10.0, Vite 8.3.5, Vitest 5.0.5 e concurrently 10.0.6. Manifesto e lockfile atualizados; sem npm audit fix --force.

## Medições e inspeção

Benchmark local, Python 3.14.5, uma regra A57, 20.000 chamadas por cenário, sem rede/SQLite:

| Cenário | Tempo observado nesta execução |
|---|---|
| Texto sem match | 0,0349 s |
| Oferta multilinha com Pix/parcelamento | 1,4249 s |

Esses números são amostras sintéticas durante o desenvolvimento, não SLA nem comparação com produção. A regressão comprova que mensagem sem match não chama o parser. O teste de feed entrega 1.000 eventos em uma notificação agrupada e preserva os 800 mais recentes.

Inspeção do renderer com bridge fictícia, sem ler dados reais:

- Grupos, regras/editor, configurações e atividade foram inspecionados no DOM e árvore acessível; screenshots de grupos/editor também foram examinadas.
- Em viewport de 760 px, sem overflow horizontal, sidebar recolhida e campos inspecionados com labels associados.
- Texto discreto sobre superfície: contraste calculado de 6,41:1. Branco sobre botão principal: 6,11:1.
- O teste de rolagem comprova que novos eventos não deslocam a leitura manual e que Voltar ao final retoma acompanhamento.
- Uma captura de screenshot na janela menor não retornou no prazo de inspeção e foi interrompida; a verificação desse viewport usou DOM, geometria e árvore acessível.
- Aba e servidor de inspeção criados nesta tarefa foram encerrados; a sessão de outros projetos não foi modificada.

## Validação manual ainda necessária

1. Autenticar a conta real pelo desktop, incluindo código incorreto, código expirado e 2FA quando habilitado.
2. Monitorar grupo de teste autorizado e confirmar um envio real, formato/link e prazo de até 60s.
3. Simular perda/restauração física de rede e replay, confirmando estado e ausência de reenvio da mesma mensagem.
4. Executar por período prolongado para observar rotação, crescimento de offers/seen e estabilidade real.
5. Conferir zoom de 200%, percurso completo por teclado e leitor de tela no Windows de destino.

Não houve conexão, autenticação ou envio à conta real durante esta implementação. Essas verificações precisam ser feitas com ciência dos efeitos de login/envio. Dry-run real também marca seen.

## Decisões que não foram inferidas

- Não apagar offers/seen sem política de retenção aprovada.
- Não substituir sessão por outra conta silenciosamente.
- Não migrar dados para pasta de instalação/userData sem definir e validar a distribuição.
- Não introduzir tray, auto-start, FastAPI ou instalador como efeitos laterais das correções.
- A pasta não possui repositório Git reconhecido; não houve commit, push ou publicação.
