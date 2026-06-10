# Tool Architecture

This document covers the complete architecture of model-invocable tools in the Claude Code codebase. Tools are the primary way Claude interacts with the user's system — reading files, running commands, editing code, searching, etc.

## Overview

Tools are defined in `src/tools/`, registered in `src/tools.ts`, and built using the `buildTool()` factory from `src/Tool.ts`. Each tool is a self-contained module with its own directory.

## Directory Structure

### Minimal Tool (3 files)

```
src/tools/GrepTool/
├── GrepTool.ts     # Core logic + buildTool() call
├── prompt.ts       # Tool name constant + getDescription()
└── UI.tsx          # React rendering functions
```

### Standard Tool (5-6 files)

```
src/tools/FileEditTool/
├── FileEditTool.ts  # Core logic + buildTool() call
├── prompt.ts        # Description function
├── constants.ts     # Name + shared constants (cycle-breaking)
├── types.ts         # Zod schemas + TypeScript types
├── utils.ts         # Tool-specific helper functions
└── UI.tsx           # React rendering functions
```

### Complex Tool (many files)

```
src/tools/BashTool/
├── BashTool.tsx           # Main tool implementation (~1100 lines)
├── UI.tsx                 # React rendering
├── BashToolResultMessage.tsx  # Specialized result component
├── prompt.ts              # Description + timeout defaults
├── toolName.ts            # Name constant (separate for cycles)
├── bashPermissions.ts     # Permission matching logic
├── bashSecurity.ts        # Security validation
├── commandSemantics.ts    # Command classification
├── modeValidation.ts      # Plan/read-only mode checks
├── pathValidation.ts      # Path validation
├── readOnlyValidation.ts  # Read-only constraint checking
├── sedEditParser.ts       # Sed command parsing
├── sedValidation.ts       # Sed command validation
├── shouldUseSandbox.ts    # Sandbox decision logic
├── commentLabel.ts        # Comment label extraction
├── destructiveCommandWarning.ts  # Warning generation
└── utils.ts               # General tool utilities
```

## File-by-File Breakdown

### `prompt.ts` — Tool Name and Description

Every tool has a `prompt.ts` that exports the tool name as a constant and a description function:

```typescript
// src/tools/GrepTool/prompt.ts
import { AGENT_TOOL_NAME } from '../AgentTool/constants.js'
import { BASH_TOOL_NAME } from '../BashTool/toolName.js'

export const GREP_TOOL_NAME = 'Grep'

export function getDescription(): string {
  return `A powerful search tool built on ripgrep

  Usage:
  - ALWAYS use ${GREP_TOOL_NAME} for search tasks. NEVER invoke \`grep\` or \`rg\` as a ${BASH_TOOL_NAME} command.
  - Supports full regex syntax (e.g., "log.*Error", "function\\s+\\w+")
  ...
`
}
```

**Key conventions:**
- Name constant is `UPPER_SNAKE_CASE` with `_TOOL_NAME` suffix
- Description function returns a template literal with usage guidance
- Description references other tools by their name constants (not hard-coded strings)
- Description is the text the model sees to decide whether to use the tool

### `constants.ts` — Shared Constants (Cycle-Breaking)

When the tool name or other constants are needed by other modules that would create import cycles, extract them:

```typescript
// src/tools/FileEditTool/constants.ts
// In its own file to avoid circular dependencies
export const FILE_EDIT_TOOL_NAME = 'Edit'

export const CLAUDE_FOLDER_PERMISSION_PATTERN = '/.claude/**'
export const GLOBAL_CLAUDE_FOLDER_PERMISSION_PATTERN = '~/.claude/**'

export const FILE_UNEXPECTEDLY_MODIFIED_ERROR =
  'File has been unexpectedly modified. Read it again before attempting to write it.'
