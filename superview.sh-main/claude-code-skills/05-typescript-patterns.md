# TypeScript Patterns

This document covers every TypeScript pattern and idiom used throughout the Claude Code codebase. These patterns are fundamental to writing code that fits the existing style.

## Branded Types for ID Safety

The codebase uses branded types (also called "opaque types" or "nominal types") to prevent accidentally mixing up string IDs at compile time:

```typescript
// src/types/ids.ts

/**
 * A session ID uniquely identifies a Claude Code session.
 * Returned by getSessionId().
 */
export type SessionId = string & { readonly __brand: 'SessionId' }

/**
 * An agent ID uniquely identifies a subagent within a session.
 * Returned by createAgentId().
 * When present, indicates the context is a subagent (not the main session).
 */
export type AgentId = string & { readonly __brand: 'AgentId' }
```

### Creating Branded Values

Provide explicit casting functions with JSDoc guidance:

```typescript
/**
 * Cast a raw string to SessionId.
 * Use sparingly - prefer getSessionId() when possible.
 */
export function asSessionId(id: string): SessionId {
  return id as SessionId
}

/**
 * Cast a raw string to AgentId.
 * Use sparingly - prefer createAgentId() when possible.
 */
export function asAgentId(id: string): AgentId {
  return id as AgentId
}
```

### Validating Branded Values

Use validation functions that return `BrandedType | null`:

```typescript
const AGENT_ID_PATTERN = /^a(?:.+-)?[0-9a-f]{16}$/

/**
 * Validate and brand a string as AgentId.
 * Matches the format produced by createAgentId(): `a` + optional `<label>-` + 16 hex chars.
 * Returns null if the string doesn't match.
 */
export function toAgentId(s: string): AgentId | null {
  return AGENT_ID_PATTERN.test(s) ? (s as AgentId) : null
}
```

### Why Use Branded Types

This prevents bugs like passing a session ID where an agent ID is expected:

```typescript
function doSomething(sessionId: SessionId, agentId: AgentId) { ... }

const sid = asSessionId('abc')
const aid = asAgentId('def')

doSomething(sid, aid)  // OK
doSomething(aid, sid)  // Compile error! Types are incompatible
doSomething('raw', 'string')  // Compile error! Plain strings don't match
```

## Discriminated Unions

Use string literal unions (not TypeScript `enum`) for status/mode/behavior enums:

```typescript
// Status types
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'killed'

// Behavior types
export type PermissionBehavior = 'allow' | 'deny' | 'ask'

// Mode types
export type DebugLogLevel = 'verbose' | 'debug' | 'info' | 'warn' | 'error'

// Result types
export type AxiosErrorKind = 'auth' | 'timeout' | 'network' | 'http' | 'other'

// Command result display types
export type CommandResultDisplay = 'skip' | 'system' | 'user'
```

### Tagged Discriminated Unions

Use the `type` field as a discriminator for complex unions:

```typescript
export type LocalCommandResult =
  | { type: 'text'; value: string }
  | {
      type: 'compact'
      compactionResult: CompactionResult
      displayText?: string
    }
  | { type: 'skip' }

// Usage — TypeScript narrows the type in each branch
switch (result.type) {
  case 'text':
    console.log(result.value)  // TypeScript knows `value` exists
    break
  case 'compact':
    console.log(result.compactionResult)  // TypeScript knows `compactionResult` exists
    break
  case 'skip':
    break
}
```

### Complex Union Types (e.g., Command)

```typescript
export type Command = CommandBase &
  (PromptCommand | LocalCommand | LocalJSXCommand)
```

Where each variant has a `type` field:
```typescript
type PromptCommand = { type: 'prompt'; ... }
type LocalCommand = { type: 'local'; ... }
type LocalJSXCommand = { type: 'local-jsx'; ... }
```

### Queued Event Unions

```typescript
type QueuedErrorEvent =
  | { type: 'error'; error: Error }
  | { type: 'mcpError'; serverName: string; error: unknown }
  | { type: 'mcpDebug'; serverName: string; message: string }
```

## `as const` + Derived Types

Define literal arrays with `as const` and derive types from them:

```typescript
// Define the array of valid values
export const EXTERNAL_PERMISSION_MODES = [
  'acceptEdits',
  'bypassPermissions',
  'default',
  'dontAsk',
  'plan',
] as const

// Derive the union type from the array
export type ExternalPermissionMode = (typeof EXTERNAL_PERMISSION_MODES)[number]
// Equivalent to: 'acceptEdits' | 'bypassPermissions' | 'default' | 'dontAsk' | 'plan'
```

This pattern is used for:
- Permission modes
- Hook events
- Tool presets
- VCS directory exclusions

```typescript
const VCS_DIRECTORIES_TO_EXCLUDE = [
  '.git', '.svn', '.hg', '.bzr', '.jj', '.sl',
] as const
```

### `as const` on Inline Literals

```typescript
return [_, r.status === 'fulfilled' ? (r.value.mtimeMs ?? 0) : 0] as const
// Type: readonly [string, number]

{ mode: 'content' as const, numFiles: 0, ... }
// Narrows 'content' to the literal type instead of string
```

## `satisfies` Keyword

Use `satisfies` to type-check values without widening the inferred type:

```typescript
// Command registration — satisfies checks the shape without widening
const help = {
  type: 'local-jsx',
  name: 'help',
  description: 'Show help and available commands',
  load: () => import('./help.js'),
} satisfies Command

export default help
```

### `satisfies` with Complex Types

```typescript
export const INTERNAL_PERMISSION_MODES = [
  ...EXTERNAL_PERMISSION_MODES,
  ...(feature('TRANSCRIPT_CLASSIFIER') ? (['auto'] as const) : ([] as const)),
] as const satisfies readonly PermissionMode[]
```

### `satisfies` on Tool Definitions

```typescript
export const GrepTool = buildTool({
  name: GREP_TOOL_NAME,
  searchHint: 'search file contents with regex (ripgrep)',
  maxResultSizeChars: 20_000,
  strict: true,
  // ... all tool methods
} satisfies ToolDef<InputSchema, Output>)
```

## Generics

### Generic Types with Constraints

```typescript
// Tool type is generic over input schema, output, and progress
export type Tool<
  Input extends AnyObject = AnyObject,
  Output = unknown,
  P = unknown,
> = { ... }

// BuildTool is a factory that accepts a ToolDef and returns a Tool
export function buildTool<I extends ZodSchema, O>(
  def: ToolDef<I, O>,
): Tool<z.infer<I>, O> { ... }
```

### Generic Utility Functions

```typescript
function applyHeadLimit<T>(
  items: T[],
  limit: number | undefined,
  offset: number = 0,
): { items: T[]; appliedLimit: number | undefined } { ... }

export function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  message: string,
): Promise<T> { ... }
```

## `DeepImmutable<>` Utility Type

Use for context objects that should never be mutated:

```typescript
export type ToolPermissionContext = DeepImmutable<{
  mode: PermissionMode
  additionalWorkingDirectories: Map<string, AdditionalWorkingDirectory>
  toolPermissionRulesBySource: ToolPermissionRulesBySource
}>
```

## Zod Schema Patterns

### `lazySchema()` for Deferred Evaluation

All tool schemas use `lazySchema()` to defer Zod schema creation until first access:

```typescript
import { lazySchema } from '../../utils/lazySchema.js'
import { z } from 'zod/v4'

const inputSchema = lazySchema(() =>
  z.strictObject({
    pattern: z.string().describe('The regex pattern to search for'),
    path: z.string().optional().describe('File or directory to search in'),
    glob: z.string().optional().describe('Glob pattern to filter files'),
  }),
)

// Derive the schema type
type InputSchema = ReturnType<typeof inputSchema>

// Derive the parsed value type
type Input = z.infer<InputSchema>
// or for schemas with preprocessing:
type Input = z.output<InputSchema>
```

### `z.strictObject()` vs `z.object()`

Tool input schemas use `z.strictObject()` which rejects unknown keys:

```typescript
// Tool inputs — strict to catch model hallucinating extra fields
const inputSchema = lazySchema(() =>
  z.strictObject({
    file_path: z.string().describe('The absolute path to the file'),
    old_string: z.string().describe('The text to replace'),
    new_string: z.string().describe('The replacement text'),
  }),
)

// Non-tool schemas — regular object (more lenient)
const hookResponseSchema = z.object({
  continue: z.boolean().optional(),
  stopReason: z.string().optional(),
})
```

