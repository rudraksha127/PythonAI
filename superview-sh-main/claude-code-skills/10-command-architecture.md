# Command Architecture

This document covers the complete architecture of slash commands in the Claude Code codebase. Commands are user-invocable actions triggered by typing `/command-name` in the REPL.

## Overview

Commands live in `src/commands/`, are registered in `src/commands.ts`, and come in three types: `'prompt'` (model-invocable), `'local'` (runs locally), and `'local-jsx'` (renders Ink UI).

## Command Types

### `'local'` — Runs Locally, Returns Text

The simplest type. Executes a function and returns a text result:

```typescript
// src/types/command.ts
type LocalCommand = {
  type: 'local'
  supportsNonInteractive: boolean
  load: () => Promise<LocalCommandModule>
}

export type LocalCommandCall = (
  args: string,
  context: LocalJSXCommandContext,
) => Promise<LocalCommandResult>

export type LocalCommandResult =
  | { type: 'text'; value: string }
  | { type: 'compact'; compactionResult: CompactionResult; displayText?: string }
  | { type: 'skip' }
```

### `'local-jsx'` — Renders React (Ink) UI

For commands that need rich terminal UI:

```typescript
type LocalJSXCommand = {
  type: 'local-jsx'
  load: () => Promise<LocalJSXCommandModule>
}

export type LocalJSXCommandCall = (
  onDone: LocalJSXCommandOnDone,
  context: ToolUseContext & LocalJSXCommandContext,
  args: string,
) => Promise<React.ReactNode>
```

### `'prompt'` — Model-Invocable (Skills)

For commands that expand into model prompts (skills):

```typescript
type PromptCommand = {
  type: 'prompt'
  progressMessage: string
  contentLength: number
  source: SettingSource | 'builtin' | 'mcp' | 'plugin' | 'bundled'
  context?: 'inline' | 'fork'
  getPromptForCommand(args: string, context: ToolUseContext): Promise<ContentBlockParam[]>
}
```

## Directory Structure

Each command gets its own kebab-case directory under `src/commands/`:

```
src/commands/
├── help/
│   ├── help.tsx              # JSX command implementation
│   └── index.ts              # Command registration
├── compact/
│   ├── compact.ts            # Local command implementation
│   └── index.ts              # Command registration
├── config/
│   ├── config.tsx            # JSX command implementation
│   └── index.ts              # Command registration
├── clear/
│   ├── clear.ts              # Simple local command
│   └── index.ts              # Command registration
└── ...                       # 50+ command directories
```

## The `index.ts` Pattern

Every command directory has an `index.ts` that exports a `Command` object with `satisfies Command`:

### Minimal Local Command

```typescript
// src/commands/clear/index.ts
import type { Command } from '../../commands.js'

const clear = {
  type: 'local',
  name: 'clear',
  description: 'Clear the conversation and start fresh',
  supportsNonInteractive: true,
  load: () => import('./clear.js'),
} satisfies Command

export default clear
```

### JSX Command

```typescript
// src/commands/help/index.ts
import type { Command } from '../../commands.js'

const help = {
  type: 'local-jsx',
  name: 'help',
  description: 'Show help and available commands',
  load: () => import('./help.js'),
} satisfies Command

export default help
```

### Command with Conditional Enablement

```typescript
// src/commands/compact/index.ts
import type { Command } from '../../commands.js'
import { isEnvTruthy } from '../../utils/envUtils.js'

const compact = {
  type: 'local',
  name: 'compact',
  description: 'Clear conversation history but keep a summary in context. Optional: /compact [instructions]',
  isEnabled: () => !isEnvTruthy(process.env.DISABLE_COMPACT),
  supportsNonInteractive: true,
  argumentHint: '<optional custom summarization instructions>',
  load: () => import('./compact.js'),
} satisfies Command

export default compact
```

### Key `index.ts` Properties

| Property | Required | Purpose |
|---|---|---|
| `type` | Yes | `'local'`, `'local-jsx'`, or `'prompt'` |
| `name` | Yes | Slash command name (what user types) |
| `description` | Yes | Help text description |
| `load` | Yes | Lazy import of implementation |
| `isEnabled` | No | Conditional availability (defaults to `true`) |
| `isHidden` | No | Hide from typeahead/help (defaults to `false`) |
| `supportsNonInteractive` | No | Can run in non-interactive mode |
| `argumentHint` | No | Hint text for arguments |
| `aliases` | No | Alternative names |
| `availability` | No | Auth/provider requirements |
| `immediate` | No | Execute immediately (bypass queue) |
| `isSensitive` | No | Redact args from history |

## Command Implementation Files

### Local Command Implementation

