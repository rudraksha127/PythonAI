# Formatting Rules

This document covers every formatting rule and code style convention used in the Claude Code codebase. The project uses Biome for formatting and ESLint + custom rules for linting.

## No Semicolons

The codebase omits semicolons entirely. This is enforced by the formatter:

```typescript
// CORRECT — no semicolons
import { getCwd } from '../../utils/cwd.js'
const result = await search()
export function toError(e: unknown): Error {
  return e instanceof Error ? e : new Error(String(e))
}

// WRONG — has semicolons
import { getCwd } from '../../utils/cwd.js';
const result = await search();
```

**Exception**: Semicolons appear in compiled/generated UI files (React compiler output) — those files are auto-generated and should not be manually edited.

## Single Quotes for Strings

Always use single quotes for string literals:

```typescript
// CORRECT
const name = 'GrepTool'
import { getCwd } from '../../utils/cwd.js'
this.name = 'AbortError'

// WRONG
const name = "GrepTool"
import { getCwd } from "../../utils/cwd.js"
```

**Exception**: Template literals (backticks) when interpolation or multiline is needed:

```typescript
const message = `Found ${count} files`
const description = `A powerful search tool built on ripgrep

  Usage:
  - ALWAYS use ${GREP_TOOL_NAME} for search tasks.
`
```

## Trailing Commas

Use trailing commas in all multiline constructs:

### Function Parameters

```typescript
export class ShellError extends Error {
  constructor(
    public readonly stdout: string,
    public readonly stderr: string,
    public readonly code: number,
    public readonly interrupted: boolean,   // <-- trailing comma
  ) {
    super('Shell command failed')
  }
}
```

### Object Literals

```typescript
const LEVEL_ORDER: Record<DebugLogLevel, number> = {
  verbose: 0,
  debug: 1,
  info: 2,
  warn: 3,
  error: 4,    // <-- trailing comma
}
```

### Array Literals

```typescript
const VCS_DIRECTORIES_TO_EXCLUDE = [
  '.git',
  '.svn',
  '.hg',
  '.bzr',
  '.jj',
  '.sl',    // <-- trailing comma
] as const
```

### Function Arguments

```typescript
const result = await checkReadPermissionForTool(
  GrepTool,
  input,
  appState.toolPermissionContext,   // <-- trailing comma
)
```

### Import Lists

```typescript
import {
  type DebugFilter,
  parseDebugFilter,
  shouldShowDebugMessage,    // <-- trailing comma
} from './debugFilter.js'
```

## 2-Space Indentation

The entire codebase uses 2 spaces for indentation:

```typescript
export function logForDebugging(
  message: string,
  { level }: { level: DebugLogLevel } = {
    level: 'debug',
  },
): void {
  if (LEVEL_ORDER[level] < LEVEL_ORDER[getMinDebugLogLevel()]) {
    return
  }
  if (!shouldLogDebugMessage(message)) {
    return
  }
  const timestamp = new Date().toISOString()
  const output = `${timestamp} [${level.toUpperCase()}] ${message.trim()}\n`
  getDebugWriter().write(output)
}
```

## No Explicit `return undefined`

Use bare `return` instead of `return undefined`:

```typescript
// CORRECT
export function getErrnoCode(e: unknown): string | undefined {
  if (e && typeof e === 'object' && 'code' in e) {
    return e.code
  }
  return undefined  // Exception: when the type signature requires it explicitly
}

// For void functions, just use return with no value
export function logError(error: unknown): void {
  if (isDisabled) {
    return
  }
  // ...
}
```

## Template Literals for Interpolation

Always use template literals when embedding expressions:

```typescript
// CORRECT
const message = `Path does not exist: ${path}`
const output = `${timestamp} [${level.toUpperCase()}] ${message.trim()}\n`
const result = `Found ${numFiles} ${plural(numFiles, 'file')}`
const logPath = `${getClaudeConfigHomeDir()}/debug/${getSessionId()}.txt`

// WRONG — string concatenation
const message = 'Path does not exist: ' + path
const output = timestamp + ' [' + level.toUpperCase() + '] ' + message + '\n'
```

## Ternary Expressions

### Simple Ternaries (Single Line)

```typescript
const effectiveLimit = limit ?? DEFAULT_HEAD_LIMIT
const result = count === 1 ? word : `${word}s`
return e instanceof Error ? e : new Error(String(e))
```

### Multiline Ternaries (for Complex Expressions)

