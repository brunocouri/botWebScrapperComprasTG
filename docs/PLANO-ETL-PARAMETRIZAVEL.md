# Plano de implementação — ETL parametrizável de ofertas

Data: 29/10/2026.

Status: implementação autorizada em 30/10/2026. Coleta real continua dependendo de ativação explícita por grupo. Contrato detalhado em SPEC-ETL.md.

Atualização aprovada pelo usuário: selected em Grupos passa a habilitar arquivamento
por padrão na inicialização do catálogo/monitor. Não reconstruir histórico anterior
ao novo marco. Preferências existentes de coleta são preservadas; pausa continua
independente dos alertas. Esta decisão substitui o padrão inicial de não adesão abaixo.

## 1. Objetivo

Construir um acervo pesquisável das postagens recebidas a partir da ativação de cada grupo. O usuário define modelos para interpretar produto, preços, condições, cupons, links, loja e outros campos. Formatos desconhecidos entram numa fila agrupada de parametrização.

A responsabilidade do app é representar o que foi anunciado e mostrar sua origem. Conferência da compra, preço na página, disponibilidade, legitimidade da promoção e aplicação efetiva de cupom pertencem a quem compra.

O resultado esperado é pesquisar, por exemplo: produto contendo Galaxy A57, preço Pix anunciado até R$ 1.900, loja escolhida, cupom obrigatório ou não informado e intervalo de publicação, sempre com acesso à mensagem original e às condições extraídas.

## 2. Escopo da primeira versão completa

Incluído:

- Arquivamento de todas as mensagens recebidas dos grupos habilitados para coleta, independente de palavra-chave, modelo ou alerta.
- Texto/legenda integral e metadados necessários: origem, IDs, datas, links visíveis/ocultos, entidades de formatação, botões com URL e metadados básicos de mídia.
- Modelos múltiplos por grupo, editáveis por exemplos e versionados.
- Campos com nome livre, identidade estável, tipo, obrigatoriedade, cardinalidade e escopo.
- Oferta individual, blocos repetidos de ofertas e divulgação de cupom sem produto.
- Regras compartilhadas de identificação de loja por hostname/domínio configurado.
- Prévia de extração, pendências agrupadas, reprocessamento local e busca filtrável.
- Continuidade dos alertas atuais durante a implantação e integração opcional dos campos estruturados aos novos filtros de alerta.

Fora desta versão:

- Varredura anterior à ativação, importação histórica do Telegram ou preenchimento do passado a partir do antigo histórico de alertas.
- Verificação de preço/estoque na loja, teste de cupons, compra automática ou clique de compra.
- IA/LLM, OCR, interpretação de áudio/vídeo, download automático de mídias e resolução automática de links externos.
- Inferência automática de catálogo universal, equivalência entre variantes ou ranking de melhor oferta do mercado.
- Reescrita em FastAPI, serviços distribuídos, instalador ou migração para outro banco como pré-requisito.

## 3. Decisões recomendadas para aprovação

| Tema | Proposta inicial |
|---|---|
| Banco | Novo catalog.db SQLite no diretório de dados; session.session e seen.db preservados |
| Seleção de grupos | Arquivar e Alertar são escolhas independentes; nenhum grupo existente passa a ser arquivado silenciosamente |
| Início temporal | capture_started_at UTC persistido por grupo; reinício não muda esse marco |
| Campos | Catálogo reutilizável no workspace, com IDs estáveis e nomes editáveis; modelos de grupos distintos podem preencher o mesmo campo |
| Modelos | Vários por grupo; publicação explícita e versões publicadas imutáveis |
| Extração | Construtores guiados por marcadores/linhas/blocos, tipos e regras explícitas; sem código executável arbitrário |
| Regex livre | Adiada; sua inclusão futura exige execução limitada e proteção contra processamento excessivo |
| Desconhecidos | Fila por grupo/formato, com contagem e exemplos; sem modal/notificação por mensagem |
| Mudança de modelo | Processar pendentes compatíveis e mensagens futuras; reprocessar resultados já concluídos só após prévia e confirmação de escopo |
| Alertas retroativos | Desativados por padrão; reprocessamento e simulação nunca disparam alertas |
| Retenção | Sem exclusão automática de mensagens, revisões ou extrações nesta entrega |
| Operação real | Coleta depende de ativação explícita; testes automatizados usam dados temporários e cliente falso |

Os nomes de tabelas/módulos abaixo são propostas de implementação, sem criar um framework genérico de automação.

