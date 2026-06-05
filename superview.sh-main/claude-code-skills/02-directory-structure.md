# Directory Structure

## Top-Level Layout

```
claude-code/
├── src/                    # All source code
├── build.mjs               # esbuild build script (ESM JavaScript)
├── package.json            # Dependencies and scripts
├── tsconfig.json           # TypeScript configuration
├── biome.jsonc             # Biome linter/formatter config
├── .eslintrc.*             # ESLint configuration
└── vitest.config.*         # Test configuration
```

## Source Directory (`src/`)

```
src/
├── entrypoints/            # CLI entry points and SDK surface
├── commands/               # Slash commands (/help, /config, /compact, etc.)
├── tools/                  # Model-invocable tools (BashTool, GrepTool, etc.)
├── components/             # Ink React UI components
├── hooks/                  # React hooks for state and behavior
├── services/               # Backend services (analytics, MCP, LSP, etc.)
├── utils/                  # Shared utility functions (largest directory)
├── types/                  # Pure type definitions (no runtime dependencies)
├── state/                  # Application state definitions
├── constants/              # Shared constant values
├── context/                # React context providers
├── skills/                 # Skill loading, discovery, and management
├── tasks/                  # Background task management
├── bridge/                 # Remote bridge connection (IDE, mobile)
├── cli/                    # CLI transport and I/O handling
├── ink/                    # Ink framework extensions and overrides
├── keybindings/            # Keyboard shortcut handling
├── migrations/             # Configuration migration scripts
└── bootstrap/              # Application bootstrapping and initialization
```

## Key Top-Level Source Files

These files live directly in `src/` and form the backbone of the system:

| File | Purpose |
|---|---|
| `Tool.ts` | Core `Tool` type definition, `buildTool()` factory, `ToolDef` interface |
| `Task.ts` | Task types (`TaskStatus`, `TaskHandle`), ID generation utilities |
| `commands.ts` | Command registry — imports, filters, memoizes all available commands |
| `tools.ts` | Tool registry — assembles the complete tool pool from all sources |
| `context.ts` | System/user context generation for conversations (git status, CLAUDE.md) |
| `query.ts` | Main query execution loop — sends messages to the API, processes responses |
| `main.tsx` | Main REPL application Ink component |
| `cost-tracker.ts` | Session cost tracking, token usage, API duration metrics |
| `history.ts` | Prompt history management, pasted content tracking |

## Tool Directory Pattern

Each tool gets its own PascalCase directory under `src/tools/`:

```
src/tools/
├── AgentTool/              # Subagent spawning
├── BashTool/               # Shell command execution (largest, ~18 files)
│   ├── BashTool.tsx        # Main tool implementation
│   ├── UI.tsx              # React rendering
│   ├── prompt.ts           # Description and name
│   ├── toolName.ts         # Name constant (separate to avoid cycles)
│   ├── bashPermissions.ts  # Permission logic
│   ├── bashSecurity.ts     # Security validation
│   ├── commandSemantics.ts # Command classification
│   ├── utils.ts            # Tool-specific utilities
│   └── ...                 # Additional specialized files
├── FileEditTool/           # File editing
│   ├── FileEditTool.ts     # Main tool implementation
│   ├── UI.tsx              # React rendering
│   ├── prompt.ts           # Description
│   ├── constants.ts        # Name + constants (separate for cycle avoidance)
│   ├── types.ts            # Input/output Zod schemas and types
│   └── utils.ts            # Edit-specific utilities
├── GrepTool/               # Ripgrep search (minimal, 3 files)
│   ├── GrepTool.ts         # Main tool
│   ├── UI.tsx              # Rendering
│   └── prompt.ts           # Description
├── FileReadTool/           # File reading
├── FileWriteTool/          # File writing
├── GlobTool/               # File globbing
├── WebFetchTool/           # URL fetching
├── WebSearchTool/          # Web search
├── TaskCreateTool/         # Background task creation
├── TaskGetTool/            # Task status retrieval
├── TaskListTool/           # Task listing
├── SkillTool/              # Skill invocation
├── MCPTool/                # MCP tool proxy
├── shared/                 # Shared tool utilities
└── testing/                # Test-only tool implementations
```

