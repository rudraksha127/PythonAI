# Function Patterns

This document covers every function pattern and idiom used in the Claude Code codebase. These patterns are used consistently and should be followed in all new code.

## `buildTool()` Factory Pattern

All model-invocable tools are created via the `buildTool()` factory from `src/Tool.ts`. This provides safe defaults for optional methods:

```typescript
import { buildTool } from '../../Tool.js'
import type { ToolDef } from '../../Tool.js'

export const GrepTool = buildTool({
  name: GREP_TOOL_NAME,
  searchHint: 'search file contents with regex (ripgrep)',
  maxResultSizeChars: 20_000,
  strict: true,

  async description() {
    return getDescription()
  },

  userFacingName() {
    return 'Search'
  },

  get inputSchema(): InputSchema {
    return inputSchema()
  },

  get outputSchema(): OutputSchema {
    return outputSchema()
  },

  isConcurrencySafe() {
    return true
  },

  isReadOnly() {
    return true
  },

  async prompt() {
    return getDescription()
  },

  async validateInput({ path }): Promise<ValidationResult> {
    // ... validation logic
    return { result: true }
  },

  async checkPermissions(input, context): Promise<PermissionDecision> {
    return checkReadPermissionForTool(GrepTool, input, ...)
  },

  renderToolUseMessage,
  renderToolUseErrorMessage,
  renderToolResultMessage,

  async call(input, context) {
    // ... tool execution logic
    return { data: output }
  },
} satisfies ToolDef<InputSchema, Output>)
```

### Key `buildTool()` Properties

| Property | Required | Purpose |
|---|---|---|
| `name` | Yes | Tool identifier (PascalCase string) |
| `inputSchema` | Yes | Zod schema (via `lazySchema`) |
| `call()` | Yes | Main execution function |
| `description()` | Yes | Description for the model |
| `prompt()` | Yes | Full prompt text |
| `renderToolUseMessage` | Yes | Ink rendering of tool use |
| `renderToolResultMessage` | Yes | Ink rendering of result |
| `searchHint` | No | 3-10 word capability phrase for ToolSearch |
| `maxResultSizeChars` | No | Max chars before truncation |
| `strict` | No | Reject unknown input keys |
| `isReadOnly()` | No | Whether tool modifies state |
| `isConcurrencySafe()` | No | Whether tool can run in parallel |
| `validateInput()` | No | Pre-execution validation |
| `checkPermissions()` | No | Permission check |

## `memoize()` Pattern

Use lodash `memoize` for expensive one-time computations. This is heavily used throughout the codebase:

### Basic Memoization

```typescript
import memoize from 'lodash-es/memoize.js'

export const isDebugMode = memoize((): boolean => {
  return (
    runtimeDebugEnabled ||
    isEnvTruthy(process.env.DEBUG) ||
    process.argv.includes('--debug')
  )
})

export const getDebugFilter = memoize((): DebugFilter | null => {
  const debugArg = process.argv.find(arg => arg.startsWith('--debug='))
  if (!debugArg) return null
  return parseDebugFilter(debugArg.substring('--debug='.length))
})

export const isDebugToStdErr = memoize((): boolean => {
  return process.argv.includes('--debug-to-stderr') || process.argv.includes('-d2e')
})
```

### Clearing Memoize Caches

When underlying state changes, clear the memoize cache:

```typescript
export function enableDebugLogging(): boolean {
  const wasActive = isDebugMode() || process.env.USER_TYPE === 'ant'
  runtimeDebugEnabled = true
  isDebugMode.cache.clear?.()  // Clear so next call re-evaluates
  return wasActive
}

export function setSystemPromptInjection(value: string | null): void {
  systemPromptInjection = value
  getUserContext.cache.clear?.()
  getSystemContext.cache.clear?.()
}
```

### Memoize for Async Functions

```typescript
const updateLatestDebugLogSymlink = memoize(async (): Promise<void> => {
  try {
    const debugLogPath = getDebugLogPath()
    const debugLogsDir = dirname(debugLogPath)
    const latestSymlinkPath = join(debugLogsDir, 'latest')
    await unlink(latestSymlinkPath).catch(() => {})
    await symlink(debugLogPath, latestSymlinkPath)
  } catch {
    // Silently fail if symlink creation fails
  }
})
```

## Arrow Functions vs `function` Declarations

### Arrow Functions: Short Callbacks, Module Constants, Inline Expressions

