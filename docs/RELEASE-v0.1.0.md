# ComprasTG v0.1.0

Primeira publicação pública do desktop e CLI para monitoramento de ofertas no Telegram.

## Funcionalidades

- Autorização da conta Telegram, seleção de grupos e canais e monitoramento via Telethon.
- Regras por palavra-chave, faixa de preço e prioridade, com simulador local.
- Alertas em Mensagens Salvas, deduplicação persistente e painel de atividade.
- Catálogo opcional com coleta, modelos declarativos, revisão, busca, reprocessamento e alertas estruturados.
- Execução por Electron ou CLI e parada cooperativa do monitor.

## Instalação

Baixe `ComprasTG-v0.1.0-source.zip`, extraia e siga o [README](https://github.com/brunocouri/botWebScrapperComprasTG/blob/v0.1.0/README.md).

O pacote contém código-fonte. Requer Python e Node.js no PATH, instalação das dependências e build local. Não inclui instalador Windows nem Python embutido. Credenciais, sessão, configurações pessoais e bancos não são distribuídos.

## Limites conhecidos

- Fechar a janela encerra o monitor; bandeja e inicialização automática não estão implementadas.
- Alterações de configuração exigem reinício do monitor.
- Preços ambíguos são filtrados quando a regra exige faixa.
- `--dry-run` não envia alertas, mas marca mensagens como vistas.
- A deduplicação anterior ao envio evita repetição, mas uma queda entre essas etapas pode perder o alerta.
- Autenticação e entrega reais no Telegram dependem de validação manual com a conta do usuário.

Consulte o [manual do usuário](https://github.com/brunocouri/botWebScrapperComprasTG/blob/v0.1.0/docs/MANUAL-USUARIO.md) e o [guia do catálogo](https://github.com/brunocouri/botWebScrapperComprasTG/blob/v0.1.0/docs/GUIA-CATALOGO.md).

## Validação desta publicação

- 45 testes Python selecionados: segurança, regras e padrões do catálogo.
- 26 testes Vitest selecionados: protocolo, ciclo de vida, arquivos de regras e atividade.
- Build TypeScript/Vite/Electron, lint e smoke test aprovados.
- Smoke com dados temporários, sem autenticação ou envio ao Telegram.
- Revisão dos arquivos publicados para exclusão de credenciais, dados pessoais e artefatos locais.
