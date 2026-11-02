# SPEC-PREÇOS — Detecção de preços e regras por keyword

## Atualização aprovada — associação e preço ambíguo (29/10/2026)

O usuário aprovou não enviar quando a associação de produto/preço for ambígua nas regras com faixa. Esta seção prevalece sobre o decisivo global por mensagem e a observação antiga sobre falha de seen nas seções históricas abaixo.

- O matching de regras ocorre antes da extração; mensagem sem termo correspondente não executa o parser.
- Ocorrências preservam índice de linha (zero-based no payload). A avaliação informa evidências de associação com linhas numeradas a partir de 1 para apresentação.
- Preços na mesma linha da keyword são evidência direta. Linhas seguintes exclusivamente de pagamento podem complementar o contexto; outra descrição ou quebra de bloco encerra essa continuação.
- Sem preço direto, uma linha de preço de outro produto não herda a keyword. Múltiplos valores atuais distintos sem vínculo seguro são ambíguos. Palavras como ou/Pix não comprovam que dois valores pertencem ao mesmo produto.
- Referência de, frete e parcela preservam seus papéis; a comparação de parcela usa total. Bordas continuam inclusivas.
- Com faixa e associação ambígua: eligible=false, reason=ambiguous_price, sem envio. A atividade mostra Preço ambíguo.
- Sem faixa: preservar alerta por termo, mas não atribuir preço decisivo se ambíguo.
- A associação é conservadora e determinística, não um classificador semântico. A keyword em uma descrição de acessório ainda é um match; configure faixa mínima quando necessário. Formatos não cobertos podem gerar filtragem conservadora.
- O simulador chama o mesmo evaluate, inclusive com rascunhos, sem conectar ao Telegram, migrar arquivos ou marcar seen.
- Falha em seen impede efeitos; somente offers é best-effort. Histórico tem delivery_status e delivery_error separados de reason, com migração aditiva.

Casos de aceite: A57 R$ 2.500 seguido de Capa R$ 20 não aprova faixa usando a capa; valores sem associação retornam ambiguous_price; de/por/Pix/parcelas/frete mantêm as regras anteriores em contexto inequívoco. Testes em tests/test_product_prices.py e tests/test_monitor_runtime.py.

---

**Status:** D1–D6 aprovadas; implementação original F1–F5 evoluída pela atualização acima. A referência histórica abaixo deve ser lida com essas correções.
**Objetivo:** ao detectar keyword, extrair preços da mensagem, avaliar contra regra da keyword (min/max/ativa) e só alertar ofertas elegíveis — sem mudar o comportamento atual para regras sem faixa.

---

## 0. Não-objetivos (fora desta spec)

- Comparar preços entre grupos, histórico de queda de preço, ranking de ofertas.
- Converter moeda estrangeira (só BRL).
- OCR em imagem (só texto/legenda da mensagem).
- Compra automática, reserva, clique em link.

## 1. Extração de preços (PriceParser — puro, sem Telegram)

**Âncora obrigatória:** marcador explícito de moeda (`R$`, `RS`, `$` com gramática BR, `reais`/`real`). Número sem âncora e sem propagação **não** é preço (`A57 1899`, `128GB`, `5G`).

**Propagação contextual (D1 ajustada):** numa construção `de A por B` / `A por B` **na mesma linha**, se um dos lados tem âncora o outro herda a gramática BR:
- `de R$ 2.499 por 1.899` → `[{249900, de}, {189900, por}]`
- `R$ 2.499 por 1.899` → idem (lado esquerdo sem "de" assume papel de referência, `kind=de`)
- `de 2.499 por R$ 1.899` → idem
- `por 1.899` sozinho (sem par, sem âncora) → **não** é preço (regra estrita)
- Prefixo de parcela `Nx` também ancora: `12x 189,90` → parcela mesmo sem `R$`
- `de` solitário + número **com separador** (ponto ou vírgula) vira referência: `só de 2.499` → `[{249900, de}]`. Bare sem separador (`de 2023`) não entra — evita ano virar preço

**Escopo:** pareamento, propagação e contexto de `kind` operam **por linha** (`\n`); entradas de todas as linhas são mescladas. Par quebrado entre linhas é limitação conhecida.

**Ordem de parsing** (por linha, consumindo spans para não contar 2x):
1. Parcelas `Nx [de] número` (`de` entre quantidade e valor é opcional: `12x de R$ 189,90` ≡ `12x R$ 189,90`; número com ou sem âncora — o `Nx` ancora).
2. Pares `de A por B` / `A por B` (≥1 lado ancorado; o outro propaga).
3. Avulsos ancorados (`R$ X`, `X reais`), com detecção de frete (abaixo).

