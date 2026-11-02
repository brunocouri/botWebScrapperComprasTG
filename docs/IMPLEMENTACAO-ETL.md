# Implementação do ETL parametrizável

Data: 30/10/2026. Implementação local autorizada. Nenhuma coleta real foi ativada
durante o desenvolvimento; nenhuma autenticação/envio Telegram fez parte dos testes.

Atualização de usabilidade: grupos selected são habilitados para arquivamento
por padrão ao inicializar catálogo/monitor, preservando preferências existentes.
O marco nasce nessa habilitação, sem importar o período em que já estavam selected.
Manual completo para treinamento em MANUAL-USUARIO.md.

Coletados agora aparece acima de Grupos e reutiliza o acervo: filtro de origem,
paginação, atualização manual/automática enquanto visível, detalhes e atalho de
parametrização. Não depende de modelo publicado nem de keyword correspondente.

## Entrega

O catálogo é opcional, separado do matching legado. Captura pode funcionar sem
modelos/worker; o worker pode processar o acervo sem monitor/sessão Telegram.
Busca consulta dados já extraídos sem depender do worker ativo.

- Banco SQLite catalog.db com schema versionado, WAL, transações, índices e backup
  consistente antes de migração. Os bancos antigos não são convertidos em catálogo.
- Fontes com início UTC, pausas/retomadas, escolha de recuperação e checkpoint de
  lote independente do recebimento ao vivo. União de origens usando um cliente.
- Texto/legenda, entidades, URLs reais de hyperlinks/botões, mídia como metadado.
  Revisões idempotentes, originais preservados e proteção contra atualização antiga.
- Fila transacional, worker exclusivo, retomada após queda e projeção atual separada
  de execuções auditáveis. Sem expiração automática de mensagens.
- Campos reutilizáveis e tipos; dinheiro em centavos, parcelamento, presença/
  ausência/desconhecido, categorias explícitas, links/lojas por hostname.
- Modelos imutáveis após publicação; edição em rascunho; reconhecimento de conflito;
  blocos, herança explícita, evidências, classificação de conteúdo sem oferta.
- Telas de coleta, acervo, editor por exemplos/seleção, teste, pendências agrupadas,
  exemplos/separação, busca paginada e filtros combináveis.
- Prévia de reprocessamento com token de escopo/configuração fixos; confirmação,
  progresso, cancelamento e retomada persistentes; resultados antigos preservados.
- Alertas estruturados opcionais com filtros por IDs; entrega pelo cliente existente,
  deduplicação própria, desfechos e histórico. Prévia/reprocessamento/recuperação e
  edições não geram alertas retroativos.
- IPC com origem validada, operações limitadas, detalhes de execuções sob demanda,
  limites de entrada/blocos/campos/saída e consultas parametrizadas.

## Validação e evidências

Testes focados novos em tests/test_catalog.py e tests/test_catalog_integrity.py:
cutoff, captura sem match, replay, revisão/reversão/fora de ordem, rollback,
retomada de worker, conflitos de versão/tipo/modelo, cupons por escopo, links
ocultos/UTF-16/botões, domínio parecido, SQL injection, backup/WAL e migração.
Cobrem também isolamento do legado em falha de catálogo, uso só de arquivo,
alertas estruturados novos sem retroatividade e cancelamento/retomada persistentes.

Frontend: ativação explícita, editor guiado, preservação de rascunho após falha e
navegação, filtros monetários brasileiros e alerta estruturado desativado por padrão.
Regressões selecionadas do monitor, segurança, preços, regras, persistência,
App/Activity/protocolo/lifecycle. Sem suíte completa e sem Playwright.

Execução final: 56 testes Python em catálogo/integridade/monitor/segurança/preços
por produto, 87 em preços/regras/persistência/F3/F4, 17 testes frontend em sete
arquivos. Build, lint e smoke concluíram com sucesso. A inspeção final confirmou
que nenhum catalog.db foi criado na raiz com dados reais.

O smoke do build real usa diretório temporário e verifica renderer/preload/IPC,
configuração, simulador, catálogo, publicação, extração, busca e start/stop do worker.
Verifica ausência de session.session e seen.db e overflow horizontal a 760px.
Capturas sintéticas em qa/catalog-desktop.png e qa/catalog-narrow.png.

Medição reproduzível com `python scripts/benchmark_catalog.py --count 10000`:

| Medida sintética | Resultado observado |
|---|---:|
| Mensagens/ofertas | 10.000 / 10.000 |
| Captura mediana / p95 | 1,04 ms / 1,92 ms |
| Processamento de 10 mil | 14,75 s |
| Busca numérica mediana / máxima | 4,93 ms / 6,24 ms |
| Banco e WAL durante medição | 26,3 MB |

Resultado bruto em qa/catalog-benchmark.json. A consulta inicial levava cerca de
3,2 segundos por executar uma subconsulta correlacionada para cada oferta.
Índices e seleção dos IDs compatíveis antes da projeção corrigiram esse custo.
Esses números não representam SLA de produção ou rede Telegram.

## Limites e homologação pendente

- Captura real, reconexão longa e edição real precisam de homologação em grupos
  explicitamente habilitados. A precisão temporal da origem é de segundos.
- Modelos exigem manutenção quando os canais mudam. Sem interpretação semântica
  por IA, OCR, confirmação de preço/estoque, resolução externa ou catálogo universal.
- Editor testa um exemplo por vez e compara com modelos publicados; teste outras
  mensagens antes de publicar. Não há garantia de generalização de uma amostra.
- Reprocessamento usa versões atuais fixadas na prévia; não há seletor visual para
  promover uma versão histórica. O histórico continua guardado no banco.
- Detalhes exibem até 50 revisões/execuções recentes, carregando uma execução por
  vez. Histórico completo não é apagado.
- O worker processa em lotes pequenos com transações por mensagem. Interrupção
  preserva fila; cancelamento vale para trabalhos ainda pendentes.
- Deduplicação antes do envio impede duplicação por replay, mas uma queda entre
  claim e confirmação pode perder um alerta. Entregas reivindicadas ficam visíveis.
- Word-match e alertas estruturados são independentes; ativar ambos pode produzir
  alertas distintos sobre a mesma mensagem.
- Não foi feita homologação de leitor de tela nem operação prolongada em conta real.

Uso e recuperação: GUIA-CATALOGO.md. Contrato: SPEC-ETL.md.
