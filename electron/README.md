# Desktop ComprasTG

Instale requirements.txt na raiz e mantenha Python no PATH. Neste diretório:

```powershell
npm ci
npm run build
npm start
```

Desenvolvimento: npm run dev:electron compila main/preload antes de iniciar Vite na porta 5173. Não use uma instância de outro projeto nessa porta; ela é a origem autorizada do renderer em desenvolvimento.

npm run smoke verifica o build compilado em janela oculta com arquivos temporários. Não autentica, não envia e não abre session.session/seen.db. Execute o build antes do smoke.

npm run lint verifica somente fontes. Testes usam Vitest/Testing Library/happy-dom e devem ser selecionados conforme a mudança. Não usar Playwright.

O contrato está em src/lib/ipc.ts. O build local requer Python. Dados de desenvolvimento ficam na raiz do projeto, salvo COMPRAS_DATA_DIR.

Distribuição Windows x64: `npm run package:win` gera instalador e ZIP em ../artifacts/windows, incluindo Python embutido. Requer Python 3.14 para preparar o runtime. `npm run smoke:packaged` valida o EXE sem Python/Node no PATH. No aplicativo distribuído, os dados ficam em `%APPDATA%\ComprasTG\data`.

Consulte ../README.md e ../docs/IMPLEMENTACAO-MELHORIAS.md.
