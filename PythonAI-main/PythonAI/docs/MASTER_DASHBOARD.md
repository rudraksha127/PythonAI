# Master Tool Dashboard

Last updated: 2026-05-25

## Local tool clones (tools/)

| Tool                    | Purpose                                      | Path                          | Version                         | Run or setup                                                 | Notes                                                                                                                      |
| ----------------------- | -------------------------------------------- | ----------------------------- | ------------------------------- | ------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------- |
| BrainGrid               | AI product planning CLI and IDE integrations | tools/braingrid               | npm @braingrid/cli (see README) | npm install -g @braingrid/cli                                | Setup: braingrid setup claude-code or braingrid setup cursor. Quickstart: braingrid init, braingrid specify --prompt "..." |
| Claude Code             | Terminal coding agent                        | tools/claude-code             | Installer-managed               | Windows install: irm https://claude.ai/install.ps1           | iex. Run: claude                                                                                                           | npm install is deprecated in README |
| Claude plugins official | Plugin directory for Claude Code             | tools/claude-plugins-official | n/a                             | Install via /plugin install {plugin}@claude-plugins-official | Includes /plugins and /external_plugins                                                                                    |
| Dyad                    | Local AI app builder                         | tools/dyad                    | 1.1.0-beta.1                    | Download from https://www.dyad.sh/#download                  | Open source desktop app; repo includes electron dev scripts                                                                |
| Paperclip               | Agent orchestration control plane            | tools/paperclip               | n/a (private package)           | pnpm install; pnpm dev                                       | Requires Node.js 20+ and pnpm 9.15+                                                                                        |

## Researched but not installed

| Tool                         | Purpose                                     | Install or setup                                                    | Status                     |
| ---------------------------- | ------------------------------------------- | ------------------------------------------------------------------- | -------------------------- |
| Gstack                       | Claude Code skill pack                      | Install via repo under ~/.claude/skills/gstack or run setup in repo | Not installed in workspace |
| Hallmark                     | Design skill for Claude Code, Cursor, Codex | npx skills add nutlope/hallmark                                     | Not installed in workspace |
| Happenstance                 | AI-assisted collaboration platform          | No install steps in README                                          | Not installed in workspace |
| Browser Control Agent v0.7.6 | Browser automation agent binary             | Repo or release asset not confirmed yet                             | Pending repo selection     |

## Notes

- Local tool clones are under tools/ and are tracked in this dashboard only when present in the workspace.
- If you want version pinning, add a column for commit hash or tag after confirming the preferred repos.
