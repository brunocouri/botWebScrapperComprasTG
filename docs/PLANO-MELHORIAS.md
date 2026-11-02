# Plano de melhorias — ComprasTG

Data: 29/10/2026.

Status: planejamento solicitado pelo usuário. Este documento não implementa mudanças nem comprova funcionamento em execução.

Atualização: implementação autorizada posteriormente e registrada em IMPLEMENTACAO-MELHORIAS.md. A política de preço ambíguo foi aprovada pelo usuário: não alertar nas regras com faixa e mostrar o motivo. Demais propostas destrutivas/de distribuição não recebem aprovação implícita.

## 1. Objetivo e limites

Tornar o monitor confiável para operação contínua: estado verdadeiro, sessão exclusiva, configuração preservada, decisões de preço explicáveis e interface que permita corrigir problemas sem depender de logs técnicos.

Arquitetura preservada: React → preload → Electron IPC → processo Python → Telethon, com retorno JSONL. `electron/src/lib/ipc.ts` continua como fonte de verdade do contrato. FastAPI e o layout `backend/app/*` não são pré-requisitos.

Desenvolvimento por Spec Driven Development e TDD: especificar comportamento, escrever reprodução que falhe, implementar o mínimo e refatorar com a regressão focada passando. A extração de módulos acompanha as mudanças necessárias; não haverá reorganização geral antecipada.

Não executar ações sobre a conta real durante testes automatizados. Não sobrescrever `.env`, `session.session`, `watched_groups.json`, `keywords.json` ou `seen.db` reais em fixtures. Não executar o script atual que encerra todos os processos Python.

## 2. Contratos a preservar

- Match exato e case-insensitive: `A57` e `a57,` correspondem; `A570`, `XA57` e `A57PRO` não.
- Valores monetários em centavos inteiros; IDs de regra estáveis após renomeação.
- Ordem das regras define prioridade; no máximo uma vencedora elegível por mensagem.
- Falha de envio não promove outra regra.
- Deduplicação persistente por `(chat_id, msg_id)`, antes do envio, com semântica at-most-once. Não prometer entrega garantida.
- Falha de integridade de `seen` impede efeitos; falha de histórico `offers` permanece best-effort e visível.
- `dry-run` operacional mantém a semântica atual de marcar `seen`; o novo simulador é independente e não marca nada.
- Manter sincronização de mensagens perdidas; não suprimir `getDifference` para acelerar startup.
- Logs sem emoji, arquivo sem ANSI e protocolo separado dos logs humanos.
- Nenhuma exclusão automática de histórico ou mudança silenciosa de conta/configuração.

## 3. Sequência de execução

| Etapa | Entrega | Dependência | Esforço relativo |
|---|---|---|---|
| E0 | Especificações, cenários e linha de base | — | Pequeno |
| E1 | Sessão exclusiva e ciclo de vida correto | E0 | Grande |
| E2 | Persistência e configuração seguras | E0; integrar com E1 | Médio |
| E3 | Protocolo, diagnóstico e segurança Electron | E1–E2 | Médio |
| E4 | Preço por produto, envio e estatísticas corretos | E2–E3; fechar política de ambiguidade | Grande |
| E5 | Fluxos de grupos, regras e configuração | E1–E4 | Grande |
| E6 | Atividade e desempenho medido | E3–E5 | Médio |
| E7 | Acessibilidade e acabamento | Aplicar desde E5; revisão após E6 | Médio |
| E8 | Build, documentação e validação integrada | E1–E7 | Médio |

Esforço relativo não é previsão de prazo. Cada etapa deve produzir uma mudança revisável com critérios próprios; não juntar toda a execução em uma entrega única.

## 4. E0 — Especificação e linha de base

### Trabalho

- Registrar cenários críticos deste plano como contratos executáveis, sem tratar testes de helpers como prova de integração.
- Conferir as versões efetivamente instaladas antes de usar comportamentos de documentação de versões diferentes, especialmente Telethon.
- Registrar startup até `monitoring_started`, custo de avaliar mensagens e atualizações do renderer usando dados sintéticos.
- Definir ambiente isolado de testes e formas de injetar paths, relógio, processo e TelegramClient.
- Documentar discrepâncias entre `AGENTS.md`, `RULES.md`, `SPEC.md`, `PRODUCT.md` e o código; corrigir a documentação na etapa dona da mudança.

