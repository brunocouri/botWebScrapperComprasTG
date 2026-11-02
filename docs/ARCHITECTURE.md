# Arquitetura atual — ComprasTG

```text
React -> preload -> Electron IPC -> bot.py -> Telethon/Telegram
React <- bot:event <- eventos JSONL stdout / logs stderr
React -> IPC -> config_cli.py -> Configuration -> JSON / .env
```

Não existe servidor FastAPI operacional. `backend/app/*` é um esqueleto e `shared/ipc.schema.json` é um rascunho legado.

## Módulos e fronteiras

| Módulo | Responsabilidade |
|---|---|
| bot.py | CLI, sessão, conexão, autenticação, listener, envio e eventos |
| runtime_safety.py | Lock do SO e substituição atômica de arquivos |
| configuration.py | Configuração coordenada, validação, migração e revisões |
| config_cli.py | Operações JSON sem Telegram/bancos; simulador usa o domínio puro |
| rules.py / price_parser.py | Matching, preços, associação e primeira vencedora elegível |
| storage.py | seen de integridade e offers best-effort, com desfecho separado de elegibilidade |
| electron/electron/main.ts | Fronteira IPC, processos, origem/navegação e shutdown |
| electron/src/lib/process.ts | Propriedade do filho até close/error; parada cooperativa e fallback |
| electron/src/lib/protocol.ts | UTF-8 incremental, limite de linha e validação runtime |
| electron/src/lib/ipc.ts | Fonte de verdade dos contratos |
| electron/src/lib/feed-store.ts | Buffer limitado atualizado em lotes |
| electron/src/features/Activity.tsx | Filtros, detalhes, cópia e acompanhamento |
| electron/src/App.tsx | Shell, grupos, regras, simulador, configuração e autorização |

## Consistência

Watch, listagem e autenticação adquirem a mesma trava antes de abrir a sessão. O SO libera o lock após morte abrupta. O arquivo permanece para não trocar inode durante concorrência. Locks PID da versão antiga são tratados conservadoramente.

Configuração usa outra trava curta, com espera limitada. Saves exigem a revisão lida; conflitos não são sobrescritos. Arquivo inválido nunca vira lista vazia. CLI e Electron compartilham a migração v2 e seus IDs estáveis.

O monitor carrega regras, grupos, credenciais e digest aplicado sob a mesma exclusão. Mudanças posteriores só entram no reinício. O renderer recebe contagens e digest, nunca credenciais desse snapshot.

## Monitoramento

Handler registrado antes da conexão e recuperação. catch_up preserva mensagens perdidas e o replay passa pela deduplicação. Nomes persistidos evitam consultas sequenciais de entidades no startup.

Pipeline: check seen -> matching/avaliação -> claim -> filtrados e um envio/dry-run. Falha da vencedora não promove outra regra. FloodWait é tipado, com um retry explícito; espera automática do cliente desativada para não somar políticas.

Estado de processo, conexão e monitoramento são distintos. Estatísticas não contam dry-run/falhas como envios confirmados. Silêncio dos grupos não é desconexão.

## Segurança e build

Renderer sem Node, com contextIsolation e sandbox. IPC verifica webContents/frame/origem; navegação e novas janelas bloqueadas; abertura externa com allowlist. CSP separa necessidades de desenvolvimento do build.

Código e senha 2FA transitam por stdin, sem argv, persistência ou eventos. Erros de SDK não ecoam credenciais. API Hash no renderer é apenas máscara.

Vite usa assets relativos; dist-electron tem pacote CommonJS próprio para main/preload/helpers. npm start abre o renderer compilado. O build local requer Python no PATH e não é um instalador autossuficiente. Runtime Python empacotado e migração de diretórios são decisões futuras de distribuição.