```typescript
const useFirstPrompt = strippedFirstPrompt && !isAutonomousPrompt

const title =
  log.agentName ||
  log.customTitle ||
  log.summary ||
  (useFirstPrompt ? strippedFirstPrompt : undefined) ||
  defaultTitle ||
  (isAutonomousPrompt ? 'Autonomous session' : undefined) ||
  (log.sessionId ? log.sessionId.slice(0, 8) : '') ||
  ''
```

### Ternaries in JSX

```typescript
{count > 0 && <CtrlOToExpand />}
{secondaryCount !== undefined && secondaryLabel
  ? <Text>across <Text bold>{secondaryCount}</Text> {secondaryLabel}</Text>
  : null}
```

## Spread Operator for Array/Object Combination

```typescript
// Combining arrays
const tools = [...builtInTools, ...mcpTools, ...pluginTools]
const modes = [...EXTERNAL_PERMISSION_MODES, ...conditionalModes]

// Conditional spreading
const allTools = [
  GrepTool,
  FileEditTool,
  ...(SleepTool ? [SleepTool] : []),
]

// Object spread for copies
return [...inMemoryErrorLog]
const queuedEvents = [...errorQueue]

// Conditional object properties
const output = {
  mode: 'content' as const,
  numFiles: 0,
  ...(appliedLimit !== undefined && { appliedLimit }),
  ...(offset > 0 && { appliedOffset: offset }),
}
```

## `Promise.all()` for Parallel Work

```typescript
const [skillDirCommands, pluginSkills] = await Promise.all([
  getSkillDirCommands(cwd).catch(err => { logError(toError(err)); return [] }),
  getPluginSkills().catch(err => { logError(toError(err)); return [] }),
])
```

## Numeric Separators

Use underscores for large numbers:

```typescript
maxResultSizeChars: 20_000
const MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024
const ASSISTANT_BLOCKING_BUDGET_MS = 15_000
```

## Destructuring

### Function Parameter Destructuring

```typescript
async call(
  {
    pattern,
    path,
    glob,
    output_mode = 'files_with_matches',
    '-B': context_before,
    '-A': context_after,
    head_limit,
    offset = 0,
  },
  { abortController, getAppState },
) { ... }
```

### Inline Destructuring

```typescript
const { messages, ...paramsWithoutMessages } = params
const { abortController } = context
```

### Renaming in Destructuring

```typescript
const { '-B': context_before, '-A': context_after } = input
const { numLines: _numLines, ...rest } = output
```

## Type Annotations on Function Returns

Always annotate return types for exported functions:

```typescript
export function toError(e: unknown): Error { ... }
export function errorMessage(e: unknown): string { ... }
export function getErrnoCode(e: unknown): string | undefined { ... }
export function isAbortError(e: unknown): boolean { ... }
export function isFsInaccessible(e: unknown): e is NodeJS.ErrnoException { ... }
```

## Empty Lines

- One empty line between top-level declarations
- One empty line before `return` in long functions (optional)
- No empty lines inside short functions
- One empty line after import blocks

## Line Length

No strict line length limit, but:
- Prefer wrapping at ~100-120 characters
- Long strings (descriptions, error messages) can exceed
- Import paths are never wrapped

## Object Method Shorthand

```typescript
// In tool definitions
const tool = {
  isConcurrencySafe() { return true },
  isReadOnly() { return true },
  getPath({ path }): string { return path || getCwd() },
  async description() { return getDescription() },
  renderToolUseMessage,           // Reference to imported function
  renderToolResultMessage,        // Reference to imported function
}
```

## Arrow Function Formatting

### No Braces for Single Expressions

```typescript
const byName = (a: Tool, b: Tool) => a.name.localeCompare(b.name)
results.map(line => toRelativePath(line))
tools.filter(tool => tool.isEnabled())
```

### Braces for Multi-Statement Bodies

```typescript
results.map((_, i) => {
  const r = stats[i]!
  return [_, r.status === 'fulfilled' ? (r.value.mtimeMs ?? 0) : 0] as const
})
```

## `switch` Statement Formatting

```typescript
switch (event.type) {
  case 'error':
    errorLogSink.logError(event.error)
    break
  case 'mcpError':
    errorLogSink.logMCPError(event.serverName, event.error)
    break
  case 'mcpDebug':
    errorLogSink.logMCPDebug(event.serverName, event.message)
    break
}
```

## Linting Tools

- **Biome** — Primary formatter and linter
- **ESLint** — Additional rules including custom rules
- **Custom rules** — e.g., `custom-rules/no-process-exit` prevents uncontrolled exits
