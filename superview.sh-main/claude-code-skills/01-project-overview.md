# Project Overview

## What is Claude Code?

Claude Code (`@anthropic-ai/claude-code`) is an interactive AI-powered coding assistant that runs as a CLI application in the terminal. It provides a REPL (Read-Eval-Print Loop) interface where users can have conversations with Claude to write, edit, debug, and understand code.

## Technology Stack

### Runtime & Language
- **TypeScript** — The entire codebase is written in TypeScript with strict type checking
- **Node.js** — Runtime environment (ESM modules, `"type": "module"` in package.json)
- **Bun** — Used internally for feature flags (`bun:bundle`) and dead code elimination; not the runtime for end users

### Build System
- **esbuild** — Transpile-only (no bundling). The build script (`build.mjs`) handles:
  - TypeScript/TSX → JavaScript transpilation
  - `bun:bundle` and `bun:ffi` shim generation
  - Bare `src/` import rewriting to relative paths
  - `.jsx` extension fixing for React components
  - `.d.ts` import stripping
  - Empty stub generation for missing internal modules
  - Runtime shims for internal packages

### UI Framework
- **Ink** — React for the terminal. Claude Code uses Ink to render its terminal UI
- **React** — Components use React patterns (hooks, JSX, functional components)
- **React Compiler** — Some UI files use `react/compiler-runtime` for memoization

### Schema Validation
- **Zod v4** — Used extensively for:
  - Tool input/output schema definitions
  - Hook response validation
  - Configuration parsing
  - Runtime type validation

### Key Dependencies
- **`@anthropic-ai/sdk`** — Anthropic's official SDK for API communication
- **`lodash-es`** — Utility library (always cherry-picked imports, never full import)
- **`chalk`** — Terminal string styling
- **`commander`** — CLI argument parsing
- **`diff`** — Diff generation for file edits
- **`globby`** — File globbing
- **`marked` / `marked-terminal`** — Markdown rendering in terminal
- **`strip-ansi`** — ANSI escape code stripping
- **`zod/v4`** — Schema validation (note: imported from `zod/v4`, not `zod`)

### Feature Flags & Dead Code Elimination
The codebase uses a feature flag system via `bun:bundle`:

```typescript
import { feature } from 'bun:bundle'

// At build time, feature('FLAG') resolves to true/false
// enabling dead code elimination of entire code paths
if (feature('PROACTIVE')) {
  // This entire block is removed from builds where PROACTIVE is false
}
```

Common feature flags include:
- `PROACTIVE` — Proactive/autonomous agent features
- `REACTIVE_COMPACT` — Reactive compaction strategy
- `TRANSCRIPT_CLASSIFIER` — Auto permission mode
- `HARD_FAIL` — Development crash-on-error mode
- `PROMPT_CACHE_BREAK_DETECTION` — Cache break monitoring

### Internal vs External Builds
- **External users** — Standard Node.js runtime, feature flags control available features
- **Internal users (`ant`)** — `process.env.USER_TYPE === 'ant'` enables additional debugging, error logging to disk, and internal-only commands
- **Cloud providers** — Bedrock (`CLAUDE_CODE_USE_BEDROCK`), Vertex (`CLAUDE_CODE_USE_VERTEX`), and Foundry (`CLAUDE_CODE_USE_FOUNDRY`) have specific environment flags

## Package Scripts

Key scripts from `package.json`:
- `typecheck` — TypeScript type checking without emit
- `build` — Run the esbuild build script
- `lint` — ESLint + Biome linting
- `test` — Vitest test runner

## Entry Points

The application has multiple entry points in `src/entrypoints/`:
- **CLI entry** — Main interactive REPL
- **SDK entry** — Programmatic usage as a library
- **Bridge entry** — Remote connection support (IDE extensions, mobile)
- **Subcommand entries** — `claude config`, `claude mcp`, etc.

## Architecture Overview

```
User Input → CLI/Bridge → REPL Loop → Query Engine → Anthropic API
                                          ↓
                                    Tool Execution
                                    (Bash, Edit, Grep, etc.)
                                          ↓
                                    Permission Check
                                          ↓
                                    Result Rendering (Ink/React)
```

The core loop:
1. User provides a prompt (via REPL or programmatic API)
2. System/user context is assembled (git status, CLAUDE.md files, etc.)
3. The prompt + context is sent to the Anthropic API
4. The model responds with text and/or tool use requests
5. Tool use requests go through permission checking
6. Approved tools execute and return results
7. Results are rendered via Ink React components
8. The loop continues until the model stops requesting tools