## 4. Arquitetura proposta

```text
Telegram: mensagem nova ou edição observada
                  |
                  v
Captura -> transação: revisão original + trabalho pendente
                  |
                  v
Worker local de ETL, sem TelegramClient
                  |
                  v
Reconhecer modelo -> extrair -> normalizar -> registrar evidências
                  |
          +-------+--------+
          |                |
          v                v
Resultado consultável   Pendência agrupada
          |
          v
Busca e filtros / alertas autorizados para eventos novos
```

O arquivo raw é gravado antes de avaliar keywords ou decidir alertas. Trabalho e revisão entram na mesma transação. Processamento falho não apaga a mensagem e não bloqueia a captura de outras mensagens que possam ser persistidas.

Falha na própria gravação é um erro de integridade do catálogo: não marcar a mensagem como capturada, não avançar checkpoint e não fingir sucesso. Alertas legados continuam independentes dessa falha e do worker. Mostrar coleta degradada e recuperar desde o último checkpoint confirmado quando possível. Somente alertas estruturados dependem dos campos extraídos.

O worker tem instância exclusiva e trabalhos persistentes. Queda do worker não perde a fila; nova execução recupera trabalhos interrompidos. UI e CLI não devem iniciar dois workers concorrentes nem encerrar processos de outro dono. CPU de interpretação não ocupa o loop de recepção MTProto.

Não prometer captura absoluta de eventos que o Telegram não entregar ou não permitir recuperar. Lacunas detectadas ficam visíveis, com grupo e intervalo afetado.

## 5. Contratos de captura e temporalidade

1. Habilitar arquivamento registra o grupo e seu marco de início. A UI informa quando a captura efetivamente entrou em operação.
2. Grupos escutados são a união dos habilitados para arquivo e dos selecionados para alertas existentes. Apenas um TelegramClient usa a sessão.
3. Recuperação após desconexão pode consultar mensagens do período de captura; isso não autoriza varredura anterior ao marco inicial.
4. Checkpoint só avança após persistência confirmada do lote completo. Mensagens fora de ordem não podem avançá-lo sobre uma lacuna conhecida.
5. Reentrega da mesma revisão é idempotente. Edição observada de mensagem já capturada cria uma revisão, sem sobrescrever o original.
6. Mensagem publicada antes do marco inicial não entra por causa de edição posterior. Não buscar mensagem antiga apenas para completar uma edição desconhecida.
7. Desabilitar captura preserva o acervo e registra a pausa. Na reativação, perguntar se retoma com recuperação desde o checkpoint ou inicia um novo intervalo dali em diante; não ocultar o intervalo sem coleta.
8. Mensagem só com mídia continua registrada; ausência de texto recebe estado específico, sem exigir parametrização de imagem nesta versão.
9. Guardar apenas os dados necessários à postagem; não coletar listas de membros, contatos ou dados adicionais da conta.

## 6. Modelo de dados proposto

| Entidade | Conteúdo e invariantes |
|---|---|
| sources | Identidade Telegram, nome observado, arquivamento, marcos/intervalos de captura e checkpoint |
| message_revisions | Identidade da mensagem, revisão de origem, conteúdo original, links/entidades/botões, timestamps e hash de integridade |
| field_definitions | ID, nome exibido, tipo, papel semântico opcional e opções de enumeração |
| template_versions | ID estável do modelo, grupo, versão, rascunho/publicado/arquivado, critérios de reconhecimento, blocos e mapeamentos |
| stores | Identidade estável e nome da loja; canal de origem e vendedor são informações distintas |
| link_rules | Host/domínio, modo de correspondência, loja associada e versão da regra |
| processing_jobs | Revisão alvo, configuração/versionamento alvo, estado, tentativas e diagnóstico |
| extraction_runs | Revisão de origem, versões utilizadas, resultado e evidências; tentativas auditáveis |
| offer_records | Ocorrências de oferta/cupom extraídas por bloco, com projeção atual e vínculo à execução/origem |
| offer_values | Campo, escopo/bloco/opção de preço, valor original e normalizado, presença e evidência |
| review_items | Grupo, motivo, assinatura aproximada de estrutura, contagem, exemplos e resolução |

Diretrizes:

- O nome de campo não é uma coluna SQL. Novos parâmetros não exigem migrations por campo.
- Valores tipados permitem filtros numéricos/textuais. Regras e payloads preservados em JSON não substituem toda a indexação necessária à busca.
- O schema físico deve criar índices para origem/data, identidade/revisão, estado de trabalho e combinações de campo/valor realmente usadas na busca.
- Identidade de captura e seen de alertas são independentes. O offers atual representa avaliações de alertas e não será convertido silenciosamente em catálogo.
- Renomear campo preserva seu ID. Alterar tipo de campo com dados exige novo campo ou migração explícita, nunca reinterpretar valores antigos silenciosamente.
- Mensagens repetidas em canais diferentes preservam todas as origens. Não descartá-las apenas por texto/produto semelhante.
- Trabalho repetido para a mesma revisão e conjunto de versões não duplica resultados. Atualizar a projeção consultável é transacional e não remove execuções anteriores.
- Revisão antiga recebida fora de ordem não pode substituir a interpretação atual de revisão mais recente.

## 7. Campos e relações suportados

Tipos iniciais:

| Tipo | Comportamento |
|---|---|
| Texto | Produto mencionado, descrição, código de cupom, vendedor ou observação |
| Dinheiro | Valor inteiro em centavos e moeda BRL; não confundir referência com valor anunciado para compra |
| Número | Quantidade, capacidade ou outro número cuja unidade seja configurada |
| Condição | Presente, ausente ou desconhecida, com texto/evidência; ausência não vira falso sem regra explícita |
| Categoria | Enumeração/mapeamento definido pelo usuário, sem classificador automático |
| Link | URL original, host normalizado, localização na mensagem e classificação de loja quando configurada |
| Parcelamento | Número de parcelas, valor da parcela e total aritmético, com origem identificada |

O campo tem nome livre, obrigatoriedade configurável e cardinalidade um ou vários. Seu papel opcional, como produto, preço Pix, referência, cupom ou loja, ajuda a compor visualizações sem depender do nome literal.

Escopos: mensagem, bloco de oferta e opção de preço. Pix e cartão podem ser alternativas da mesma oferta; cada opção mantém suas próprias condições e cupons. Um cupom no cabeçalho só é herdado por todos os produtos se o modelo declarar essa relação.

Não calcular desconto pelo nome do cupom. Não subtrair cupom de preço possivelmente já descontado. Calcular somente relações explicitamente parametrizadas, guardando fórmula, entradas e rótulo de valor calculado. Não inferir juros, elegibilidade ou desconto desconhecidos.

## 8. Modelos por grupo

### Reconhecimento

Cada modelo declara marcadores textuais, estrutura de blocos e outros critérios verificáveis. Conteúdo variável, como produto/preço/código, é extraído e não faz parte de uma identidade fixa da mensagem.

- Nenhum modelo compatível: unknown_format.
- Mais de um modelo compatível sem regra inequívoca de seleção: ambiguous_template.
- Modelo reconhecido, mas campo obrigatório falha: extraction_error ou ambiguous_field.
- Campo opcional ausente: registrar ausência sem inventar valor.
- Texto extra fora dos campos: preservar; não criar pendência automaticamente por pontuação, saudação ou rodapé irrelevante.

Ordem de modelos não deve esconder conflito acidental. Publicação mostra sobreposições contra modelos ativos do mesmo grupo. A política de primeira regra elegível dos alertas legados permanece separada desse reconhecimento.

### Extratores guiados

- Linha absoluta ou relativa a marcador.
- Conteúdo após/antes de um marcador ou entre dois marcadores.
- Presença de expressão configurada para condição.
- Blocos repetidos por delimitador explícito; cada bloco pode gerar uma oferta.
- Links por posição, marcador ou regra de domínio.
- Conversão de dinheiro/parcelamento usando gramática BR e evidência original.
- Valores constantes e mapeamentos explícitos, identificados como configuração do usuário, sem atribuí-los falsamente ao texto.

Nada de eval, scripts arbitrários ou acesso ao filesystem/rede dentro do modelo. Toda operação tem limite de entrada, quantidade de blocos e custo de execução testado.

### Versionamento

Salvar rascunho não altera extrações em produção. Publicar gera nova versão imutável. Cada execução referencia versões do modelo, campos, regras de links e motor utilizadas. Arquivar modelo impede novos usos sem apagar resultados existentes.

## 9. Identificação de links e lojas