**Ignorados explicitamente:** moeda estrangeira (`US$`, `USD`, `dólar`, `euro` — sem conversão); valores por extenso ("2 mil"); zero/`grátis`. Parser nunca lança exceção em entrada estranha (robustez: ignora o trecho).
**Limitação conhecida:** parcelamento sem `Nx` (`em 12 parcelas de R$ 189`) cai como `avulso` (âncora só no valor) — sem `total_cents`. Revisitar após amostragem real se frequente.

### 1.1 Formatos e normalização (**centavos inteiros**, nunca float)

| Exemplo real | cents |
|---|---|
| `R$ 1.899,00` | 189900 |
| `R$1899,99` | 189999 |
| `RS 1.899` / `R$ 1899` | 189900 |
| `$ 1.899,00` / `1899 reais` | 189900 |
| `12x R$ 189,90` | parcela 18990 (total 227880, ver 1.3) |

- Gramática sempre BR (`.` milhar, `,` decimal), inclusive no lado propagado (`1.899` → 189900).
- Regex base (conceitual): marcador + `(\d{1,3}(?:\.\d{3})*,\d{2} | \d+,\d{2} | \d{1,3}(?:\.\d{3})+)`.

### 1.2 Entradas (PriceEntry)

`{ cents, kind, raw, installments?, installment_cents?, total_cents? }`, `kind ∈ { por, vista, parcela, de, avulso, frete }`:
- `parcela`: `cents` = valor da parcela; `installments` = N; `installment_cents` = cents; `total_cents` = N×cents (D4: estrutura sempre preservada).
- `de`: referência, **nunca decisivo sozinho**.
- `vista`: marcador (pix/à vista/boleto) na mesma linha; senão `avulso`.
- `frete`: custo acessório reconhecido em contexto local forte (`frete R$`, `frete: R$`, `+ frete R$`, `envio R$`, `R$ X de frete`); **preservado nas ocorrências, excluído da disputa do decisivo**. Sem adjacência não contamina (`frete grátis · A57 R$ 1.899` mantém o produto intacto).

### 1.3 Decisivo (um por mensagem)

`Decisive = PriceEntry | null` — a entrada vencedora, **origem/kind preservados** (não só cents). Valor de comparação: `total_cents` se parcela, senão `cents`.
Prioridade: **`por` > `vista`/`avulso` (menor cents entre eles) > total de `parcela`**. Empate de prioridade → menor cents (viés caçador). `frete` nunca compete.
- Só-`de`, só-`frete` ou sem preço → `decisive = null` (ver elegibilidade em §3: com faixa, `no_price`).

## 2. Regras por keyword (config)

### 2.1 Modelo

```json
{
  "version": 2,
  "rules": [
    { "id": "a57-3f9a", "term": "A57", "enabled": true, "min_cents": null, "max_cents": 189900 },
    { "id": "galaxy-71c2", "term": "Galaxy", "enabled": true, "min_cents": null, "max_cents": null }
  ]
}
```

- `id`: **identidade estável e imutável**, gerada uma vez na criação/migração (`slug(term) + "-" + 4 hex aleatórios`, ex. `a57-3f9a`); **nunca recalculada**. Renomear `term` preserva `id` e a continuidade do histórico. Nunca exibido na UI. Unicidade validada no save (Electron); em load com duplicata, mantém a primeira e loga `[AVISO]`.
- `term`: editável; casa exatamente como hoje. Renomear não quebra nada (match usa `term` atual, histórico usa `id`).
- `enabled: false` ≡ termo fora da lista (sem match, sem log de match).
- `min_cents`/`max_cents` opcionais (`null` = sem limite). Semântica: alerta se `min ≤ decisivo ≤ max` (bordas inclusivas, D2 aprovada).

### 2.2 Migração v1 → v2 (automática, com backup)

- `keywords.json` atual (`["A57"]`) = **v1 implícito**. Na primeira leitura com regras: cria `keywords.json.bak`, escreve v2 com `enabled: true`, limites `null` e **`id` estável gerado por termo** (comportamento 100% preservado).
- **Ordem do array = ordem de avaliação = prioridade** da política first-only (D6). Reordenar regras muda qual alerta prevalece; UI futura pode expor reorder, fora desta spec.
- Leitura tolerante: string solta dentro de `rules` ou arquivo v1 ainda carrega como regra sem faixa (nunca quebrar por formato).

## 3. Avaliação — `evaluate()` v2 (pura)

Uma avaliação **por regra correspondente** (term casa + `enabled`); extração de preços roda **uma vez por mensagem**, elegibilidade é por regra:

```
evaluate(text, rules) -> list[Evaluation]   # [] = sem match (igual a hoje)
Evaluation = { rule_id, keyword(term atual), prices[], decisive: Decisive|null, eligible: bool, reason }
Decisive = PriceEntry  # origem/kind preservados; comparação usa total_cents se parcela
```

- Regra desabilitada → nenhuma avaliação (como se ausente).
- `eligible`:
  - regra sem `min`/`max` → `true` (**comportamento atual preservado**);
  - com faixa e `decisive != null` → `min ≤ comparação ≤ max` (D2: bordas inclusivas);
  - com faixa e `decisive == null` → `false`, `reason: "no_price"` (D3 aprovada).
- `reason ∈ { ok, above_max, below_min, no_price, superseded }` (`superseded` = elegível mas suprimida pela política multi-regra, ver decisão 6).
- `evaluate_message()` continua existindo como helper de compat (testes atuais passam); o handler usa `evaluate()`.
- Pura: sem Telegram, envio, log, arquivo ou Electron. Toda regra nova futura entra aqui, nunca no handler.

## 4. Protocolo JSONL (extensão mínima)

Campos novos são **opcionais**; renderer antigo ignora sem quebrar:

- `keyword_matched` += `prices[]` (entradas completas §1.2), `decisive: {cents, kind, installments?, installment_cents?, total_cents?} | null`, `eligible: bool`, `rule_id`, `reason`
- `alert_sent` / `dry_run_detected` += `decisive` (mesmo objeto, para exibir origem e total da parcela)
- Novo `rule_filtered { keyword, group_id, message_id, decisive | null, bounds: {min_cents, max_cents} | null, reason }` — match **não elegível** (transparência: aparece na Atividade como "fora da faixa", nunca no Salvos, nunca no badge)
- Handler (D6: first-eligible-only em ordem das rules): vencedora `eligible && !dry_run` → envia Salvos (`alert_sent`); vencedora `&& dry_run` → `dry_run_detected`; `!eligible` ou suprimida → **só** `rule_filtered`, sem envio e **sem** `keyword_matched` (um evento por avaliação, nunca dois). Falha no envio da vencedora **não** promove outra regra (at-most-once, ver §5).

Texto do alerta no Salvos ganha 1 linha (sem mudar o resto do formato): `Preço: R$ 1.899,00 (à vista)` — ou `12x de R$ 189,90 (total R$ 2.278,80)` quando o decisivo for parcela. (Formatação exata definida na implementação; spec exige só a presença + origem.)

## 5. Deduplicação persistente + histórico (spec de dados)

Fica no Python, atrás de funções puras/testáveis; Electron não acessa direto. Duas persistências com garantias **diferentes**:

- `seen` = **integridade** (garantia anti-duplicata no replay do `getDifference` após restart).
- `offers` = **best-effort** (histórico para fases futuras; falha de disco nunca bloqueia alerta).
- `seen.db` (sqlite, ao lado de `session.session`):
  - `seen(chat_id INTEGER, msg_id INTEGER, PRIMARY KEY (chat_id, msg_id))` — substitui o `set` em memória.
  - `offers(id INTEGER PK, chat_id, msg_id, rule_id, keyword, decisive_json NULL, prices_json, sent INTEGER, reason TEXT, created_at)` — `sent` registra o desfecho (1 enviado, 0 filtrado/falha); `reason` espelha a avaliação. Uma linha por avaliação com efeito (inclui `superseded`).
- Migração: na primeira execução, `seen` começa vazio (aceita-se um re-alerta único de mensagens recentes após o restart que ativar isso).

**Ordem do pipeline por mensagem (obrigatória):** `check seen → evaluate → mark seen (1x por mensagem, não por avaliação) → efeitos (send | rule_filtered | nada)`.
- `mark` **antes** do send (at-most-once, igual ao código atual): crash entre mark e send pode perder 1 alerta; nunca duplica no replay.
- Falha de envio (não-FloodWait): já marcado → sem retry futuro; emite `error` + linha `offers(sent=0)` best-effort.
- FloodWait: retry 1x preservado; falha final → `error` + `offers(sent=0)`.
- Falha ao gravar `seen`/`offers`: log `[AVISO]`, nunca bloqueia o alerta.
- `dry_run` também marca `seen` (evita re-log em replay).

## 6. UI Electron (mudanças mínimas)