```typescript
// Short callbacks
const byName = (a: Tool, b: Tool) => a.name.localeCompare(b.name)
results.map(line => toRelativePath(line))
tools.filter(tool => tool.isEnabled())
items.sort((a, b) => b[1] - a[1])

// Module-level memoized constants
export const isDebugMode = memoize((): boolean => { ... })
export const getDebugFilter = memoize((): DebugFilter | null => { ... })
```

### `function` Declarations: Named Exports, Hoisted Helpers, Complex Logic

```typescript
// Named exports
export function toError(e: unknown): Error {
  return e instanceof Error ? e : new Error(String(e))
}

export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

// Hoisted helpers (can be referenced before declaration)
function applyHeadLimit<T>(
  items: T[],
  limit: number | undefined,
  offset: number = 0,
): { items: T[]; appliedLimit: number | undefined } {
  if (limit === 0) return { items: items.slice(offset), appliedLimit: undefined }
  const effectiveLimit = limit ?? DEFAULT_HEAD_LIMIT
  const sliced = items.slice(offset, offset + effectiveLimit)
  const wasTruncated = items.length - offset > effectiveLimit
  return { items: sliced, appliedLimit: wasTruncated ? effectiveLimit : undefined }
}

function formatLimitInfo(
  appliedLimit: number | undefined,
  appliedOffset: number | undefined,
): string {
  const parts: string[] = []
  if (appliedLimit !== undefined) parts.push(`limit: ${appliedLimit}`)
  if (appliedOffset) parts.push(`offset: ${appliedOffset}`)
  return parts.join(', ')
}
```

### No-Op Functions

```typescript
function noop(): void {}
```

## `void` for Fire-and-Forget Promises

Explicitly mark intentionally unhandled promises with `void` to satisfy the linter and signal intent:

```typescript
void addToPromptHistory(command)
void flushPromptHistory(retries + 1)
void updateLatestDebugLogSymlink()
void resolve()
void reject(opts.abortError?.() ?? new Error('aborted'))
```

This pattern is used when:
- The promise result is not needed
- The failure is handled internally by the called function
- The caller should not wait for completion

## Guard Clause / Early Return

Return early to avoid deep nesting. This is the preferred control flow pattern:

```typescript
export function logError(error: unknown): void {
  const err = toError(error)

  // Guard: hard fail mode
  if (feature('HARD_FAIL') && isHardFailMode()) {
    console.error('[HARD FAIL]', err.stack || err.message)
    process.exit(1)
  }

  // Guard: disabled reporting
  if (
    isEnvTruthy(process.env.CLAUDE_CODE_USE_BEDROCK) ||
    isEnvTruthy(process.env.DISABLE_ERROR_REPORTING) ||
    isEssentialTrafficOnly()
  ) {
    return
  }

  // Main logic (only reached if all guards pass)
  addToInMemoryErrorLog({ error: err.stack || err.message, timestamp: ... })
  // ...
}

function shouldLogDebugMessage(message: string): boolean {
  if (process.env.NODE_ENV === 'test' && !isDebugToStdErr()) {
    return false
  }
  if (process.env.USER_TYPE !== 'ant' && !isDebugMode()) {
    return false
  }
  if (typeof process === 'undefined') {
    return false
  }
  const filter = getDebugFilter()
  return shouldShowDebugMessage(message, filter)
}
```

## Async Generators for Streaming Data

Used when data is produced incrementally or loaded lazily:

```typescript
export async function* getHistory(): AsyncGenerator<HistoryEntry> {
  for await (const entry of makeLogEntryReader()) {
    if (!entry || typeof entry.project !== 'string') continue
    yield await logEntryToHistoryEntry(entry)
  }
}

// Consuming an async generator
for await (const entry of getHistory()) {
  processEntry(entry)
}
```

## Defensive Defaults

### Nullish Coalescing (`??`)

Use `??` for null/undefined fallbacks:

```typescript
const modelUsage = getUsageForModel(model) ?? {
  inputTokens: 0,
  outputTokens: 0,
  cacheReadInputTokens: 0,
}

return TASK_ID_PREFIXES[type] ?? 'x'
const header = lines[0] ?? e.message
const title = log.agentName || log.customTitle || log.summary || ''
```

### Default Parameter Values