### Semantic Type Wrappers

The codebase has Zod preprocessors for loose type parsing from model output:

```typescript
import { semanticBoolean } from '../../utils/semanticBoolean.js'
import { semanticNumber } from '../../utils/semanticNumber.js'

// semanticBoolean accepts: true, false, "true", "false", 1, 0, etc.
replace_all: semanticBoolean(
  z.boolean().default(false).optional(),
).describe('Replace all occurrences'),

// semanticNumber accepts: 5, "5", etc.
'-B': semanticNumber(z.number().optional()).describe('Lines before match'),
head_limit: semanticNumber(z.number().optional()).describe('Limit output'),
```

### Discriminated Unions in Zod

```typescript
z.union([
  z.object({
    hookEventName: z.literal('PreToolUse'),
    permissionDecision: permissionBehaviorSchema().optional(),
    updatedInput: z.record(z.string(), z.unknown()).optional(),
  }),
  z.object({
    hookEventName: z.literal('PostToolUse'),
    additionalContext: z.string().optional(),
  }),
  z.object({
    hookEventName: z.literal('SessionStart'),
    watchPaths: z.array(z.string()).optional(),
  }),
])
```

## Compile-Time Type Assertions

Use type-level assertions to verify that types from different sources match:

```typescript
import type { IsEqual } from 'type-fest'

// Assert that Zod-inferred type matches SDK type
type Assert<T extends true> = T
type _assertSDKTypesMatch = Assert<
  IsEqual<SchemaHookJSONOutput, HookJSONOutput>
>
```

## Type Guards

### `is` Return Type

```typescript
export function isAbortError(e: unknown): boolean {
  return (
    e instanceof AbortError ||
    e instanceof APIUserAbortError ||
    (e instanceof Error && e.name === 'AbortError')
  )
}

export function isFsInaccessible(e: unknown): e is NodeJS.ErrnoException {
  const code = getErrnoCode(e)
  return code === 'ENOENT' || code === 'EACCES' || code === 'EPERM' || ...
}

export function isHookEvent(value: string): value is HookEvent {
  return HOOK_EVENTS.includes(value as HookEvent)
}

export function isSyncHookJSONOutput(
  json: HookJSONOutput,
): json is SyncHookJSONOutput {
  return !('async' in json && json.async === true)
}
```

### Narrowing with `in` Operator

```typescript
if ('isAxiosError' in e && e.isAxiosError) {
  // e is narrowed to have isAxiosError property
}

if ('async' in json && json.async === true) {
  // json is narrowed to AsyncHookJSONOutput
}
```

## Constructor Parameter Properties

Use `public readonly` in constructor parameters:

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

## Object Spread for Conditional Properties

Use spread with short-circuit for optional properties:

```typescript
const output = {
  mode: 'content' as const,
  numFiles: 0,
  filenames: [],
  content: finalLines.join('\n'),
  numLines: finalLines.length,
  // Only include appliedLimit if it was actually applied
  ...(appliedLimit !== undefined && { appliedLimit }),
  // Only include appliedOffset if non-zero
  ...(offset > 0 && { appliedOffset: offset }),
}
```

## Record Types

```typescript
const LEVEL_ORDER: Record<DebugLogLevel, number> = {
  verbose: 0, debug: 1, info: 2, warn: 3, error: 4,
}

// Zod record
z.record(z.string(), z.unknown())
```

## Never Type for Exhaustiveness Checking

```typescript
function getPrefix(type: TaskType): string {
  switch (type) {
    case 'background': return 'b'
    case 'foreground': return 'f'
    default:
      const _exhaustive: never = type
      return 'x'
  }
}
```

## Utility Type Patterns

```typescript
// Omit for derived types
export type EditInput = Omit<FileEditInput, 'file_path'>

// Partial for optional inputs
function renderToolUseMessage(
  { pattern, path }: Partial<{ pattern: string; path?: string }>,
  { verbose }: { verbose: boolean },
): React.ReactNode { ... }

// ReturnType for schema types
type InputSchema = ReturnType<typeof inputSchema>
type OutputSchema = ReturnType<typeof outputSchema>
```
