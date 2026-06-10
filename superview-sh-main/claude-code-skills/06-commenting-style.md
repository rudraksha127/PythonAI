# Commenting Style

This document covers every commenting pattern used in the Claude Code codebase. Comments in this project are unusually high-quality — they explain reasoning, link to issues, and serve as documentation for future developers.

## Philosophy: Explain *Why*, Not Just *What*

The codebase consistently favors comments that explain the reasoning behind a decision over comments that merely restate what the code does:

```typescript
// GOOD — explains why this alphabet was chosen
// Case-insensitive-safe alphabet (digits + lowercase) for task IDs.
// 36^8 ≈ 2.8 trillion combinations, sufficient to resist brute-force symlink attacks.
const TASK_ID_ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyz'

// GOOD — explains the non-obvious constraint
// V8/Bun string length limit is ~2^30 characters (~1 billion). For typical
// ASCII/Latin-1 files, 1 byte on disk = 1 character, so 1 GiB in stat bytes
// ≈ 1 billion characters ≈ the runtime string limit. Multi-byte UTF-8 files
// can be larger on disk per character, but 1 GiB is a safe byte-level guard
// that prevents OOM without being unnecessarily restrictive.
const MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024 // 1 GiB (stat bytes)

// BAD — merely restates what the code does
// Set max edit file size to 1 GiB
const MAX_EDIT_FILE_SIZE = 1024 * 1024 * 1024
```

## JSDoc for Public/Exported APIs

Use `/** ... */` JSDoc blocks for exported functions. Include purpose, usage context, and where appropriate `@param`, `@returns`, `@example`, `@internal`:

### Single-Purpose Functions

```typescript
/**
 * Normalize an unknown value into an Error.
 * Use at catch-site boundaries when you need an Error instance.
 */
export function toError(e: unknown): Error {
  return e instanceof Error ? e : new Error(String(e))
}

/**
 * Extract a string message from an unknown error-like value.
 * Use when you only need the message (e.g., for logging or display).
 */
export function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}
```

### Functions with Complex Behavior

```typescript
/**
 * True iff `e` is any of the abort-shaped errors the codebase encounters:
 * our AbortError class, a DOMException from AbortController.abort()
 * (.name === 'AbortError'), or the SDK's APIUserAbortError. The SDK class
 * is checked via instanceof because minified builds mangle class names —
 * constructor.name becomes something like 'nJT' and the SDK never sets
 * this.name, so string matching silently fails in production.
 */
export function isAbortError(e: unknown): boolean { ... }
```

### Multi-Line JSDoc with Tags

```typescript
/**
 * Abort-responsive sleep. Resolves after `ms` milliseconds, or immediately
 * when `signal` aborts (so backoff loops don't block shutdown).
 *
 * By default, abort resolves silently; the caller should check
 * `signal.aborted` after the await. Pass `throwOnAbort: true` to have
 * abort reject — useful when the sleep is deep inside a retry loop
 * and you want the rejection to bubble up and cancel the whole operation.
 *
 * Pass `abortError` to customize the rejection error (implies
 * `throwOnAbort: true`). Useful for retry loops that catch a specific
 * error class (e.g. `APIUserAbortError`).
 */
export function sleep(
  ms: number,
  signal?: AbortSignal,
  opts?: { throwOnAbort?: boolean; abortError?: () => Error; unref?: boolean },
): Promise<void> { ... }
```

### Functions with Usage Examples

```typescript
/**
 * Logs an error to multiple destinations for debugging and monitoring.
 *
 * This function logs errors to:
 * - Debug logs (visible via `claude --debug` or `tail -f ~/.claude/debug/latest`)
 * - In-memory error log (accessible via `getInMemoryErrors()`, useful for including
 *   in bug reports or displaying recent errors to users)
 * - Persistent error log file (only for internal 'ant' users)
 *
 * Usage:
 * ```ts
 * logError(new Error('Failed to connect'))
 * ```
 *
 * To view errors:
 * - Debug: Run `claude --debug` or `tail -f ~/.claude/debug/latest`
 * - In-memory: Call `getInMemoryErrors()` to get recent errors
 */
export function logError(error: unknown): void { ... }
```

### Error Class JSDoc with `@example`

```typescript
/**
 * Error with a message that is safe to log to telemetry.
 * Use the long name to confirm you've verified the message contains no
 * sensitive data (file paths, URLs, code snippets).
 *
 * Single-arg: same message for user and telemetry
 * Two-arg: different messages (e.g., full message has file path, telemetry doesn't)
 *
 * @example
 * // Same message for both
 * throw new TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS(
 *   'MCP server "slack" connection timed out'
 * )
 *
 * @example
 * // Different messages
 * throw new TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS(
 *   `MCP tool timed out after ${ms}ms`,  // Full message for logs/user
 *   'MCP tool timed out'                  // Telemetry message
 * )
 */
export class TelemetrySafeError_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS extends Error { ... }
```