```typescript
// src/commands/compact/compact.ts
import type { LocalCommandCall } from '../../types/command.js'

export const call: LocalCommandCall = async (args, context) => {
  const { abortController, messages } = context
  const customInstructions = args.trim()

  try {
    // ... command logic
    return {
      type: 'compact',
      compactionResult: result,
      displayText: 'Conversation compacted',
    }
  } catch (err) {
    if (hasExactErrorMessage(err, ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)) {
      return { type: 'text', value: 'Not enough messages to compact' }
    }
    throw err
  }
}
```

### JSX Command Implementation

```typescript
// src/commands/help/help.tsx
import * as React from 'react'
import { HelpV2 } from '../../components/HelpV2/HelpV2.js'
import type { LocalJSXCommandCall } from '../../types/command.js'

export const call: LocalJSXCommandCall = async (
  onDone,
  { options: { commands } },
) => {
  return <HelpV2 commands={commands} onClose={onDone} />
}
```

### `onDone` Callback

JSX commands receive an `onDone` callback to signal completion:

```typescript
export type LocalJSXCommandOnDone = (
  result?: string,
  options?: {
    display?: CommandResultDisplay    // 'skip' | 'system' | 'user'
    shouldQuery?: boolean             // Send to model after command
    metaMessages?: string[]           // Hidden model-visible messages
    nextInput?: string                // Pre-fill next input
    submitNextInput?: boolean         // Auto-submit next input
  },
) => void
```

## Command Registration

Commands are imported and registered in `src/commands.ts`:

```typescript
// src/commands.ts
import help from './commands/help/index.js'
import compact from './commands/compact/index.js'
import config from './commands/config/index.js'
import clear from './commands/clear/index.js'
// ... many more imports

export const COMMANDS = memoize(() => [
  help,
  compact,
  config,
  clear,
  // ... all commands

  // Internal-only commands
  ...INTERNAL_ONLY_COMMANDS,
])
```

### Command Filtering

Commands go through multiple filters:

```typescript
// Filter by availability (auth/provider)
function meetsAvailabilityRequirement(cmd: CommandBase): boolean { ... }

// Filter by enabled status
function isCommandEnabled(cmd: CommandBase): boolean {
  return cmd.isEnabled?.() ?? true
}

// Get all available commands
export function getAvailableCommands(): Command[] {
  return COMMANDS()
    .filter(meetsAvailabilityRequirement)
    .filter(isCommandEnabled)
}
```

### Command Categories

```typescript
// Internal-only commands (USER_TYPE === 'ant')
const INTERNAL_ONLY_COMMANDS = [antTrace, backfillSessions, bughunter, ...]

// Commands safe for remote/bridge connections
const REMOTE_SAFE_COMMANDS = ['help', 'compact', 'clear', 'cost', ...]

// Commands safe for bridge connections
const BRIDGE_SAFE_COMMANDS = [...REMOTE_SAFE_COMMANDS, 'model', ...]
```

## Command Context

Commands receive a rich context object:

```typescript
export type LocalJSXCommandContext = ToolUseContext & {
  canUseTool?: CanUseToolFn
  setMessages: (updater: (prev: Message[]) => Message[]) => void
  options: {
    dynamicMcpConfig?: Record<string, ScopedMcpServerConfig>
    ideInstallationStatus: IDEExtensionInstallationStatus | null
    theme: ThemeName
  }
  onChangeAPIKey: () => void
  onChangeDynamicMcpConfig?: (config: ...) => void
  onInstallIDEExtension?: (ide: IdeType) => void
  resume?: (sessionId: UUID, log: LogOption, entrypoint: ResumeEntrypoint) => Promise<void>
}
```

## Helper Functions

```typescript
// Resolve user-visible name
export function getCommandName(cmd: CommandBase): string {
  return cmd.userFacingName?.() ?? cmd.name
}

// Check if enabled
export function isCommandEnabled(cmd: CommandBase): boolean {
  return cmd.isEnabled?.() ?? true
}
```

## Adding a New Command (Step-by-Step)

1. **Create directory**: `src/commands/my-command/`
2. **Create implementation**: `my-command.ts` (or `.tsx` for JSX)
3. **Create index**: `index.ts` with `satisfies Command` export
4. **Register**: Import in `src/commands.ts` and add to `COMMANDS()` array
5. **Test**: Verify with `/my-command` in the REPL

### Example: New Local Command

```typescript
// src/commands/my-command/my-command.ts
import type { LocalCommandCall } from '../../types/command.js'

export const call: LocalCommandCall = async (args, context) => {
  return { type: 'text', value: `You said: ${args}` }
}

// src/commands/my-command/index.ts
import type { Command } from '../../commands.js'

const myCommand = {
  type: 'local',
  name: 'my-command',
  description: 'Does something useful',
  supportsNonInteractive: false,
  load: () => import('./my-command.js'),
} satisfies Command

export default myCommand
```