### Aceite

Cada defeito prioritário tem cenário observável de antes/depois. Medições indicam ambiente, volume e procedimento, sem inventar metas ou números de produção.

## 5. E1 — Exclusividade da sessão e ciclo de vida

### Trabalho

- Substituir o fluxo de lock sujeito a corrida por exclusão atômica válida no Windows, com metadados de proprietário. Escolher o mecanismo na spec técnica após verificar encerramento abrupto e recuperação de lock antigo; não adicionar dependência sem necessidade.
- Usar a mesma proteção em watch, listagem e autenticação. Em falha de aquisição/verificação, impedir abertura da sessão.
- Liberar recursos em todos os caminhos: falha de config, timeout, autorização ausente, cancelamento, erro de conexão e encerramento normal. A liberação nunca remove lock de outro proprietário.
- Manter a referência do filho no Electron até `close`. Start, stop, reload e autenticação não podem disputar a sessão.
- Implementar estado operacional tipado: parado, iniciando, conectando, autenticacao_necessaria, sincronizando, monitorando, reconectando, parando e erro. Estado de processo e conexão são informações distintas.
- `startBot()` confirma aceitação do comando; somente o evento operacional confirma monitoramento. Desabilitar ações incompatíveis durante transições.
- Conexão com limite de 45s e verificação de autorização com limite de 5s. Relatar timeout sem fingir sucesso.
- No desktop, detectar autorização ausente sem pedir input invisível no terminal. Até o fluxo de autenticação da E5, apresentar instrução explícita para autenticação pela CLI, com o monitor parado.
- Encerrar apenas o filho/PID validado deste app nos scripts. Não presumir que `kill()` no Windows executará o `finally` do Python; verificar e prever encerramento cooperativo com timeout e fallback restrito ao filho.
- Tratar fechar janela explicitamente como encerrar o monitor nesta versão; tray permanece uma evolução separada.

### TDD e aceite

- Dois processos simultâneos: apenas um abre a sessão; perdedor recebe erro explícito.
- Watch versus listagem/autenticação tem a mesma exclusão, inclusive com processo headless externo.
- Lock inválido, antigo ou impossível de gravar não autoriza dois clientes.
- Stop → start rápido espera o encerramento anterior; callbacks antigos não alteram o novo processo.
- Spawn aceito sem conexão mantém a UI em transição; erro/timeout não aparece como monitoramento ativo.
- Fechamento da janela e falhas durante startup não deixam recursos pertencentes à instância sem tratamento.

Arquivos principais: `bot.py`, `electron/electron/main.ts`, `electron/src/lib/lifecycle.ts`, `electron/src/lib/ipc.ts`, `electron/electron/preload.ts`, scripts headless e testes de integração de processos.

## 6. E2 — Persistência e configuração

### Trabalho

- Diferenciar arquivo ausente, inválido e inacessível. Nenhum erro de leitura deve virar lista vazia seguida de sobrescrita.
- Escrita por temporário no mesmo diretório e substituição atômica conforme a plataforma; limpeza do temporário e preservação do último arquivo válido quando a substituição falhar.
- Serializar mutações de configuração no processo principal. Evitar corrida de leitura/edição/gravação entre Electron e CLI por coordenação de escrita ou revisão de conteúdo; o lock de sessão sozinho não resolve edição concorrente de JSON.
- Preservar `selected` por ID, backup da migração e IDs de regras entre leituras legadas. Não gerar identidades diferentes a cada leitura sem persistência coordenada.
- Validar payloads completos no main e Python: shape, IDs duplicados, booleanos, termos, tamanho e centavos seguros entre JS e Python.
- Definir política consistente para termos repetidos após renomeação. Proposta: impedir duplicata normalizada, preservando a identidade de cada regra existente durante migração.
- Falha ao salvar deve preservar dados digitados e restaurar somente a operação correspondente; não desfazer ações mais recentes por rollback antigo.
- Proteger exclusão da última regra e configuração com todas desativadas: bloquear início com explicação, sem inventar regra padrão na UI.