```

### `types.ts` — Zod Schemas and TypeScript Types

For tools with complex input/output, extract schemas to a dedicated file:

```typescript
// src/tools/FileEditTool/types.ts
import { z } from 'zod/v4'
import { lazySchema } from '../../utils/lazySchema.js'
import { semanticBoolean } from '../../utils/semanticBoolean.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    file_path: z.string().describe('The absolute path to the file to modify'),
    old_string: z.string().describe('The text to replace'),
    new_string: z.string().describe('The text to replace it with'),
    replace_all: semanticBoolean(
      z.boolean().default(false).optional(),
    ).describe('Replace all occurrences (default false)'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

// Parsed output type (z.output for preprocessed schemas)
export type FileEditInput = z.output<InputSchema>

// Derived types
export type EditInput = Omit<FileEditInput, 'file_path'>
export type FileEdit = {
  old_string: string
  new_string: string
  replace_all: boolean
}

const outputSchema = lazySchema(() =>
  z.object({
    filePath: z.string(),
    oldString: z.string(),
    newString: z.string(),
    structuredPatch: z.array(hunkSchema()),
    userModified: z.boolean(),
    replaceAll: z.boolean(),
    gitDiff: gitDiffSchema().optional(),
  }),
)
type OutputSchema = ReturnType<typeof outputSchema>
export type FileEditOutput = z.infer<OutputSchema>

export { inputSchema, outputSchema }
```

### `ToolName.ts` — Main Tool Implementation

The main file exports the tool via `buildTool()`:

```typescript
// src/tools/GrepTool/GrepTool.ts
import { z } from 'zod/v4'
import type { ValidationResult } from '../../Tool.js'
import { buildTool, type ToolDef } from '../../Tool.js'
import { getCwd } from '../../utils/cwd.js'
import { isENOENT } from '../../utils/errors.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { GREP_TOOL_NAME, getDescription } from './prompt.js'
import { getToolUseSummary, renderToolResultMessage, renderToolUseMessage } from './UI.js'

// Schema definition (inline for simple tools, or imported from types.ts)
const inputSchema = lazySchema(() =>
  z.strictObject({
    pattern: z.string().describe('The regex pattern to search for'),
    path: z.string().optional().describe('File or directory to search in'),
    // ...
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

// Constants
const DEFAULT_HEAD_LIMIT = 250

// Helper functions
function applyHeadLimit<T>(items: T[], limit: number | undefined): { ... }

// The tool definition
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

  getToolUseSummary,

  getActivityDescription(input) {
    const summary = getToolUseSummary(input)
    return summary ? `Searching for ${summary}` : 'Searching'
  },

  get inputSchema(): InputSchema {
    return inputSchema()
  },

  isConcurrencySafe() { return true },
  isReadOnly() { return true },

  getPath({ path }): string {
    return path || getCwd()
  },

  async validateInput({ path }): Promise<ValidationResult> {
    if (path) {
      try {
        await fs.stat(expandPath(path))
      } catch (e) {
        if (isENOENT(e)) {
          return { result: false, message: `Path does not exist: ${path}` }
        }
        throw e
      }
    }
    return { result: true }
  },

  async checkPermissions(input, context): Promise<PermissionDecision> {
    return checkReadPermissionForTool(GrepTool, input, ...)
  },

  async prompt() {
    return getDescription()
  },

  renderToolUseMessage,
  renderToolUseErrorMessage,
  renderToolResultMessage,

  mapToolResultToToolResultBlockParam(output, toolUseID) {
    // Format tool result for the API
    return {
      tool_use_id: toolUseID,
      type: 'tool_result',
      content: formattedContent,
    }
  },

  async call(input, { abortController, getAppState }) {
    // Main tool execution
    const results = await ripGrep(args, absolutePath, abortController.signal)
    return { data: output }
  },
} satisfies ToolDef<InputSchema, Output>)
```

### `UI.tsx` — React Rendering

Every tool needs rendering functions for the Ink terminal UI:

```typescript
// src/tools/GrepTool/UI.tsx
import type { ToolResultBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import React from 'react'
import { MessageResponse } from '../../components/MessageResponse.js'
import { Box, Text } from '../../ink.js'

// Summary for the collapsed view
export function getToolUseSummary(input: Partial<{
  pattern: string
  path?: string
}>): string | null {
  if (!input?.pattern) return null
  return truncate(input.pattern, TOOL_SUMMARY_MAX_LENGTH)
}

// Renders the tool use (what the model asked to do)
export function renderToolUseMessage(
  { pattern, path }: Partial<{ pattern: string; path?: string }>,
  { verbose }: { verbose: boolean },
): React.ReactNode {
  if (!pattern) return null
  const parts = [`pattern: "${pattern}"`]
  if (path) parts.push(`path: "${verbose ? path : getDisplayPath(path)}"`)
  return parts.join(', ')
}

// Renders errors
export function renderToolUseErrorMessage(
  result: ToolResultBlockParam['content'],
  { verbose }: { verbose: boolean },
): React.ReactNode {
  if (!verbose && typeof result === 'string') {
    return <MessageResponse><Text color="error">Error searching files</Text></MessageResponse>
  }
  return <FallbackToolUseErrorMessage result={result} verbose={verbose} />
}

// Renders the tool result (what was returned)
export function renderToolResultMessage(
  output: Output,
  _progressMessages: ProgressMessage<ToolProgressData>[],
  { verbose }: { verbose: boolean },
): React.ReactNode {
  return <SearchResultSummary count={output.numFiles} countLabel="files" ... />
}
```

## Tool Registration

Tools are registered in `src/tools.ts`:

```typescript
// src/tools.ts
import { GrepTool } from './tools/GrepTool/GrepTool.js'
import { FileEditTool } from './tools/FileEditTool/FileEditTool.js'
// ...

export function getAllBaseTools(): Tool[] {
  return [
    GrepTool,
    FileEditTool,
    FileReadTool,
    FileWriteTool,
    BashTool,
    GlobTool,
    // Conditional tools
    ...(SleepTool ? [SleepTool] : []),
    // ...
  ]
}
```

## Tool Lifecycle

1. **Registration** — Tool is imported and added to `getAllBaseTools()` in `tools.ts`
2. **Assembly** — `assembleToolPool()` filters tools by permissions, environment, deny rules
3. **Description** — Model receives tool descriptions in the system prompt
4. **Invocation** — Model requests tool use with input JSON
5. **Validation** — `validateInput()` checks input validity
6. **Permission** — `checkPermissions()` checks if the user has granted permission
7. **Execution** — `call()` runs the tool logic
8. **Result** — Output is formatted via `mapToolResultToToolResultBlockParam()`
9. **Rendering** — Ink renders the result via `renderToolResultMessage()`

## Schema Conventions

### Input Schemas — `z.strictObject()`

Always use `z.strictObject()` (rejects unknown keys) for tool inputs:

```typescript
const inputSchema = lazySchema(() =>
  z.strictObject({
    pattern: z.string().describe('The regex pattern'),
    path: z.string().optional().describe('Search path'),
  }),
)
```

### Output Schemas — `z.object()`

Output schemas use regular `z.object()`:

```typescript
const outputSchema = lazySchema(() =>
  z.object({
    numFiles: z.number(),
    filenames: z.array(z.string()),
    content: z.string().optional(),
  }),
)
```

### Semantic Type Wrappers

For model-facing parameters that might be sent as strings:

```typescript
import { semanticBoolean } from '../../utils/semanticBoolean.js'
import { semanticNumber } from '../../utils/semanticNumber.js'

// Accepts: true, false, "true", "false", 1, 0, "yes", "no"
replace_all: semanticBoolean(z.boolean().default(false).optional()),

// Accepts: 5, "5", 5.0
head_limit: semanticNumber(z.number().optional()),
```

## Permission Patterns

### Read-Only Tools

```typescript
async checkPermissions(input, context): Promise<PermissionDecision> {
  return checkReadPermissionForTool(
    GrepTool,
    input,
    context.getAppState().toolPermissionContext,
  )
}
```

### Write Tools

```typescript
async checkPermissions(input, context): Promise<PermissionDecision> {
  return checkWritePermissionForTool(
    FileEditTool,
    input,
    context.getAppState().toolPermissionContext,
  )
}
```

### Custom Permission Matching

```typescript
async preparePermissionMatcher({ pattern }) {
  return rulePattern => matchWildcardPattern(rulePattern, pattern)
}
```

## Tool Call Return Values

### Success

```typescript
return { data: output }
```

### Success with Diff (for edit tools)

```typescript
return {
  data: output,
  resultForAssistant: {
    type: 'tool_result',
    tool_use_id: toolUseID,
    content: diffContent,
  },
}
```

## All Current Tools (42 Directories)

| Tool | Purpose | Read-Only |
|---|---|---|
| `AgentTool` | Spawn subagents | No |
| `AskUserQuestionTool` | Ask user a question | Yes |
| `BashTool` | Execute shell commands | No |
| `BriefTool` | Brief text generation | Yes |
| `ConfigTool` | Read/write config | No |
| `FileEditTool` | Edit file contents | No |
| `FileReadTool` | Read file contents | Yes |
| `FileWriteTool` | Write new files | No |
| `GlobTool` | File pattern matching | Yes |
| `GrepTool` | Ripgrep search | Yes |
| `LSPTool` | Language Server Protocol | Yes |
| `MCPTool` | MCP tool proxy | Varies |
| `NotebookEditTool` | Edit Jupyter notebooks | No |
| `SkillTool` | Invoke skills | Yes |
| `TaskCreateTool` | Create background tasks | No |
| `TaskGetTool` | Get task status | Yes |
| `TaskListTool` | List tasks | Yes |
| `TodoWriteTool` | Write todo items | No |
| `ToolSearchTool` | Search available tools | Yes |
| `WebFetchTool` | Fetch URL content | Yes |
| `WebSearchTool` | Web search | Yes |
| And more... | | |