### Minimum Files Per Tool

At minimum, a tool needs:

| File | Contents |
|---|---|
| `prompt.ts` | `TOOL_NAME` constant + `getDescription()` function |
| `ToolName.ts` | `buildTool({ ... })` export with all methods |
| `UI.tsx` | `renderToolUseMessage()`, `renderToolResultMessage()`, `renderToolUseErrorMessage()` |

Larger tools add:
- `constants.ts` — Name and shared constants (when needed to break import cycles)
- `types.ts` — Zod schemas and TypeScript types (when schemas are complex)
- `utils.ts` — Tool-specific helper functions
- Domain-specific files (e.g., `bashSecurity.ts`, `sedEditParser.ts`)

## Command Directory Pattern

Commands use kebab-case directories under `src/commands/`:

```
src/commands/
├── help/
│   ├── help.tsx            # JSX command implementation
│   └── index.ts            # Command registration object
├── compact/
│   ├── compact.ts          # Local command implementation
│   └── index.ts            # Command registration object
├── config/
├── clear/
├── model/
├── add-dir/
├── install-github-app/
├── ...                     # 50+ command directories
```

### Command Registration (`index.ts`)

Every command directory has an `index.ts` that exports a `Command` object:

```typescript
import type { Command } from '../../commands.js'

const help = {
  type: 'local-jsx',
  name: 'help',
  description: 'Show help and available commands',
  load: () => import('./help.js'),
} satisfies Command

export default help
```

## Utils Directory

The `utils/` directory is the largest, containing shared functionality:

```
src/utils/
├── errors.ts               # Error classes and utilities
├── debug.ts                # Debug logging
├── log.ts                  # Error logging
├── sleep.ts                # Abort-aware sleep/timeout
├── cwd.ts                  # Current working directory management
├── path.ts                 # Path expansion and normalization
├── file.ts                 # File operations
├── fileRead.ts             # File reading with metadata
├── format.ts               # Output formatting
├── envUtils.ts             # Environment variable helpers
├── stringUtils.ts          # String manipulation
├── messages.ts             # Message processing
├── systemPrompt.ts         # System prompt construction
├── lazySchema.ts           # Deferred Zod schema evaluation
├── semanticBoolean.ts      # Zod preprocessor for loose boolean parsing
├── semanticNumber.ts       # Zod preprocessor for loose number parsing
├── permissions/            # Permission system (filesystem, shell, etc.)
├── settings/               # User/project settings management
├── bash/                   # Bash command parsing and analysis
├── plugins/                # Plugin management
├── sandbox/                # Sandboxed execution
├── task/                   # Task output and disk management
└── ...                     # Many more specialized utilities
```

## Types Directory

Pure type definitions with **no runtime dependencies** — used to break import cycles:

```
src/types/
├── command.ts              # Command, PromptCommand, LocalCommand types
├── hooks.ts                # Hook types, Zod schemas, result types
├── ids.ts                  # Branded types (SessionId, AgentId)
├── logs.ts                 # Log entry types
├── message.ts              # Message types
├── permissions.ts          # Permission mode/rule/behavior types
├── plugin.ts               # Plugin manifest types
├── textInputTypes.ts       # Text input types
└── generated/              # Auto-generated types (protobuf, events)
```

## Where to Put New Code

| What you're adding | Where it goes |
|---|---|
| New model-invocable tool | `src/tools/MyTool/` (PascalCase dir) |
| New slash command | `src/commands/my-command/` (kebab-case dir) |
| New shared utility | `src/utils/myUtil.ts` (camelCase file) |
| New React component | `src/components/MyComponent.tsx` (PascalCase file) |
| New React hook | `src/hooks/useMyHook.ts` |
| New pure types | `src/types/myTypes.ts` |
| New constants | `src/constants/myConstants.ts` |
| New service | `src/services/myService/` |
| New background task type | `src/tasks/MyTask/` |