### TDD e aceite

- JSON truncado ou permissão negada mantém bytes originais e apresenta erro recuperável.
- Falha na substituição não destrói arquivo anterior; migração não substitui backup existente.
- Operações concorrentes não perdem alterações silenciosamente.
- Migração Electron/Python converge para o mesmo documento e IDs.
- Fixture não escreve nos arquivos reais; `.env` preserva chaves não editadas e segredos não aparecem nos erros.

Arquivos principais: `rules.py`, `bot.py` (grupos), `electron/electron/main.ts`, `electron/src/lib/rules-file.ts`, testes de persistência/migração. Extrair helpers pequenos de IO quando necessários.

## 7. E3 — Protocolo, diagnóstico e segurança

### Trabalho

- Acrescentar contrato de estado e snapshot da configuração efetivamente aplicada, com revisão/identificador e contagem de grupos/regras habilitadas. Comparar conteúdo salvo e aplicado; não depender somente de avisos locais do renderer.
- Decodificar stdout/stderr com UTF-8 incremental e remontar linhas entre chunks.
- Validar eventos em runtime por tipo/campos. Evento desconhecido é ignorado ou diagnóstico técnico; payload malformado nunca derruba o renderer.
- Limitar tamanho de linha e memória do buffer de protocolo; falhas de transporte/serialização devem ser diagnosticáveis.
- Emitir códigos úteis para sessão ocupada, autorização necessária, timeout, config inválida, storage indisponível e envio falho. Não classificar toda saída como crash genérico.
- Verificar origem/frame de quem invoca IPC, restringir navegação e criação de janelas, definir CSP compatível com dev/build e manter APIs mínimas no preload.
- Manter API Hash real no processo principal/Python; simulação e diagnóstico não devem exportar credenciais ou códigos de login.
- Incluir timestamp de origem e IDs de correlação dos eventos quando úteis; manter compatibilidade temporária com eventos existentes.

### TDD e aceite

Chunks cortados no meio de caractere acentuado ou JSON, linhas incompletas/grandes, tipos novos e payloads inválidos não corrompem o fluxo nem causam crash. IPC de origem não permitida é recusado. Snapshot diferencia configuração salva da aplicada e não contém segredos.

Arquivos principais: `electron/src/lib/ipc.ts`, `electron/electron/main.ts`, `electron/electron/preload.ts`, `electron/src/lib/activity.ts`, `bot.py`, `electron/index.html`.

## 8. E4 — Matching, preços, envio e estatísticas

### Trabalho

- Detectar regras correspondentes antes de extrair preços. Extração continua uma vez por mensagem relevante, com associação por regra/produto quando houver vários contextos.
- Evoluir a spec de preços antes do algoritmo: delimitação de produto/bloco, evidências da associação e motivo explícito de ambiguidade.
- Preservar formatos BRL, prioridade de `por`, tratamento de frete, parcelas pelo total, bordas inclusivas e first-eligible-only.
- Tratar FloodWait por exceção tipada e campo de segundos, sem procurar a palavra `wait` em qualquer erro. Verificar interação com espera automática da versão instalada do Telethon.
- Manter no máximo um retry explícito após FloodWait e nenhum fallback de regra após falha.
- Separar contadores: mensagens recebidas, duplicatas, correspondências, filtradas, simulações, envios confirmados e falhas. Contar envio somente após sucesso, inclusive retry.
- Medir duração com relógio monotônico; não apresentar duração negativa no retry. Diferenciar duração da chamada de envio de latência desde o recebimento.
- Tornar histórico explicável: elegibilidade e desfecho de envio são conceitos distintos; não deixar `reason=ok` como único diagnóstico de envio falho. Fazer evolução de schema compatível.
- Corrigir `< mínimo` e `> máximo` na atividade.
- Usar nomes já persistidos e resolver entidade sob demanda, sem bloquear registro do listener por chamadas sequenciais. Confirmar recuperação de mensagens durante reconexão/startup com deduplicação ativa.
- Revisar formatação de mensagens e links para tipos de grupo suportados; texto externo não deve quebrar o formato do alerta.

