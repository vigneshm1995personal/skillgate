# Skill Gate dashboard

Vite + React + shadcn app. Local mode is served by `skillgate ui` from `web/dist` at http://127.0.0.1:8765. No account.

```bash
pnpm install
pnpm test
pnpm build
```

Then from the repo root: `skillgate ui`. During development, `pnpm dev` proxies `/api` to port 8765. See [`docs/ui.md`](../docs/ui.md).