- Página Keywords: cada chip expande editor inline — switch `Ativa`, `Preço mín.` e `Preço máx.` (inputs com máscara BRL `R$ _. ___,__`, gravam centavos), validação `min ≤ max`, erro inline. Usa o padrão existente: dirty → Salvar/Descartar, await+revert+erro, aviso "próxima inicialização" com bot rodando (já implementado).
- Tipos `ipc.ts`: `Rule { id, term, enabled, min_cents: number|null, max_cents: number|null }`; `keywords:get/save` passam a `Rule[]` (com tolerância de leitura a `string[]` legada no main). `id` nunca exibido; rename de `term` preserva `id`.
- Atividade: `Oferta encontrada · A57 · R$ 1.899` (quando houver decisivo); `Fora da faixa · A57 · R$ 2.499 > máx R$ 1.899` para `rule_filtered` (com `bounds` do evento); `superseded` → `Já alertada por outra regra` (genérico, sem vencedor no schema); badge de erro **não** conta filtrados.
- Sem novas páginas, sem redesign, sem Tailwind em massa (só se o editor precisar de componente novo).

## 7. Testes de aceite (mínimos, todos sem Telegram)

Parser: `R$ 1.899,00`→189900 · `RS1899,99`→189999 · `12x R$ 189,90`→parcela{installments:12, total:227880} · `12x 189,90` (sem âncora)→idem via Nx · `de R$ 2.499 por 1.899` / `R$ 2.499 por 1.899` / `de 2.499 por R$ 1.899`→ambos reconhecidos, decisive=por · `por 1.899` sozinho→[] · `128GB / 5G / A57 1899`→[] · `US$ 100`→[] · `só de 2.499`→decisive null.
Regras: sem faixa→eligible · `max=189900` + decisive 189900→ok (borda inclusiva) · +1 centavo→`above_max` · `min` análogo · `decisive null`+faixa→`no_price`/inelegível · `enabled:false`→[] (nenhuma avaliação) · msg casando 2 regras→2 avaliações em ordem das rules · rename de `term` preserva `id` · v1 `["A57"]` migra para v2 equivalente com `id` estável.
Decisivo: objeto com `kind` preservado (`por`/`vista`/parcela+totais); comparação usa `total_cents` se parcela.
Protocolo: `keyword_matched` com/sem campos novos parseia; tipo desconhecido→null sem crash (teste existente cobre o mecanismo).
E2E manual: msg com preço dentro da faixa→Salvos com linha de preço; fora→só Atividade; restart→sem re-alerta (seen.db).

## 8. Fases de implementação (ordem)

1. **F1 — parser + testes** (`price_parser` puro + casos §7). Sem tocar em handler/protocolo/UI.
2. **F2 — regras + migração** (modelo §2, `evaluate()` §3 + testes; `evaluate_message` mantido).
3. **F3 — protocolo + handler** (eventos §4; envio só se elegível; texto do alerta; política D6 + testes: 1 elegível→vence · 2 elegíveis→1ª vence/2ª `superseded` · 1ª inelegível+2ª elegível→2ª vence · todas inelegíveis→sem vencedora · 1ª disabled→não participa · reorder→muda vencedora deterministicamente · dry-run = mesma vencedora).
4. **F4 — seen.db + offers** (§5, ordem check→evaluate→mark→efeitos).
5. **F5 — UI** (editor por keyword, tipos IPC, mapeamentos Atividade).

## 9. Decisões

- **D1 — âncora + propagação: APROVADA COM AJUSTE.** Âncora explícita obrigatória; propagação só em par `de/por` na mesma linha com ≥1 lado ancorado, mais prefixo `Nx` como ancorador. `por 1899` sozinho e `A57 1899` não são preço.
- **D2 — bordas inclusivas: APROVADA** conforme proposta.
- **D3 — `de`-só com faixa inelegível (`no_price`): APROVADA** conforme proposta.
- **D4 — decisivo de parcela: APROVADA COM AJUSTE.** Só-parcelamento → decisivo = N×parcela; vista/Pix/`por` têm prioridade; estrutura sempre preserva `installments`, `installment_cents`, `total_cents`.
- **D5 — filtrado visível na Atividade (sem badge): APROVADA** conforme proposta.
- **D6 — first-eligible-only por mensagem: APROVADA.** A ordem de `rules[]` define prioridade. Após `evaluate()` retornar todas as avaliações: (a) a primeira com `eligible=true` é a vencedora; (b) no máximo **um** alerta por `chat_id + message_id`; (c) outras avaliações elegíveis tornam-se `superseded`; (d) inelegíveis preservam o motivo real (`above_max`, `below_min`, `no_price`); (e) `superseded` = exclusivamente "seria elegível, mas outra regra de maior prioridade venceu". Exemplo: `Galaxy` eligible + `A57` eligible + `256GB` above_max → Galaxy alerta, A57 `superseded`, 256GB `above_max`. Todas as avaliações são preservadas para protocolo/histórico, mas só a vencedora produz efeito externo. `dry_run` usa exatamente a mesma seleção (só troca o envio pelo evento); semânticas de matching idênticas. Mensagem sem elegível não alerta.