- O usuário cadastra a regra de host/domínio e associa a uma loja. Não presumir que uma substring isolada é um domínio completo válido.
- Correspondência é pelo hostname analisado e normalizado: host exato ou subdomínios explicitamente permitidos, respeitando fronteiras de domínio.
- Ler a URL real de hyperlinks e botões, não somente seu texto visível.
- Guardar URL original e URL interpretada; não remover parâmetros de afiliação ou consulta por suposição.
- Canal que publicou, loja, plataforma marketplace e vendedor não são sinônimos. O modelo pode preencher campos separados.
- Link desconhecido permanece desconhecido. Não acessar encurtadores ou páginas de compra automaticamente nesta versão.
- Regras de lojas são reutilizáveis entre grupos e versionadas. Corrigi-las permite reprocessar classificações locais.

## 10. Pendências e reprocessamento

A fila agrupa por grupo, motivo e assinatura aproximada de estrutura. A assinatura serve para organizar exemplos, não prova que todas as mensagens tenham o mesmo significado.

Cada item mostra primeira/última ocorrência, quantidade, exemplos diferentes e ações: criar modelo, ajustar modelo, classificar como conteúdo sem oferta ou deixar pendente. Ignorar uma classe não apaga mensagens; a classificação é rastreável.

Publicar um modelo apresenta prévia sobre exemplos salvos e permite processar pendentes compatíveis daquele grupo. Cada mensagem ainda passa por reconhecimento/extração próprios; agrupamento não aprova todo o lote automaticamente.

Reprocessar resultados concluídos exige escolher grupo, período, versões e estados, visualizar quantidade e confirmar. O job tem progresso, cancelamento entre lotes e retomada. Comparar resultados anteriores/novos e preservar histórico.

Reprocessamento, correção manual de modelo e simulação não enviam alertas nem alteram seen dos alertas existentes. Separar falha técnica transitória de falha determinística de extração: esta vai para revisão, sem retry infinito.

## 11. Fluxos de interface

1. **Grupos:** distinguir Arquivar de Alertar; mostrar marco inicial, estado da captura e lacunas/pausas. Aplicação da mudança de escuta é explícita, com recuperação dentro do período autorizado.
2. **Acervo:** listar mensagens por grupo/data/estado, inclusive desconhecidas e mídia sem texto; abrir original e revisões.
3. **Modelos:** listar formatos do grupo, versão e estado; criar rascunho a partir de uma mensagem salva.
4. **Editor por exemplos:** original e marcação de trechos, definição de campos/relações e prévia lado a lado; permitir configurar o trecho selecionado como variável, sem fixar o produto/valor de exemplo.
5. **Publicação:** comparar extrações em outros exemplos, apontar obrigatórios falhos/conflitos, confirmar impacto e publicar; avisar quando a amostra disponível for pequena.
6. **Pendências:** resumo agrupado com quantidade e exemplos; não interromper uso a cada chegada de mensagem.
7. **Ofertas:** filtros tipados por campo, grupo de origem, loja, intervalo, preço/condição e estado da extração; abrir evidências e original.
8. **Reprocessamento:** escolher escopo, visualizar impacto, acompanhar/cancelar/retomar; sem alertas retroativos.

Nomes e tipos de campos são reutilizados entre grupos para permitir comparação. Não declarar automaticamente dois campos equivalentes apenas porque seus rótulos se parecem. Busca textual de produto é parte da V1; identidade canônica e equivalência entre variantes ficam fora.

Preservar a identidade visual existente, teclado, foco, contraste e rascunhos. Não expor IDs internos, detalhes de SQL ou JSON obrigatório nos fluxos normais. Avançados e diagnóstico podem mostrar detalhes técnicos sob demanda.

## 12. Fases de implementação e critérios de aceite

### F0 — Spec detalhada e contratos de exemplo

Entrega: fixtures anotadas, contratos de captura/versionamento, gramática dos extratores e estados IPC. Começar com exemplos fictícios ou amostras fornecidas, sem ativar conta real implicitamente.

Cobrir: oferta individual, Pix/cartão, cupom condicionado, cupom sem produto, lista de produtos, hyperlink oculto, múltiplos links, condição opcional ausente, mídia sem texto, formato desconhecido e modelos conflitantes.

Aceite: cada formato tem exemplos positivos, negativos e o resultado esperado; decisões da seção 3 estão aprovadas ou ajustadas. Nenhuma chamada de rede é necessária à spec.

### F1 — Banco e captura independente

Entrega: catalog.db, migrations aditivas, seleção de grupos para arquivo, mensagens/revisões, checkpoint e criação transacional dos jobs. Persistir antes de keyword/alerta.

