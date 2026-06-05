# Quick References

Step-by-step checklists for common development tasks in the Claude Code codebase.

---

## Adding a New Tool

### Step 1: Create the Directory

```
src/tools/MyTool/
```

Directory name must be **PascalCase** matching the tool name.

### Step 2: Create `prompt.ts`

```typescript
// src/tools/MyTool/prompt.ts
export const MY_TOOL_NAME = 'MyTool'

export function getDescription(): string {
  return `Description of what the tool does.

  Usage:
  - When to use this tool
  - Key capabilities
  - Important constraints
`
}
```

### Step 3: Create `MyTool.ts`

```typescript
// src/tools/MyTool/MyTool.ts
import { z } from 'zod/v4'
import type { ValidationResult } from '../../Tool.js'
import { buildTool, type ToolDef } from '../../Tool.js'
import { getCwd } from '../../utils/cwd.js'
import { lazySchema } from '../../utils/lazySchema.js'
import { MY_TOOL_NAME, getDescription } from './prompt.js'
import {
  getToolUseSummary,
  renderToolResultMessage,
  renderToolUseErrorMessage,
  renderToolUseMessage,
} from './UI.js'

const inputSchema = lazySchema(() =>
  z.strictObject({
    param1: z.string().describe('Description of param1'),
    param2: z.string().optional().describe('Optional parameter'),
  }),
)
type InputSchema = ReturnType<typeof inputSchema>

const outputSchema = lazySchema(() =>
  z.object({
    result: z.string(),
    count: z.number(),
  }),
)
type OutputSchema = ReturnType<typeof outputSchema>
type Output = z.infer<OutputSchema>

export const MyTool = buildTool({
  name: MY_TOOL_NAME,
  searchHint: 'brief capability phrase for search',
  maxResultSizeChars: 20_000,
  strict: true,

  async description() {
    return getDescription()
  },

  userFacingName() {
    return 'My Tool'
  },

  getToolUseSummary,

  getActivityDescription(input) {
    const summary = getToolUseSummary(input)
    return summary ? `Running ${summary}` : 'Running tool'
  },

  get inputSchema(): InputSchema {
    return inputSchema()
  },

  get outputSchema(): OutputSchema {
    return outputSchema()
  },

  isConcurrencySafe() {
    return true  // Can it run in parallel with other tools?
  },

  isReadOnly() {
    return true  // Does it modify the filesystem or state?
  },

  async prompt() {
    return getDescription()
  },

  renderToolUseMessage,
  renderToolUseErrorMessage,
  renderToolResultMessage,

  async call(
    { param1, param2 },
    { abortController, getAppState },
  ) {
    // Main tool logic
    const result = await doWork(param1, param2)

    return {
      data: {
        result: result.text,
        count: result.count,
      },
    }
  },
} satisfies ToolDef<InputSchema, Output>)
```

### Step 4: Create `UI.tsx`

```typescript
// src/tools/MyTool/UI.tsx
import type { ToolResultBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import React from 'react'
import { FallbackToolUseErrorMessage } from '../../components/FallbackToolUseErrorMessage.js'
import { MessageResponse } from '../../components/MessageResponse.js'
import { TOOL_SUMMARY_MAX_LENGTH } from '../../constants/toolLimits.js'
import { Text } from '../../ink.js'
import { truncate } from '../../utils/format.js'

type Output = {
  result: string
  count: number
}

export function getToolUseSummary(
  input: Partial<{ param1: string }> | undefined,
): string | null {
  if (!input?.param1) return null
  return truncate(input.param1, TOOL_SUMMARY_MAX_LENGTH)
}

export function renderToolUseMessage(
  { param1 }: Partial<{ param1: string }>,
  { verbose }: { verbose: boolean },
): React.ReactNode {
  if (!param1) return null
  return `param1: "${param1}"`
}

export function renderToolUseErrorMessage(
  result: ToolResultBlockParam['content'],
  { verbose }: { verbose: boolean },
): React.ReactNode {
  return <FallbackToolUseErrorMessage result={result} verbose={verbose} />
}

export function renderToolResultMessage(
  { result, count }: Output,
  _progressMessages: unknown[],
  { verbose }: { verbose: boolean },
): React.ReactNode {
  return (
    <MessageResponse>
      <Text>
        Found <Text bold>{count}</Text> results
      </Text>
    </MessageResponse>
  )
}
```

### Step 5: Register in `src/tools.ts`

```typescript
// Add import
import { MyTool } from './tools/MyTool/MyTool.js'

// Add to getAllBaseTools()
export function getAllBaseTools(): Tool[] {
  return [
    // ... existing tools
    MyTool,
  ]
}
```

### Checklist

- [ ] Directory: `src/tools/MyTool/` (PascalCase)
- [ ] `prompt.ts`: `MY_TOOL_NAME` constant + `getDescription()` function
- [ ] `MyTool.ts`: `buildTool({ ... }) satisfies ToolDef<InputSchema, Output>`
- [ ] `UI.tsx`: `getToolUseSummary`, `renderToolUseMessage`, `renderToolResultMessage`, `renderToolUseErrorMessage`
- [ ] Registered in `src/tools.ts`
- [ ] Input schema uses `lazySchema(() => z.strictObject({ ... }))`
- [ ] All relative imports use `.js` extension
- [ ] Type-only imports use `import type`
- [ ] No semicolons, single quotes, trailing commas

---

## Adding a New Command

