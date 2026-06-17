# ForgeAI Monorepo

This workspace is organised as a two-namespace monorepo.

## Layout

```
forgeai-core/     — Primary ForgeAI product
  backend/        — Python source (formerly PythonAI/src/)
  api/            — REST API layer (formerly PythonAI/src/api/)
  frontend/       — Next.js dashboard (formerly dashboard/)
  database/       — Data stores and vector databases
  tests/          — Test suite (formerly PythonAI/tests/)
  configs/        — Config files, Dockerfile, Makefile, pyproject.toml
  docs/           — Documentation (formerly PythonAI/docs/)
  html/           — Built frontend (formerly dashboard/out/)
  extension/      — VS Code extension (formerly PythonAI/vscode-extension/)
  scripts/        — Utility scripts (formerly PythonAI/scripts/)

external-tools/   — Satellite tool repositories
  hermes/         — hermes-agent-main
  open-claude/    — open-claude-main
  codebuff/       — codebuff-main
  ruflo/          — ruflo (fresh/ subdirectory = ruflo-fresh)
  rudra-bots/     — Rudra-bots-main
  claude-code/    — Claude_Code_npm-main
  skills/         — skills-main
  kronos/         — Kronos-master
  odysseus/       — odysseus

arsenal/          — Reference collection (UNTOUCHED)
```

## Getting Started

See `forgeai-core/README.md` for core product instructions.