### `@internal` Tag for Test-Only APIs

```typescript
/**
 * Reset error log state for testing purposes only.
 * @internal
 */
export function _resetErrorLogForTesting(): void {
  errorLogSink = null
  errorQueue.length = 0
  inMemoryErrorLog = []
}
```

### `@private` Tag for Internal Functions

```typescript
/**
 * Internal function to load and process logs from a specified path
 * @param path Directory containing logs
 * @returns Array of logs sorted by date
 * @private
 */
async function loadLogList(path: string): Promise<LogOption[]> { ... }
```

## Type Property Documentation

Use `/** ... */` for type/interface properties — especially for non-obvious fields:

```typescript
export type CommandBase = {
  availability?: CommandAvailability[]
  description: string
  hasUserSpecifiedDescription?: boolean
  /** Defaults to true. Only set when the command has conditional enablement. */
  isEnabled?: () => boolean
  /** Defaults to false. Only set when the command should be hidden from typeahead/help. */
  isHidden?: boolean
  name: string
  aliases?: string[]
  argumentHint?: string // Hint text for command arguments (displayed in gray after command)
  whenToUse?: string // From the "Skill" spec. Detailed usage scenarios
  version?: string // Version of the command/skill
  disableModelInvocation?: boolean // Whether to disable this command from being invoked by models
  /** Defaults to `name`. Only override when the displayed name differs. */
  userFacingName?: () => string
}
```

### Multi-Line Property Documentation

```typescript
export type Tool = {
  /** Optional aliases for backwards compatibility when a tool is renamed. */
  aliases?: string[]
  /**
   * One-line capability phrase used by ToolSearch for keyword matching.
   * 3–10 words, no trailing period.
   */
  searchHint?: string
  /**
   * Lazy-load the command implementation.
   * Returns a module with a call() function.
   * This defers loading heavy dependencies until the command is invoked.
   */
  load: () => Promise<LocalJSXCommandModule>
}
```

## Inline Implementation Comments

Use `//` for inline comments that explain implementation details. These are the most common comment type:

### Explaining Business Logic

```typescript
// REPL keeps snipped messages for UI scrollback — project so the compact
// model doesn't summarize content that was intentionally removed.
messages = getMessagesAfterCompactBoundary(messages)

// Skip firstPrompt if it's a tick/goal message (autonomous mode auto-prompt)
const isAutonomousPrompt = log.firstPrompt?.startsWith(`<${TICK_TAG}>`)

// Strip display-unfriendly tags (command-name, ide_opened_file, etc.) early
// so that command-only prompts (e.g. /clear) become empty and fall through
// to the next fallback instead of showing raw XML tags.
const strippedFirstPrompt = log.firstPrompt
  ? stripDisplayTagsAllowEmpty(log.firstPrompt)
  : ''
```

### Explaining Non-Obvious Code

```typescript
// If pattern starts with dash, use -e flag to specify it as a pattern
// This prevents ripgrep from interpreting it as a command-line option
if (pattern.startsWith('-')) {
  args.push('-e', pattern)
}

// Limit line length to prevent base64/minified content from cluttering output
args.push('--max-columns', '500')

// Check aborted state BEFORE setting up the timer. If we defined
// onAbort first and called it synchronously here, it would reference
// `timer` while still in the Temporal Dead Zone.
if (signal?.aborted) { ... }
```

### Explaining Performance Decisions

```typescript
// Apply head_limit first — relativize is per-line work, so
// avoid processing lines that will be discarded (broad patterns can
// return 10k+ lines with head_limit keeping only ~30-100).
const { items: limitedResults, appliedLimit } = applyHeadLimit(results, head_limit, offset)

// WSL has severe performance penalty for file reads (3-5x slower on WSL2)
// The timeout is handled by ripgrep itself via execFile timeout option
const results = await ripGrep(args, absolutePath, abortController.signal)
```

## PR and Issue References

Reference PRs and issues to provide historical context:

```typescript
// PR #19134 blanket-blocked all slash commands from bridge inbound because
// `/model` from iOS was popping the local Ink picker.

// Module-level so .bind captures only its explicit args, not the
// writeFn closure's parent scope (Jarred, #22257).

// immediateMode: must stay sync. Async writes are lost on direct
// process.exit() and keep the event loop alive in beforeExit
// handlers (infinite loop with Perfetto tracing). See #22257.

// See: https://github.com/BurntSushi/ripgrep/discussions/2156#discussioncomment-2316335
```

## Section Headers

Use decorated section headers in build scripts, long files, and configuration files:

