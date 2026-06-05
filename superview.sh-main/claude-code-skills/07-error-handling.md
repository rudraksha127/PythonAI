# Error Handling

This document covers every error handling pattern used in the Claude Code codebase. Error handling is taken seriously in this project — the codebase has a rich set of custom error classes, utility functions, and conventions to ensure robustness without crashes.

## Core Principle: Never Crash on Non-Critical Failures

The application must remain responsive even when individual operations fail. This means:
- Catch errors at boundaries and provide fallbacks
- Log errors for debugging without propagating to the user
- Use graceful degradation instead of throwing

## Custom Error Classes

### Base Pattern

All custom errors extend `Error` and set `this.name`:

```typescript
export class ClaudeError extends Error {
  constructor(message: string) {
    super(message)
    this.name = this.constructor.name
  }
}

export class MalformedCommandError extends Error {}

export class AbortError extends Error {
  constructor(message?: string) {
    super(message)
    this.name = 'AbortError'
  }
}
```

### Data-Carrying Errors

Use constructor parameter properties (`public readonly`) to attach metadata:

```typescript
export class ShellError extends Error {
  constructor(
    public readonly stdout: string,
    public readonly stderr: string,
    public readonly code: number,
    public readonly interrupted: boolean,
  ) {
    super('Shell command failed')
    this.name = 'ShellError'
  }
}

export class ConfigParseError extends Error {
  filePath: string
  defaultConfig: unknown

  constructor(message: string, filePath: string, defaultConfig: unknown) {
    super(message)
    this.name = 'ConfigParseError'
    this.filePath = filePath
    this.defaultConfig = defaultConfig
  }
}

export class TeleportOperationError extends Error {
  constructor(
    message: string,
    public readonly formattedMessage: string,
  ) {
    super(message)
    this.name = 'TeleportOperationError'
  }
}
```

### Telemetry-Safe Errors

For errors that get sent to telemetry, the long class name forces the developer to verify no sensitive data is included:

```typescript
export class TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS extends Error {
  readonly telemetryMessage: string

  constructor(message: string, telemetryMessage?: string) {
    super(message)
    this.name = 'TelemetrySafeError'
    this.telemetryMessage = telemetryMessage ?? message
  }
}
```

## Error Utility Functions

The codebase provides a comprehensive set of utility functions in `src/utils/errors.ts`. **Always use these instead of raw casts or manual checks.**

### `toError(e: unknown): Error`

Normalize an unknown caught value into an `Error` instance. Use at catch-site boundaries:

```typescript
try {
  await riskyOperation()
} catch (err) {
  logError(toError(err))  // Always an Error, even if `err` was a string or number
}
```

### `errorMessage(e: unknown): string`

Extract a message string when you don't need the full Error object:

```typescript
try {
  await riskyOperation()
} catch (err) {
  const msg = errorMessage(err)  // "something failed" — always a string
  displayToUser(`Operation failed: ${msg}`)
}
```

### `getErrnoCode(e: unknown): string | undefined`

Extract the errno code (e.g., `'ENOENT'`, `'EACCES'`) from a caught error. **Replaces** the `(e as NodeJS.ErrnoException).code` cast pattern:

```typescript
// GOOD — type-safe, no cast
const code = getErrnoCode(e)
if (code === 'ENOENT') { ... }

// BAD — unsafe cast
if ((e as NodeJS.ErrnoException).code === 'ENOENT') { ... }
```

### `isENOENT(e: unknown): boolean`

Check if an error is "file not found":

```typescript
try {
  await fs.stat(absolutePath)
} catch (e: unknown) {
  if (isENOENT(e)) {
    return { result: false, message: `Path does not exist: ${path}` }
  }
  throw e  // Re-throw unexpected errors
}
```

### `isFsInaccessible(e: unknown): e is NodeJS.ErrnoException`

Check if the path is missing, inaccessible, or structurally unreachable. Covers ENOENT, EACCES, EPERM, ENOTDIR, ELOOP:

```typescript
try {
  const content = await readFile(path, 'utf8')
} catch (e) {
  if (isFsInaccessible(e)) {
    return []  // Graceful fallback
  }
  throw e
}
```

### `getErrnoPath(e: unknown): string | undefined`

Extract the filesystem path from a Node.js error:

```typescript
const path = getErrnoPath(e)
if (path) {
  logForDebugging(`Failed to access: ${path}`)
}
```

### `isAbortError(e: unknown): boolean`

Check for any flavor of abort error (custom, DOMException, SDK):

```typescript
try {
  await longRunningOperation(signal)
} catch (e) {
  if (isAbortError(e)) {
    return  // User cancelled — not an error
  }
  throw e
}
```

### `hasExactErrorMessage(error: unknown, message: string): boolean`

Check if an error has an exact message match:

```typescript
if (hasExactErrorMessage(err, ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)) {
  return 'Not enough messages to compact'
}
```

### `shortErrorStack(e: unknown, maxFrames = 5): string`

Extract error message + top N stack frames. Used when the error flows to the model as a tool_result to save context tokens:

```typescript
// Instead of sending 500+ chars of stack trace to the model
const shortStack = shortErrorStack(error, 5)
return { type: 'tool_result', content: shortStack }
```

### `classifyAxiosError(e: unknown)`

Classify HTTP errors into buckets. Replaces duplicated 20-line chains:

```typescript
const { kind, status, message } = classifyAxiosError(e)
switch (kind) {
  case 'auth':     // 401/403
  case 'timeout':  // ECONNABORTED
  case 'network':  // ECONNREFUSED/ENOTFOUND
  case 'http':     // Other HTTP error
  case 'other':    // Not an axios error
}
```

## Error Logging

### `logError()` — Centralized Error Logging

All errors flow through `logError()` which handles multiple destinations:

```typescript
import { logError } from '../../utils/log.js'

try {
  await operation()
} catch (err) {
  logError(toError(err))
}
```

`logError()` sends to:
1. Debug logs (visible with `--debug` flag)
2. In-memory log (for bug reports)
3. Persistent error file (ant users only)

### `logForDebugging()` — Debug-Level Logging

For informational messages that help debugging but aren't errors:

```typescript
import { logForDebugging } from '../../utils/debug.js'

logForDebugging(`Tool ${name} completed in ${ms}ms`)
logForDebugging(`Cache miss for key: ${key}`, { level: 'verbose' })
```

## Catch Block Patterns

### Pattern 1: Catch, Log, and Continue

The most common pattern — catch the error, log it, and provide a fallback:

```typescript
try {
  const result = await expensiveOperation()
  return result
} catch (err) {
  logError(toError(err))
  return defaultValue
}
```

### Pattern 2: Catch-Per-Promise with `Promise.all()`

When running parallel operations, catch individually so one failure doesn't break all:

```typescript
const [skillDirCommands, pluginSkills] = await Promise.all([
  getSkillDirCommands(cwd).catch(err => {
    logError(toError(err))
    return []
  }),
  getPluginSkills().catch(err => {
    logError(toError(err))
    return []
  }),
])
```

### Pattern 3: Catch Specific Errors, Re-throw Others

```typescript
try {
  await fs.stat(absolutePath)
} catch (e: unknown) {
  if (isENOENT(e)) {
    // Expected: file doesn't exist
    return { result: false, message: `Path does not exist: ${path}` }
  }
  // Unexpected: re-throw
  throw e
}
```

### Pattern 4: Silent Catch for Expected Failures

When failure is expected and harmless, use an empty catch with a comment:

```typescript
// Creating a directory that might already exist
try {
  getFsImplementation().mkdirSync(dir)
} catch {
  // Directory already exists
}

// Removing a symlink that might not exist
await unlink(latestSymlinkPath).catch(() => {})

// Symlink creation is best-effort
try {
  await symlink(debugLogPath, latestSymlinkPath)
} catch {
  // Silently fail if symlink creation fails
}
```

### Pattern 5: The `// pass` Comment

For truly no-op catches:

```typescript
} catch {
  // pass
}
```

### Pattern 6: Defensive Outer Catch

When you've already caught per-promise but want belt-and-suspenders:

```typescript
try {
  const [a, b] = await Promise.all([
    opA().catch(err => { logError(toError(err)); return fallbackA }),
    opB().catch(err => { logError(toError(err)); return fallbackB }),
  ])
  return { a, b }
} catch (err) {
  // This should never happen since we catch at the Promise level, but defensive
  logError(toError(err))
  return { a: fallbackA, b: fallbackB }
}
```

### Pattern 7: `Promise.allSettled()` for Batch Operations

When individual failures in a batch shouldn't reject the whole operation:

```typescript
// Use allSettled so a single ENOENT (file deleted between ripgrep's scan
// and this stat) does not reject the whole batch. Failed stats sort as mtime 0.
const stats = await Promise.allSettled(
  results.map(_ => getFsImplementation().stat(_)),
)
const sortedMatches = results.map((_, i) => {
  const r = stats[i]!
  return [_, r.status === 'fulfilled' ? (r.value.mtimeMs ?? 0) : 0] as const
})
```

## Abort Handling

The codebase has a specific pattern for handling user cancellation:

```typescript
// Tools receive an abortController in their context
async call(input, { abortController }) {
  const results = await ripGrep(args, path, abortController.signal)
  // ...
}

// Sleep that responds to abort
await sleep(ms, signal)
if (signal?.aborted) {
  return  // Clean exit on abort
}
```

### AbortError Detection

```typescript
try {
  await operation(signal)
} catch (e) {
  if (isAbortError(e)) {
    // User cancelled — clean up silently
    return
  }
  // Real error — handle normally
  logError(toError(e))
}
```

## Validation Errors

Tools return validation results instead of throwing:

```typescript
async validateInput({ path }): Promise<ValidationResult> {
  if (path) {
    try {
      await fs.stat(absolutePath)
    } catch (e: unknown) {
      if (isENOENT(e)) {
        return {
          result: false,
          message: `Path does not exist: ${path}`,
          errorCode: 1,
        }
      }
      throw e
    }
  }
  return { result: true }
}
```

## Error Sink Pattern

Errors are queued before the logging infrastructure is initialized, then drained when the sink attaches:

```typescript
// Queue errors before sink is ready
const errorQueue: QueuedErrorEvent[] = []
let errorLogSink: ErrorLogSink | null = null

export function logError(error: unknown): void {
  if (errorLogSink === null) {
    errorQueue.push({ type: 'error', error: toError(error) })
    return
  }
  errorLogSink.logError(toError(error))
}

// Drain queue when sink attaches
export function attachErrorLogSink(newSink: ErrorLogSink): void {
  if (errorLogSink !== null) return  // Idempotent
  errorLogSink = newSink
  for (const event of errorQueue) {
    // ... dispatch each queued event
  }
  errorQueue.length = 0
}
```

## Hard Fail Mode

For development, `--hard-fail` mode crashes immediately on any logged error:

```typescript
const isHardFailMode = memoize((): boolean => {
  return process.argv.includes('--hard-fail')
})

export function logError(error: unknown): void {
  const err = toError(error)
  if (feature('HARD_FAIL') && isHardFailMode()) {
    // biome-ignore lint/suspicious/noConsole:: intentional crash output
    console.error('[HARD FAIL] logError called with:', err.stack || err.message)
    // eslint-disable-next-line custom-rules/no-process-exit
    process.exit(1)
  }
  // ... normal error handling
}
```
