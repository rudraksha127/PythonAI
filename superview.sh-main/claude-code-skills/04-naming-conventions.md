# Naming Conventions

This document covers all naming conventions used throughout the Claude Code codebase, with real examples from the source.

## Variables and Functions: `camelCase`

All local variables, module-level variables, parameters, and function names use `camelCase`:

```typescript
// Functions
export function getCommands(): Command[] { ... }
export function isDebugMode(): boolean { ... }
export function logError(error: unknown): void { ... }
export function findCommand(name: string): Command | undefined { ... }
export function enableDebugLogging(): boolean { ... }
export function captureAPIRequest(params: BetaMessageStreamParams): void { ... }

// Variables
let runtimeDebugEnabled = false
let systemPromptInjection: string | null = null
let debugWriter: BufferedWriter | null = null
let hasFormattedOutput = false
const customInstructions = args.trim()
const absolutePath = path ? expandPath(path) : getCwd()
```

### Boolean Variables/Functions

Prefix with `is`, `has`, `should`, `can`, or similar:

```typescript
export function isAbortError(e: unknown): boolean { ... }
export function isENOENT(e: unknown): boolean { ... }
export function isFsInaccessible(e: unknown): boolean { ... }
export function hasExactErrorMessage(error: unknown, message: string): boolean { ... }
function shouldLogDebugMessage(message: string): boolean { ... }
function shouldUseSandbox(): boolean { ... }

let hasFormattedOutput = false
const isAutonomousPrompt = log.firstPrompt?.startsWith(`<${TICK_TAG}>`)
const useFirstPrompt = strippedFirstPrompt && !isAutonomousPrompt
```

### Getter/Setter Pairs

Use `get`/`set` prefixes for module-level state accessors:

```typescript
export function getSystemPromptInjection(): string | null { ... }
export function setSystemPromptInjection(value: string | null): void { ... }

export function getHasFormattedOutput(): boolean { ... }
export function setHasFormattedOutput(value: boolean): void { ... }

export function getDebugLogPath(): string { ... }
export function getDebugFilePath(): string | null { ... }
export function getMinDebugLogLevel(): DebugLogLevel { ... }
```

## Types, Interfaces, and Classes: `PascalCase`

All type aliases, interfaces, classes, and enums use `PascalCase`:

```typescript
// Type aliases
export type SessionId = string & { readonly __brand: 'SessionId' }
export type AgentId = string & { readonly __brand: 'AgentId' }
export type DebugLogLevel = 'verbose' | 'debug' | 'info' | 'warn' | 'error'
export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'killed'
export type PermissionBehavior = 'allow' | 'deny' | 'ask'
export type PermissionMode = InternalPermissionMode
export type AxiosErrorKind = 'auth' | 'timeout' | 'network' | 'http' | 'other'

// Compound types
export type ToolUseContext = { ... }
export type ToolPermissionContext = DeepImmutable<{ ... }>
export type LocalCommandResult = { type: 'text'; value: string } | { ... }
export type AggregatedHookResult = { ... }
export type PromptRequest = z.infer<ReturnType<typeof promptRequestSchema>>

// Classes
export class ClaudeError extends Error { ... }
export class AbortError extends Error { ... }
export class ShellError extends Error { ... }
export class ConfigParseError extends Error { ... }
export class TeleportOperationError extends Error { ... }

// Interfaces (via type, not interface keyword)
export type ErrorLogSink = {
  logError: (error: Error) => void
  logMCPError: (serverName: string, error: unknown) => void
  ...
}
```

### Types for Schemas

When deriving types from Zod schemas, follow this pattern:

```typescript
const inputSchema = lazySchema(() => z.strictObject({ ... }))
type InputSchema = ReturnType<typeof inputSchema>         // The schema type
export type FileEditInput = z.output<InputSchema>         // The parsed output type
export type FileEditOutput = z.infer<OutputSchema>        // The inferred type
```

## Constants: `UPPER_SNAKE_CASE`

Module-level constants and configuration values use `UPPER_SNAKE_CASE`:

```typescript
// Numeric constants
const MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024  // 1 GiB
const DEFAULT_HEAD_LIMIT = 250
const MAX_IN_MEMORY_ERRORS = 100
const PROGRESS_THRESHOLD_MS = 2000
const ASSISTANT_BLOCKING_BUDGET_MS = 15_000
const PREVIEW_SIZE_BYTES = 4096

// String constants
const EOL = '\n'
const TASK_ID_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz'
export const FILE_EDIT_TOOL_NAME = 'Edit'
export const GREP_TOOL_NAME = 'Grep'
export const BASH_TOOL_NAME = 'Bash'

// Array/Set constants
const VCS_DIRECTORIES_TO_EXCLUDE = ['.git', '.svn', '.hg', '.bzr', '.jj', '.sl'] as const
const BASH_SEARCH_COMMANDS = new Set(['find', 'grep', 'rg', 'ag', 'ack', 'locate'])
const BASH_READ_COMMANDS = new Set(['cat', 'head', 'tail', 'less', 'more', 'wc', 'stat'])
const BASH_SILENT_COMMANDS = new Set(['mv', 'cp', 'rm', 'mkdir', 'rmdir', 'chmod'])

// Object constants
const LEVEL_ORDER: Record<DebugLogLevel, number> = {
  verbose: 0, debug: 1, info: 2, warn: 3, error: 4,
}

// Pattern constants
const AGENT_ID_PATTERN = /^a(?:.+-)?[0-9a-f]{16}$/
export const CLAUDE_FOLDER_PERMISSION_PATTERN = '/.claude/**'
```

### Exported Constants from `constants/` Directory

Constants shared across the codebase go in `src/constants/`:

```typescript
// src/constants/toolLimits.ts
export const TOOL_SUMMARY_MAX_LENGTH = 100

// src/constants/xml.ts
export const TICK_TAG = 'tick'
```

## Tool Names: `PascalCase` String Constants

Tool names are `PascalCase` strings stored as `UPPER_SNAKE_CASE` constants:

```typescript
export const GREP_TOOL_NAME = 'Grep'
export const BASH_TOOL_NAME = 'Bash'
export const FILE_EDIT_TOOL_NAME = 'Edit'
export const NOTEBOOK_EDIT_TOOL_NAME = 'NotebookEdit'
export const AGENT_TOOL_NAME = 'Agent'
```

## File and Directory Naming

### Tool Directories: `PascalCase`
```
src/tools/GrepTool/
src/tools/BashTool/
src/tools/FileEditTool/
src/tools/AgentTool/
src/tools/WebFetchTool/
```

### Command Directories: `kebab-case`
```
src/commands/add-dir/
src/commands/install-github-app/
src/commands/install-slack-app/
src/commands/debug-tool-call/
src/commands/output-style/
src/commands/break-cache/
```

### Utility Files: `camelCase.ts`
```
src/utils/errors.ts
src/utils/debug.ts
src/utils/sleep.ts
src/utils/envUtils.ts
src/utils/stringUtils.ts
src/utils/fileRead.ts
src/utils/lazySchema.ts
src/utils/semanticBoolean.ts
src/utils/cleanupRegistry.ts
src/utils/bufferedWriter.ts
```

### Component Files: `PascalCase.tsx`
```
src/components/Spinner.tsx
src/components/Markdown.tsx
src/components/MessageResponse.tsx
src/components/CtrlOToExpand.tsx
src/components/FallbackToolUseErrorMessage.tsx
src/components/HelpV2/HelpV2.tsx
```

### Type Files: `camelCase.ts`
```
src/types/command.ts
src/types/hooks.ts
src/types/ids.ts
src/types/logs.ts
src/types/message.ts
src/types/permissions.ts
src/types/plugin.ts
```

### Top-Level Source Files: `PascalCase.ts` for Core Types
```
src/Tool.ts           # Core type — PascalCase
src/Task.ts           # Core type — PascalCase
src/commands.ts       # Registry — camelCase
src/tools.ts          # Registry — camelCase
src/context.ts        # Utility — camelCase
src/query.ts          # Core loop — camelCase
src/main.tsx          # Entry — camelCase
src/cost-tracker.ts   # Service — kebab-case (rare)
src/history.ts        # Service — camelCase
```