```typescript
export function shortErrorStack(e: unknown, maxFrames = 5): string { ... }

function applyHeadLimit<T>(
  items: T[],
  limit: number | undefined,
  offset: number = 0,
): { ... }
```

### Fallback Arrays

```typescript
const commands = getCommands() || []
const results = await search().catch(() => [])
```

## Module-Level Getter/Setter Pattern

For module-level mutable state, always use getter/setter functions:

```typescript
let hasFormattedOutput = false

export function setHasFormattedOutput(value: boolean): void {
  hasFormattedOutput = value
}

export function getHasFormattedOutput(): boolean {
  return hasFormattedOutput
}
```

### Getter/Setter with Side Effects

```typescript
let systemPromptInjection: string | null = null

export function getSystemPromptInjection(): string | null {
  return systemPromptInjection
}

export function setSystemPromptInjection(value: string | null): void {
  systemPromptInjection = value
  // Side effect: invalidate caches that depend on this value
  getUserContext.cache.clear?.()
  getSystemContext.cache.clear?.()
}
```

## Lazy Loading Pattern

Commands and heavy modules use lazy loading via dynamic `import()`:

```typescript
const compact = {
  type: 'local',
  name: 'compact',
  description: 'Clear conversation history...',
  load: () => import('./compact.js'),  // Only loaded when command is invoked
} satisfies Command
```

### Conditional Require for Feature Flags

```typescript
/* eslint-disable @typescript-eslint/no-require-imports */
const reactiveCompact = feature('REACTIVE_COMPACT')
  ? (require('../../services/compact/reactiveCompact.js') as typeof import('../../services/compact/reactiveCompact.js'))
  : null
/* eslint-enable @typescript-eslint/no-require-imports */
```

## Callback/Cleanup Registration

Register cleanup functions that run on process exit:

```typescript
import { registerCleanup } from './cleanupRegistry.js'

registerCleanup(async () => {
  debugWriter?.dispose()
  await pendingWrite
})
```

## Promise Chaining for Sequential Async

```typescript
// Chain writes so depth stays ~1 per second
pendingWrite = pendingWrite
  .then(appendAsync.bind(null, needMkdir, dir, path, content))
  .catch(noop)
```

## `.bind()` for Partial Application

Used to avoid closures that capture parent scope (reduces memory):

```typescript
// Module-level so .bind captures only its explicit args, not the
// writeFn closure's parent scope (Jarred, #22257).
async function appendAsync(
  needMkdir: boolean,
  dir: string,
  path: string,
  content: string,
): Promise<void> { ... }

// Usage — bind instead of closure
pendingWrite = pendingWrite
  .then(appendAsync.bind(null, needMkdir, dir, path, content))
  .catch(noop)
```

## `setTimeout` with Extra Arguments

Pass arguments directly to setTimeout instead of using closures:

```typescript
// Pass resolve and signal as extra args to avoid closure
const timer = setTimeout(
  (signal, onAbort, resolve) => {
    signal?.removeEventListener('abort', onAbort)
    void resolve()
  },
  ms,
  signal,    // arg1
  onAbort,   // arg2
  resolve,   // arg3
)
```

## Pure Utility Functions

Small, focused functions that do one thing:

```typescript
export function dateToFilename(date: Date): string {
  return date.toISOString().replace(/[:.]/g, '-')
}

export function plural(count: number, word: string): string {
  return count === 1 ? word : `${word}s`
}

function parseISOString(s: string): Date {
  const b = s.split(/\D+/)
  return new Date(Date.UTC(...))
}
```

## `Promise.race()` for Timeouts

```typescript
export function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  message: string,
): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined
  const timeoutPromise = new Promise<never>((_, reject) => {
    timer = setTimeout(rejectWithTimeout, ms, reject, message)
    if (typeof timer === 'object') timer.unref?.()
  })
  return Promise.race([promise, timeoutPromise]).finally(() => {
    if (timer !== undefined) clearTimeout(timer)
  })
}
```

## Export Patterns

### Named Exports (Most Common)

```typescript
export function toError(e: unknown): Error { ... }
export const isDebugMode = memoize((): boolean => { ... })
export class ShellError extends Error { ... }
export type SessionId = string & { ... }
```

### Default Exports (Commands Only)

```typescript
// Only used for command index.ts files
export default compact
export default help
```

### Re-Exports

```typescript
export type { ToolPermissionRulesBySource }
export { inputSchema, outputSchema }
```