### Decisão de produto pendente

O preço mínimo da mensagem inteira não pode ser tratado como preço de cada keyword. Proposta para a primeira versão: associar somente quando o contexto do produto/preço for identificável pelas regras documentadas; com faixa e associação ambígua, não enviar e emitir `ambiguous_price`. Regras sem faixa mantêm o alerta por termo. Não usar proximidade de linha como promessa de associação correta sem corpus de aceite.

Essa política foi aprovada pelo usuário antes da implementação de E4 e documentada em SPEC-PRECO.md. A associação conservadora pode filtrar ofertas cujo formato não forneça vínculo suficiente.

### TDD e aceite

- `A57 R$ 2.500` + `Capa R$ 20` nunca aprova a faixa do A57 usando a capa.
- Mensagens com vários produtos, parcelas, frete, múltiplas regras e preço ausente têm decisão e motivo previsíveis.
- Erro comum não vira FloodWait; retry confirmado conta um envio; falha e dry-run contam zero envios.
- Testar o handler com TelegramClient falso e send falhando, além dos helpers puros.
- Restart/replay não reenvia mensagem marcada; registrar explicitamente a janela de perda aceita por at-most-once.

Arquivos principais: `price_parser.py`, `rules.py`, `storage.py`, `bot.py`, `docs/SPEC-PRECO.md`, `electron/src/lib/ipc.ts`, `electron/src/lib/activity.ts` e testes de parser/domínio/handler.

## 9. E5 — Grupos, regras, configuração e autenticação

### Trabalho e aceite de UI

1. **Cabeçalho operacional:** estado real visível com sidebar recolhida, contagens aplicadas, último processamento e último envio. Ausência de mensagens não significa desconexão; não marcar offline só por silêncio.
2. **Aplicação de mudanças:** aviso persistente quando a configuração salva diverge da aplicada; botão explícito para reiniciar e aplicar, reutilizando E1. Falha de reinício mantém aviso/diagnóstico.
3. **Grupos:** ações distintas para selecionar resultados e todos os grupos, com quantidade; checkbox nativo com estado misto; busca por nome/ID e opção de mostrar selecionados. Filtrar não modifica seleção.
4. **Estados vazios:** diferenciar lista ainda não carregada, falha de leitura, nenhum grupo disponível, nenhum selecionado e nenhum resultado. Cada estado apresenta a ação correspondente.
5. **Regras:** linhas compactas com termo, estado, faixa e prioridade; editar preserva ID. Controles subir/descer tornam a ordem explícita sem exigir drag-and-drop.
6. **Rascunhos:** indicador global de N alterações; salvar/descartar considera todos os rascunhos, mesmo se a regra aberta não estiver alterada ou se o editor estiver fechado. Exclusão falha não destrói o rascunho.
7. **Operações pendentes:** prevenir cliques duplicados em adicionar/salvar/excluir; manter texto digitado até sucesso; foco segue erro ou retorno da operação. Proteger fechamento da janela com rascunhos; trocar página preserva rascunhos.
8. **Simulador:** colar texto e usar o mesmo domínio Python por operação sem Telegram/lock de sessão/SQLite. Retornar avaliações, preços, associação, vencedora e motivo. Permitir simular rascunhos identificando-os como não salvos. Nenhum envio, migração ou marcação de `seen`.
9. **Configuração:** validação consistente nos dois lados, feedback de salvamento e distinção entre credenciais preenchidas e sessão autorizada. Não prometer troca de conta apenas por mudar PHONE com sessão antiga existente.
10. **Autenticação desktop:** quando necessária, conduzir código e 2FA com estados tipados, cancelamento e timeout. Autenticação deve ser dona exclusiva da sessão; código/senha ficam apenas em memória durante a operação. Não implementar troca destrutiva da sessão existente; orientar separadamente quando a conta configurada divergir.
11. **Fechar app:** informar de forma contextual que o monitor será encerrado; não afirmar que continuará em segundo plano sem tray implementado.

### TDD e arquivos