```typescript
// ── Step 1: Discover all TS/TSX source files ────────────────────────────

// ── Step 2: Build with esbuild (transpile-only, no bundling) ────────────

// ============================================================================
// Permission Modes
// ============================================================================

// ============================================================================
// Permission Rules
// ============================================================================
```

## Lint Suppression Comments

**Always** explain why a lint rule is being suppressed:

### ESLint Suppressions

```typescript
// eslint-disable-next-line custom-rules/no-process-exit
process.exit(1)

// eslint-disable-next-line no-restricted-syntax -- not a sleep: REJECTS after ms (timeout guard)
timer = setTimeout(rejectWithTimeout, ms, reject, message)
```

### Biome Suppressions

```typescript
// biome-ignore lint/suspicious/noConsole:: intentional crash output
console.error('[HARD FAIL] logError called with:', err.stack || err.message)

// biome-ignore-all assist/source/organizeImports: ANT-ONLY import markers must not be reordered
```

### ESLint Block Suppressions

```typescript
/* eslint-disable @typescript-eslint/no-require-imports */
const SleepTool = feature('PROACTIVE')
  ? require('./tools/SleepTool/SleepTool.js').SleepTool
  : null
/* eslint-enable @typescript-eslint/no-require-imports */
```

## Silent Catch Comments

When a catch block intentionally does nothing, **always** explain why:

```typescript
} catch {
  // Silently fail if symlink creation fails
}

} catch {
  // pass
}

} catch {
  // Directory already exists
}

} catch (err) {
  // This should never happen since we catch at the Promise level, but defensive
  logError(toError(err))
}
```

## Constant Value Comments

Explain the significance of magic numbers and values:

```typescript
const DEFAULT_HEAD_LIMIT = 250
// 250 is generous enough for exploratory searches while preventing context bloat.
// Pass head_limit=0 explicitly for unlimited.

const PROGRESS_THRESHOLD_MS = 2000 // Show progress after 2 seconds

// In assistant mode, blocking bash auto-backgrounds after this many ms in the main agent
const ASSISTANT_BLOCKING_BUDGET_MS = 15_000

// 20K chars - tool result persistence threshold
maxResultSizeChars: 20_000,
```

## Inline End-of-Line Comments

Short clarifying comments at the end of a line:

```typescript
value: i, // hack: overwritten after sorting, right below this
numLines: z.number().optional(), // For content mode
numMatches: z.number().optional(), // For count mode
appliedLimit: z.number().optional(), // The limit that was applied (if any)
```

## File-Level Module Comments

```typescript
// In-memory error log for recent errors
// Moved from bootstrap/state.ts to break import cycle
const MAX_IN_MEMORY_ERRORS = 100

// In its own file to avoid circular dependencies
export const FILE_EDIT_TOOL_NAME = 'Edit'
```

## Comments Explaining What NOT to Do

```typescript
// SECURITY: Skip filesystem operations for UNC paths to prevent NTLM credential leaks.
if (absolutePath.startsWith('\\\\') || absolutePath.startsWith('//')) {
  return { result: true }
}

// Note: ripgrep only applies gitignore patterns relative to the working directory
// So for non-absolute paths, we need to prefix them with '**'
```

## TODO Comments

```typescript
// TODO: Add support for streaming responses
// TODO: Consider memoizing this computation
```

## Comments on Process.env Checks

```typescript
// Non-ants only write debug logs when debug mode is active (via --debug at
// startup or /debug mid-session). Ants always log for /share, bug reports.
if (process.env.USER_TYPE !== 'ant' && !isDebugMode()) {
  return false
}

// Cloud providers (Bedrock/Vertex/Foundry) always disable features
if (
  isEnvTruthy(process.env.CLAUDE_CODE_USE_BEDROCK) ||
  isEnvTruthy(process.env.CLAUDE_CODE_USE_VERTEX) ||
  isEnvTruthy(process.env.CLAUDE_CODE_USE_FOUNDRY)
) {
  return
}
```

## Summary of Comment Types

| Comment Type | Format | When to Use |
|---|---|---|
| Public API docs | `/** ... */` JSDoc | All exported functions, classes, types |
| Property docs | `/** ... */` | Non-obvious type properties |
| Implementation notes | `//` | Explaining why, business logic, non-obvious code |
| Section headers | `// ── ... ──` or `// ===` | Long files, build scripts |
| PR references | `// PR #NNNN ...` | Historical context for decisions |
| Lint suppression | `// eslint-disable...` + reason | Every lint suppression |
| Silent catch | `// pass` or `// Silently fail...` | Empty catch blocks |
| Constant explanation | `//` after or before constant | Magic numbers, non-obvious values |
| TODO | `// TODO: ...` | Planned future work |
| Module context | `//` at top of file | Import cycle breaks, ownership |
