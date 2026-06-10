# State Management

This document covers every state management pattern used in the Claude Code codebase. The project uses a combination of module-level state, React context, and explicit state threading — no external state management library.

## Core Principles

1. **Module-level `let` with getter/setter pairs** for global singletons
2. **`AppState` threaded through context objects** for per-session state
3. **`registerCleanup()` for process exit cleanup** of resources
4. **`memoize()` for cached computations** that depend on static state
5. **Functional updates** (`setAppState(prev => next)`) for state transitions

## Module-Level State (Singletons)

The most common pattern for process-wide state. Declare a module-level `let` variable and expose it through getter/setter functions:

### Basic Getter/Setter

```typescript
let hasFormattedOutput = false

export function setHasFormattedOutput(value: boolean): void {
  hasFormattedOutput = value
}

export function getHasFormattedOutput(): boolean {
  return hasFormattedOutput
}
```

### Getter/Setter with Cache Invalidation

When changing state should invalidate memoized computations:

```typescript
let systemPromptInjection: string | null = null

export function getSystemPromptInjection(): string | null {
  return systemPromptInjection
}

export function setSystemPromptInjection(value: string | null): void {
  systemPromptInjection = value
  // Invalidate caches that depend on this state
  getUserContext.cache.clear?.()
  getSystemContext.cache.clear?.()
}
```

### Getter/Setter with Side Effects

```typescript
let runtimeDebugEnabled = false

export function enableDebugLogging(): boolean {
  const wasActive = isDebugMode() || process.env.USER_TYPE === 'ant'
  runtimeDebugEnabled = true
  isDebugMode.cache.clear?.()  // Re-evaluate debug mode
  return wasActive
}
```

### Module-Level Nullable Singletons

For resources that are initialized lazily:

```typescript
let debugWriter: BufferedWriter | null = null
let pendingWrite: Promise<void> = Promise.resolve()

function getDebugWriter(): BufferedWriter {
  if (!debugWriter) {
    debugWriter = createBufferedWriter({
      writeFn: content => { ... },
      flushIntervalMs: 1000,
      maxBufferSize: 100,
      immediateMode: isDebugMode(),
    })
    registerCleanup(async () => {
      debugWriter?.dispose()
      await pendingWrite
    })
  }
  return debugWriter
}
```

### Error Log Sink Pattern

A more complex version with queuing for events that arrive before initialization:

```typescript
let errorLogSink: ErrorLogSink | null = null
const errorQueue: QueuedErrorEvent[] = []

export function logError(error: unknown): void {
  const err = toError(error)
  if (errorLogSink === null) {
    // Queue the event — sink isn't attached yet
    errorQueue.push({ type: 'error', error: err })
    return
  }
  errorLogSink.logError(err)
}

/**
 * Attach the error log sink. Queued events are drained immediately.
 * Idempotent: if already attached, this is a no-op.
 */
export function attachErrorLogSink(newSink: ErrorLogSink): void {
  if (errorLogSink !== null) return
  errorLogSink = newSink

  // Drain the queue
  if (errorQueue.length > 0) {
    const queuedEvents = [...errorQueue]
    errorQueue.length = 0
    for (const event of queuedEvents) {
      switch (event.type) {
        case 'error': errorLogSink.logError(event.error); break
        case 'mcpError': errorLogSink.logMCPError(event.serverName, event.error); break
        case 'mcpDebug': errorLogSink.logMCPDebug(event.serverName, event.message); break
      }
    }
  }
}
```

### In-Memory Ring Buffer

```typescript
const MAX_IN_MEMORY_ERRORS = 100
let inMemoryErrorLog: Array<{ error: string; timestamp: string }> = []

function addToInMemoryErrorLog(errorInfo: { error: string; timestamp: string }): void {
  if (inMemoryErrorLog.length >= MAX_IN_MEMORY_ERRORS) {
    inMemoryErrorLog.shift()  // Remove oldest
  }
  inMemoryErrorLog.push(errorInfo)
}

export function getInMemoryErrors(): { error: string; timestamp: string }[] {
  return [...inMemoryErrorLog]  // Return copy, not reference
}
```

## `AppState` Threading

Per-session state is bundled in an `AppState` object and threaded through `ToolUseContext`:

### Accessing State in Tools

```typescript
async call(input, { abortController, getAppState }) {
  const appState = getAppState()
  const ignorePatterns = getFileReadIgnorePatterns(appState.toolPermissionContext)
  // ...
}

async checkPermissions(input, context): Promise<PermissionDecision> {
  const appState = context.getAppState()
  return checkReadPermissionForTool(
    GrepTool,
    input,
    appState.toolPermissionContext,
  )
}
```

### `ToolUseContext` Shape

The context object passed to tools and commands:

```typescript
export type ToolUseContext = {
  getAppState: () => AppState
  abortController: AbortController
  messages: Message[]
  agentId: AgentId | undefined
  options: {
    querySource?: QuerySource
    // ... more options
  }
}
```

### Functional State Updates

State updates use functional form to avoid stale state:

```typescript
// Update state immutably
setAppState((prev: AppState) => ({
  ...prev,
  toolPermissionContext: {
    ...prev.toolPermissionContext,
    mode: newMode,
  },
}))

// Update messages
context.setMessages((prev: Message[]) => [
  ...prev,
  newMessage,
])
```

## `memoize()` as Cached State

Module-level `memoize()` acts as computed/derived state that's cached after first evaluation:

```typescript
import memoize from 'lodash-es/memoize.js'

// Computed once, then cached
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

const isHardFailMode = memoize((): boolean => {
  return process.argv.includes('--hard-fail')
})
```

### Invalidating Memoized State

When the underlying data changes, clear the memoize cache:

```typescript
export function setSystemPromptInjection(value: string | null): void {
  systemPromptInjection = value
  getUserContext.cache.clear?.()
  getSystemContext.cache.clear?.()
}

// After successful compaction
getUserContext.cache.clear?.()

// After enabling debug mode
isDebugMode.cache.clear?.()
```

## Cleanup Registry

Register cleanup functions that run when the process exits:

```typescript
import { registerCleanup } from './cleanupRegistry.js'

// Register cleanup when creating resources
registerCleanup(async () => {
  debugWriter?.dispose()
  await pendingWrite
})

// Multiple cleanups can be registered
registerCleanup(async () => {
  await flushPromptHistory()
})
```

## Flush Patterns

For buffered state that needs to be persisted to disk:

```typescript
export async function flushDebugLogs(): Promise<void> {
  debugWriter?.flush()
  await pendingWrite
}

export async function flushPromptHistory(): Promise<void> {
  if (pendingEntries.length === 0) return
  const toFlush = [...pendingEntries]
  pendingEntries.length = 0
  await appendToFile(historyPath, toFlush.map(jsonStringify).join('\n') + '\n')
}
```

## Buffered Writer Pattern

For state that accumulates and flushes periodically:

```typescript
debugWriter = createBufferedWriter({
  writeFn: content => {
    // ... write to file
  },
  flushIntervalMs: 1000,    // Flush every second
  maxBufferSize: 100,       // Flush after 100 entries
  immediateMode: isDebugMode(),  // Skip buffering in debug mode
})
```

## Session-Level State in Bootstrap

Early session state lives in `src/bootstrap/state.ts`:

```typescript
// src/bootstrap/state.ts
let sessionId: SessionId

export function getSessionId(): SessionId { return sessionId }
export function setSessionId(id: SessionId): void { sessionId = id }

let lastAPIRequest: unknown = null
export function setLastAPIRequest(req: unknown): void { lastAPIRequest = req }
export function getLastAPIRequest(): unknown { return lastAPIRequest }
```

## React State (Ink Components)

Ink components use standard React hooks for local UI state:

```typescript
// In components - standard React patterns
const [isExpanded, setIsExpanded] = useState(false)
const [selectedIndex, setSelectedIndex] = useState(0)
```

## Anti-Patterns to Avoid

1. **Don't use global `var`** — always `let` with getter/setter
2. **Don't expose module-level state directly** — always use functions
3. **Don't mutate returned arrays/objects** — return copies (`[...array]`, `{ ...obj }`)
4. **Don't forget to clear memoize caches** when underlying state changes
5. **Don't use class instances for singletons** — use module-level state
6. **Don't store state in `process.env`** — read it, but use module variables for mutable state