## Unused Parameters: `_` Prefix

Mark unused parameters with an underscore prefix:

```typescript
// Unused function parameters
function renderToolResultMessage(
  output: Output,
  _progressMessagesForMessage: ProgressMessage<ToolProgressData>[],
  { verbose }: { verbose: boolean },
): React.ReactNode { ... }

// Unused destructured properties
const { numLines: _numLines, ...rest } = output

// Unused loop variables
results.map((_, i) => ...)

// Exhaustive check variable
const _exhaustive: never = status
```

## Intentionally Long Names for Safety

When a name carries a security or privacy obligation, make it deliberately long to force the developer to acknowledge they've verified the safety:

```typescript
// Error class — name forces you to verify message content
export class TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS extends Error {
  readonly telemetryMessage: string
  ...
}

// Type — name forces you to verify metadata content
type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS = string

// Usage — the long name is intentional friction
throw new TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS(
  'MCP server connection timed out'
)
```

## React Component Names: `PascalCase`

```typescript
function SearchResultSummary({ count, countLabel, content, verbose }) { ... }
function BackgroundHint() { ... }

// Exported components
export function HelpV2({ commands, onClose }) { ... }
export function MessageResponse({ children, height }) { ... }
export function CtrlOToExpand() { ... }
export function FallbackToolUseErrorMessage({ result, verbose }) { ... }
```

## Hook Names: `use` Prefix

```typescript
// File: src/hooks/useCanUseTool.ts
export type CanUseToolFn = ...

// React hooks follow standard React naming
function useAppState() { ... }
function useMessages() { ... }
```

## Event Handler Names

Not prefixed with `on` — use descriptive function names:

```typescript
// Module-level handlers
function onAbort(): void { ... }
function appendAsync(...): Promise<void> { ... }
function noop(): void {}

// Callback props use `on` prefix
type Props = {
  onClose: () => void
  onDone: LocalJSXCommandOnDone
  onChangeAPIKey: () => void
  onChangeDynamicMcpConfig?: (config: ...) => void
  onInstallIDEExtension?: (ide: IdeType) => void
}
```

## Summary Table

| Category | Convention | Real Examples |
|---|---|---|
| Functions | `camelCase` | `getCommands`, `isDebugMode`, `logError`, `toError` |
| Variables | `camelCase` | `runtimeDebugEnabled`, `debugWriter`, `absolutePath` |
| Types/Interfaces | `PascalCase` | `SessionId`, `ToolUseContext`, `AppState`, `TaskStatus` |
| Classes | `PascalCase` | `ClaudeError`, `AbortError`, `ShellError` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_HEAD_LIMIT`, `BASH_TOOL_NAME`, `EOL` |
| Tool names | `PascalCase` string | `'Grep'`, `'Bash'`, `'Edit'`, `'NotebookEdit'` |
| Tool dirs | `PascalCase/` | `GrepTool/`, `BashTool/`, `FileEditTool/` |
| Command dirs | `kebab-case/` | `add-dir/`, `install-github-app/` |
| Util files | `camelCase.ts` | `errors.ts`, `debug.ts`, `lazySchema.ts` |
| Component files | `PascalCase.tsx` | `Spinner.tsx`, `Markdown.tsx` |
| Unused params | `_` prefix | `_input`, `_ctx`, `_numLines`, `_exhaustive` |
| Safety names | Long explicit | `TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS` |
| Booleans | `is`/`has`/`should` | `isAbortError`, `hasFormattedOutput`, `shouldLog` |
| Getters/Setters | `get`/`set` prefix | `getSystemPromptInjection`, `setHasFormattedOutput` |
| React components | `PascalCase` | `SearchResultSummary`, `HelpV2`, `MessageResponse` |
| Hooks | `use` prefix | `useAppState`, `useCanUseTool` |