### Step 1: Create the Directory

```
src/commands/my-command/
```

Directory name must be **kebab-case**.

### Step 2: Create the Implementation

**For a local command** (`my-command.ts`):

```typescript
// src/commands/my-command/my-command.ts
import type { LocalCommandCall } from '../../types/command.js'

export const call: LocalCommandCall = async (args, context) => {
  const { abortController, messages } = context
  const trimmedArgs = args.trim()

  // Command logic here

  return {
    type: 'text',
    value: `Result: ${trimmedArgs}`,
  }
}
```

**For a JSX command** (`my-command.tsx`):

```typescript
// src/commands/my-command/my-command.tsx
import * as React from 'react'
import type { LocalJSXCommandCall } from '../../types/command.js'
import { MyComponent } from '../../components/MyComponent.js'

export const call: LocalJSXCommandCall = async (onDone, context, args) => {
  return <MyComponent args={args} onClose={onDone} />
}
```

### Step 3: Create `index.ts`

```typescript
// src/commands/my-command/index.ts
import type { Command } from '../../commands.js'

const myCommand = {
  type: 'local',           // or 'local-jsx'
  name: 'my-command',
  description: 'What this command does',
  supportsNonInteractive: false,
  load: () => import('./my-command.js'),
} satisfies Command

export default myCommand
```

### Step 4: Register in `src/commands.ts`

```typescript
// Add import
import myCommand from './commands/my-command/index.js'

// Add to COMMANDS()
export const COMMANDS = memoize(() => [
  // ... existing commands
  myCommand,
])
```

### Checklist

- [ ] Directory: `src/commands/my-command/` (kebab-case)
- [ ] Implementation: `my-command.ts` or `my-command.tsx`
- [ ] Registration: `index.ts` with `satisfies Command` and `export default`
- [ ] Registered in `src/commands.ts` COMMANDS array
- [ ] `load: () => import('./my-command.js')` for lazy loading
- [ ] All relative imports use `.js` extension
- [ ] No semicolons, single quotes, trailing commas

---

## Adding a New Utility Function

### Step 1: Choose the Right Location

| Utility Type | File |
|---|---|
| Error handling | `src/utils/errors.ts` |
| File operations | `src/utils/file.ts` |
| Path manipulation | `src/utils/path.ts` |
| String operations | `src/utils/stringUtils.ts` |
| Environment checks | `src/utils/envUtils.ts` |
| Format/display | `src/utils/format.ts` |
| New domain | `src/utils/myNewUtil.ts` (camelCase) |

### Step 2: Write the Function

```typescript
/**
 * Brief description of what the function does.
 * Explain when to use it and any important caveats.
 */
export function myUtilFunction(param: string, options?: { flag?: boolean }): string {
  if (!param) {
    return ''
  }
  // Implementation
  return result
}
```

### Checklist

- [ ] JSDoc comment with purpose and usage context
- [ ] Exported with `export function` (named export)
- [ ] Return type annotated explicitly
- [ ] Guard clauses for edge cases
- [ ] No semicolons, single quotes, trailing commas
- [ ] If stateful, provide `_resetForTesting()` helper

---

## Adding a New Type

### Step 1: Choose the Right Location

| Type Category | File |
|---|---|
| Pure types (no runtime deps) | `src/types/myTypes.ts` |
| Types tied to a module | Same file as the module |
| Complex schemas | Dedicated `types.ts` in tool/service directory |

### Step 2: Write the Type

```typescript
// src/types/myTypes.ts

/**
 * Description of what this type represents.
 */
export type MyNewType = {
  /** Description of this field */
  id: string
  /** Description of this field */
  status: 'active' | 'inactive'
  /** Optional field with default behavior */
  metadata?: Record<string, unknown>
}
```

### Checklist

- [ ] JSDoc on the type and non-obvious properties
- [ ] Use `type` (not `interface`) — the codebase prefers `type`
- [ ] String literal unions (not `enum`) for status/mode fields
- [ ] `as const` arrays when runtime validation of values is needed
- [ ] No runtime dependencies in `src/types/` files
- [ ] `export type` when re-exporting

---

## Code Review Checklist

Before submitting any change, verify:

### Imports
- [ ] `.js` extension on all relative imports
- [ ] `import type` for type-only imports
- [ ] Cherry-picked lodash (`import memoize from 'lodash-es/memoize.js'`)
- [ ] Zod from `'zod/v4'`

### Naming
- [ ] `camelCase` for functions and variables
- [ ] `PascalCase` for types, classes, components
- [ ] `UPPER_SNAKE_CASE` for constants
- [ ] `_` prefix for unused parameters

### Style
- [ ] No semicolons
- [ ] Single quotes
- [ ] Trailing commas
- [ ] 2-space indentation

### Error Handling
- [ ] `toError()` / `errorMessage()` at catch boundaries (not raw casts)
- [ ] `isENOENT()` / `isFsInaccessible()` for fs errors (not `(e as ...).code`)
- [ ] `logError()` for error logging
- [ ] Graceful fallbacks, not crashes

### Comments
- [ ] JSDoc on exported APIs
- [ ] Comments explain *why*, not *what*
- [ ] Lint suppressions include explanations
- [ ] Silent catches have explanatory comments

### TypeScript
- [ ] No `any` (use `unknown` and narrow)
- [ ] Branded types for IDs
- [ ] `satisfies` on tool/command definitions
- [ ] `as const` on literal arrays