Aceite: mensagem sem match/modelo continua no acervo; reentrega não duplica; edição preserva original; falha de disco não avança cursor; reinício não altera marco inicial; recuperação não consulta anterior ao início autorizado. Dados existentes permanecem intactos.

Esta é a primeira entrega operacional útil: acervo bruto durável, mesmo antes do editor completo.

### F2 — Motor parametrizável e worker

Entrega: campos tipados, reconhecimento de modelos, extratores guiados, escopos de oferta/preço, blocos repetidos, evidências e worker retomável sem TelegramClient.

Aceite: alterações de produto/preço não invalidam um formato; campos não herdam valores de outro bloco; opcionais não viram falha obrigatória; conflito não escolhe silenciosamente um modelo; crash retoma jobs sem duplicar resultados. Limites de entrada/tempo/blocos impedem travar captura/UI.

### F3 — Links, lojas e condições

Entrega: cadastro compartilhado de lojas/regras de links; relação explícita entre cupom, condição e opção de preço; normalizações e cálculos identificados.

Aceite: identificar host configurado em texto, entidade e botão; rejeitar domínio parecido malicioso; preservar links desconhecidos; cupom de um bloco não contamina outro; código GALAXY100 não implica desconto de R$ 100.

### F4 — Editor visual e publicação

Entrega: criação por mensagem salva, campos reutilizáveis, seleção de trechos, prévias e publicação/versionamento.

Aceite: usuário configura um formato por marcadores sem escrever código; consegue testar outras mensagens e ver evidências/erros; salvar rascunho não altera produção; renomear campo preserva buscas; falha ao salvar não perde trabalho.

### F5 — Pendências e reprocessamento

Entrega: agrupamento, exemplos, resolução, prévia de impacto e lotes retomáveis.

Aceite: cem mensagens semelhantes não criam cem interrupções; mensagens do grupo continuam salvas enquanto há pendência; agrupamento errado pode ser separado; novo modelo processa pendentes compatíveis; resultados anteriores permanecem auditáveis; nenhum alerta retroativo é enviado.

### F6 — Busca e catálogo de ofertas

Entrega: listagem paginada e filtros tipados, origem, loja, período e condições; detalhes com preços alternativos e original.

Aceite: comparar o mesmo campo entre dois grupos; distinguir desconhecido de ausente/zero; combinar condições sem misturar opções Pix/cartão de ofertas distintas; registrar cupom sem produto; preservar ocorrências de origens diferentes. Plano de índices e tempo de busca verificados com volume sintético representativo.

### F7 — Alertas estruturados e operação integrada

Entrega: filtros opcionais sobre campos extraídos, observabilidade da captura/worker/pendências e integração final CLI/Electron.

Aceite: alertas legados mantêm seu contrato enquanto não migrados; filtros estruturados referenciam IDs de campos; revisão/reprocessamento não reenviam; novos alertas respeitam origem nova e deduplicação independente da captura. Falha de alerta não desfaz captura ou extração.

### F8 — Validação e documentação

Entrega: regressão focada, smoke do build, instruções, recuperação/backup e relatório de limitações.

Aceite: instalar/abrir build local com dados isolados; fechar e retomar com jobs pendentes; navegar por teclado nas telas novas; nenhuma suíte automatizada acessa conta real. Validar captura real somente em canais/grupos autorizados após ativação explícita.

## 13. Módulos e arquivos previstos

| Área | Alteração proposta |
|---|---|
| bot.py | Capturar antes do matching; eventos de edição observados; union de grupos e recuperação temporal |
| catalog_storage.py (novo) | Schema/migrations, revisões, jobs, execuções e consultas |
| extraction/ (novo, pequeno) | Tipos, modelos, reconhecimento, extratores e validações puros |
| etl_worker.py (novo) | Processamento local retomável com exclusão de instância, sem TelegramClient |
| config_cli.py | Rotas sem sessão para consultas/configuração ETL, prévia e submissão de jobs |
| configuration.py | Integração das revisões/configuração com fontes de captura, sem apagar seleção legada |
| rules.py / price_parser.py | Reuso das primitivas compatíveis; separar política legada de interpretação configurada |
| electron/electron/main.ts e preload.ts | IPC e lifecycle do worker, consultas paginadas e progresso |
| electron/src/lib/ipc.ts | Contratos versionados para fontes, modelos, campos, pendências, catálogo e jobs |
| electron/src/features/ | Telas de acervo, modelos/editor, pendências e ofertas; extrair conforme entrega |
| tests/ e testes frontend | Casos de domínio, integração e interação com dados isolados |