Testes de interação para seleção filtrada, save global, reorder, erros/rollback, preservação de rascunhos, cancelamento de autenticação e simulador sem efeitos. Não limitar cobertura aos helpers: montar os componentes com bridge IPC falsa usando recursos de teste apropriados ao projeto.

Arquivos: `electron/src/App.tsx`, `electron/src/lib/keywords.ts`, preload/IPC/main e operação Python pura de simulação/autenticação. Extrair páginas e componentes conforme forem alterados, mantendo a identidade visual existente.

## 10. E6 — Atividade, observabilidade e desempenho

### Trabalho

- Filtros por ofertas, enviados, filtrados e erros; busca por keyword/grupo e detalhes expansíveis com preço, regra, origem e desfecho.
- Preservar campos estruturados no modelo de atividade; não depender de procurar palavras em textos traduzidos para filtrar.
- Ao usuário subir a lista, pausar acompanhamento e indicar N novos eventos. Aplicar o mesmo comportamento ao modo técnico, com um único scroll owner por view.
- Copiar logs com confirmação e tratamento de falha. Redigir como exportação do buffer disponível, sem chamar isso de histórico completo. Remover ANSI no modo técnico.
- Separar estado do feed das páginas de edição. Agrupar eventos durante rajadas, preservando ordem, erros e estado terminal. Cancelar listeners/agendamentos no unmount.
- Manter buffers limitados; medir antes de adicionar virtualização ou store externo. Não introduzir memoização em massa sem evidência.
- Rotacionar `bot.log`. Proposta inicial: 5 arquivos de 5 MiB, com limites configuráveis e verificação de erro de disco.
- Definir retenção de `offers` e `seen` separadamente. Nesta execução, manter `seen` sem expiração automática; remoção pode reautorizar alertas antigos. Retenção destrutiva de `offers` depende de política aprovada; primeiro expor tamanho e instrução de manutenção.
- Evitar leitura síncrona repetida de JSON no filtro de sincronização; usar cache do snapshot carregado. Agregação deve contar canais efetivamente envolvidos, não todas as linhas do arquivo.

### TDD e aceite

Rajada sintética mantém ordem, limite de memória e responsividade de edição; rolagem manual não é interrompida; modo técnico acompanha corretamente. Navegação não apaga eventos. Rotação preserva os limites e reporta falhas. Medir antes/depois no mesmo cenário; virtualizar somente se os resultados justificarem.

Arquivos: `electron/src/lib/activity.ts`, páginas/hooks extraídos do App, `bot.py` e configuração de logs; `storage.py` somente após definição da manutenção.

## 11. E7 — Acessibilidade e acabamento

- Associar labels aos inputs, erros e instruções; usar `aria-invalid`, descrição de ajuda e anúncios pontuais de operação. Não anunciar o feed inteiro a cada evento.
- Navegação por teclado completa: seleção em massa, linhas, editor, prioridade, detalhes, ajuda e diálogos. Restaurar foco ao fechar editores/confirmar operações.
- Ajustar contraste de texto normal para pelo menos 4,5:1 e controles/foco conforme seu requisito aplicável. Texto branco no accent e texto discreto atual exigem revisão.
- Corrigir `lang` para `pt-BR`, título de documento e nomes acessíveis de botões; marcar a página atual na navegação.
- Centralizar tokens de cores/foco/estados e reduzir duplicação de estilos nos componentes alterados. Não converter todo o App por cosmética.
- Avaliar tamanho de fonte, zoom de 200%, janela menor e sidebar recolhida no contexto desktop Windows. Não transformar suporte mobile em requisito de distribuição.
- Preservar reduced-motion. O detector apontou transição de largura da sidebar; medir custo antes de classificá-la como gargalo e simplificar se necessário.
- Manter aparência escura e accent existentes, ajustando-os para legibilidade; redesign de marca não faz parte do plano.

Aceite: percurso completo por teclado, foco visível, nomes/erros acessíveis, ausência de perda de função com zoom/janela reduzida e inspeção visual em execução. Resultados estáticos não substituem essa validação.

## 12. E8 — Build, documentação e entrega

- Verificar caminhos de `loadFile`, preload e recursos Python na árvore compilada; revisar URLs de assets do Vite para carregamento local.
- Verificar compatibilidade CommonJS/ESM dos helpers emitidos e imports do main, não somente a existência de `main.cjs`.
- Tornar o build explícito sobre falhas de compilação e renomeação. Conferir `dev:electron` em checkout limpo, sem depender de build antigo.
- Separar arquivos graváveis do usuário dos recursos da aplicação para distribuição; definir migração com preservação dos dados existentes antes de mudar paths. Python no PATH versus runtime empacotado deve constar da spec de distribuição.
- Validar abertura do build local com dados isolados. Instalador público, assinatura, publicação e auto-update não são entregas implícitas deste plano.
- Atualizar README, arquitetura, regras e produto para refletir IPC/JSONL, preços v2, SQLite, autenticação, reinício e parada. Remover orientações destrutivas e referências de TUI que não se aplicam.
- Revisar exclusões de artefatos sensíveis: `seen.db`, journals/WAL/SHM, backups com dados e arquivos temporários. Não assumir que `.gitignore` elimina dados já versionados.

Aceite: build reproduzível abre renderer/preload, operações isoladas chegam ao Python e falhas são apresentadas. Instruções permitem configurar, autenticar, iniciar, diagnosticar e parar sem conhecimento do código.

## 13. Estratégia de verificação

1. Escrever primeiro os testes do comportamento da etapa e comprovar a falha relevante.
2. Implementar e executar somente a seleção necessária de pytest/Vitest; usar temporários, processo fake e cliente Telegram falso.
3. Para bugs de processo/IO/protocolo, incluir integração real entre componentes locais isolados; helpers sozinhos não bastam.
4. Verificar TypeScript, lint e build nas etapas que os alterarem. Ampliar regressão quando mudanças ou falhas justificarem, sem repetições automáticas da suíte inteira.
5. Antes de qualquer execução de testes, atender à instrução do usuário de `php artisan config:clear` quando houver aplicação Laravel aplicável. Este workspace não tem `artisan`; registrar a inaplicabilidade, sem criar Laravel ou rodar o comando em outro projeto como substituto.
6. Validação visual em app com bridge/dados de teste, sem Playwright. Testes automatizados não devem autenticar, enviar mensagens ou consumir a sessão real.
7. Smoke manual com Telegram real é uma etapa separada: precisa de grupo de teste e autorização explícita para autenticação/envio. `dry-run` real também altera `seen`, portanto não equivale a inspeção sem efeitos.

## 14. Decisões a fechar no momento apropriado

| Decisão | Proposta | Bloqueia |
|---|---|---|
| Preço ambíguo/múltiplos produtos | Filtrar regras com faixa quando não houver associação inequívoca; explicar motivo | Algoritmo E4 |
| Volume/idade de histórico | Rotacionar logs; não expirar `seen`; política de exclusão de offers separada | Somente limpeza destrutiva E6 |
| Distribuição | Validar build local primeiro; definir runtime Python e paths antes de empacotar | Empacotamento E8 |
| Conta diferente da sessão existente | Não substituir/apagar sessão automaticamente; fluxo específico preservando dados | Troca de conta, não monitoramento da conta atual |
| Termos duplicados após edição | Rejeitar duplicata normalizada, com diagnóstico e migração sem descarte silencioso | Validação final de regras E2 |

O restante do trabalho pode avançar sem transformar essas escolhas em uma rodada geral de perguntas. Nenhuma proposta desta tabela deve ser apresentada como decisão já aprovada.

## 15. Definição de conclusão

- Todas as etapas têm critérios demonstrados, alterações revisáveis e limitações registradas.
- A interface distingue processo criado, conexão, autorização e monitoramento ativo.
- Exclusividade da sessão e integridade de arquivos são exercitadas em condições de falha/concorrência.
- Regras e preços são explicáveis e compatíveis com a spec aprovada; nenhum alerta herda preço de outro produto silenciosamente.
- Testes reproduzem falhas de integração, não somente decisões de helpers.
- Build e interface são verificados com dados isolados; dependências de validação real estão explicitadas.
- Não há commit, push, publicação ou alteração da conta real como efeito implícito do planejamento.