Não mover todo o backend para o esqueleto planejado. Extrair módulos quando a fase exigir uma fronteira real. Configuração de modelos/links/campos no catalog.db deve ter transação e revisão próprias; não manter duas fontes de verdade em JSON e banco.

## 14. Estratégia SDD/TDD e segurança de dados

Para cada fase: fechar contrato de entrada/saída -> escrever testes que reproduzem o comportamento ausente/incorreto -> implementar o mínimo -> refatorar -> executar regressão relevante e registrar evidência.

Testes essenciais:

- Processo capturador cai antes/depois de commit e enfileiramento; resultado não perde vínculo com o original.
- Worker cai durante lote; retomada idempotente e ausência de duplicação na projeção atual.
- Mensagens fora de ordem, duplicatas, edições, reversão de conteúdo e versões antigas não sobrescrevem indevidamente revisões novas.
- Captura antes do corte rejeitada; recuperação dentro do intervalo autorizado permitida; pausa/reativação explícitas.
- Múltiplos produtos, preços, cupons e condições mantêm seus respectivos escopos.
- Dois modelos casam; nenhum casa; obrigatório falha; opcional falta; texto extra irrelevante não provoca avalanche de pendências.
- Mudança de rótulo e versão não quebra filtros nem reescreve resultados antigos.
- Publicação/reprocessamento/preview não autenticam nem enviam ao Telegram.
- Domínios e hyperlinks: hostname exato/subdomínio permitido, Unicode/normalização, texto visível diferente da URL e domínio apenas parecido.
- Queries são parametrizadas e paginação determinística; valores de usuário não viram SQL ou código.
- UI preserva rascunhos, mostra progresso real, funciona por teclado e não trava sob rajada.

Toda migration é aditiva e testada em cópia temporária. Backup consistente antes de evoluir um catalog.db com dados reais; sem exclusões automáticas. Não fazer cópia ingênua de um SQLite ativo como se garantisse backup consistente.

Selecionar testes pytest/Vitest conforme a mudança; não usar Playwright. Antes de testes Laravel, executar php artisan config:clear quando houver aplicação aplicável; este workspace não tem artisan. Build/lint/smoke nas etapas que alterarem Electron e contratos.

## 15. Operação, limites e mensuração

- Painel distingue captura ativa/parada/degradada, worker ativo/parado, fila pendente, formatos desconhecidos e alertas. Worker parado não significa que captura deixou de persistir.
- Retenção inicial é integral e explícita. Mostrar crescimento do banco e falta de espaço; não apagar o acervo para contornar falha de disco.
- Medir escrita, atraso entre captura/extração, custo por modelo, tamanho do acervo e consulta paginada com massa sintética. Não estabelecer SLA de produção sem volume/ambiente medidos.
- Agrupamento de pendências é aproximação; correção exige exemplos diversos e avaliação por mensagem.
- Mudanças de padrão exigem manutenção dos modelos. Reutilização de campos/regras reduz o custo, mas não o elimina.
- Registrar preço informado e condições como evidências da postagem; não rotular como confirmado, vigente ou disponível sem essa informação na própria origem.
- Não garantir reconstrução de toda edição/exclusão ocorrida quando o app estava indisponível. V1 preserva revisões observadas e lacunas detectadas.

## 16. Pontos de revisão e autorização

O plano pode ser aprovado integralmente ou por fases. Ordem recomendada: F0/F1 -> F2/F3 -> F4/F5 -> F6/F7 -> F8. Cada conjunto produz uma entrega revisável; não acumular todas as mudanças numa entrega única.

Antes de executar, confirmar ou alterar as propostas da seção 3. Decisões com maior impacto:

1. Capturar todas as mensagens somente dos grupos explicitamente habilitados, com Arquivar e Alertar independentes.
2. Campos tipados reutilizáveis entre grupos, com nomes livres e IDs estáveis.
3. Construtores guiados inicialmente; regex livre e IA ficam para evolução posterior.
4. Publicação de modelo pode processar pendentes, mas não reprocessa silenciosamente todo o acervo nem envia alertas retroativos.
5. Novo banco local e nenhuma migração destrutiva dos dados existentes.

Aprovar este documento permitirá implementar dentro desses limites. Não implica autorização para varredura histórica, limpeza de dados, publicação/deploy ou acesso à conta real antes da ativação explícita da coleta.
