# Import Conventions

This document covers every import pattern used in the Claude Code codebase. Following these conventions exactly is critical — the build system, dead code elimination, and module resolution all depend on them.

## Rule 1: Always Use `.js` Extensions on Relative Imports

TypeScript ESM convention. The compiled output is `.js`, so all relative imports must use `.js` extensions, even though the source files are `.ts` or `.tsx`:

```typescript
// CORRECT — .js extension on relative imports
import { getCwd } from '../../utils/cwd.js'
import { buildTool } from '../../Tool.js'
import { GREP_TOOL_NAME } from './prompt.js'

// WRONG — no extension or .ts extension
import { getCwd } from '../../utils/cwd'
import { buildTool } from '../../Tool.ts'
```

This applies to all relative imports regardless of the actual source file extension:
- `.ts` files → import as `.js`
- `.tsx` files → import as `.js` (not `.jsx`)

```typescript
// A .tsx file is still imported with .js
import { HelpV2 } from '../../components/HelpV2/HelpV2.js'
import { renderToolUseMessage } from './UI.js'  // UI.tsx → UI.js
```

## Rule 2: Separate `import type` from Value Imports

Always use `import type` for type-only imports. This ensures they are erased at compile time and don't create runtime dependencies:

```typescript
// Type-only imports — erased at compile time
import type { ToolResultBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import type { ToolDef, ValidationResult } from '../../Tool.js'
import type { AppState } from 'src/state/AppState.js'
import type { z } from 'zod/v4'
import type { UUID } from 'crypto'
```

When a module provides both types AND values, use **separate** import statements:

```typescript
// Value import
import { buildTool } from '../../Tool.js'
// Type import from the same module — separate statement
import type { ToolDef, ValidationResult, ToolUseContext } from '../../Tool.js'

// Another example — value + type from same module
import { z } from 'zod/v4'
import type { ZodSchema } from 'zod/v4'

// Inline type imports are also acceptable for mixed imports
import { buildTool, type ToolDef } from '../../Tool.js'
```

### When to Use Inline `type` Keyword

Sometimes you'll see the inline `type` keyword in a value import. This is used when you need both values and types from the same import:

```typescript
import {
  type LineEndingType,
  readFileSyncWithMetadata,
} from '../../utils/fileRead.js'

import {
  type AnalyticsMetadata_I_VERIFIED_THIS_IS_NOT_CODE_OR_FILEPATHS,
  logEvent,
} from '../../services/analytics/index.js'
```

## Rule 3: Cherry-Pick Lodash Imports

**Never** import all of lodash. Always import individual functions from `lodash-es`:

```typescript
// CORRECT — individual function imports from lodash-es
import memoize from 'lodash-es/memoize.js'
import uniqBy from 'lodash-es/uniqBy.js'
import groupBy from 'lodash-es/groupBy.js'
import sortBy from 'lodash-es/sortBy.js'

// WRONG — importing all of lodash
import _ from 'lodash'
import { memoize } from 'lodash'
import * as _ from 'lodash-es'
```

Note the `.js` extension even for `lodash-es` submodule imports.

## Rule 4: Zod v4 Import Path

Always import Zod from the v4 path:

```typescript
// CORRECT
import { z } from 'zod/v4'

// WRONG
import { z } from 'zod'
```

## Rule 5: Feature Flag Conditional Imports

The codebase uses `feature()` from `bun:bundle` combined with `require()` for dead code elimination. This pattern allows the build system to completely tree-shake unused modules:

```typescript
import { feature } from 'bun:bundle'

// Pattern: feature flag + conditional require + eslint disable/enable
/* eslint-disable @typescript-eslint/no-require-imports */
const SleepTool = feature('PROACTIVE')
  ? require('./tools/SleepTool/SleepTool.js').SleepTool
  : null
/* eslint-enable @typescript-eslint/no-require-imports */
```

### Multi-Module Conditional Import

```typescript
/* eslint-disable @typescript-eslint/no-require-imports */
const reactiveCompact = feature('REACTIVE_COMPACT')
  ? (require('../../services/compact/reactiveCompact.js') as typeof import('../../services/compact/reactiveCompact.js'))
  : null
/* eslint-enable @typescript-eslint/no-require-imports */
```

Note the type assertion `as typeof import(...)` to preserve type information even with `require()`.

### Using Conditionally Imported Values

Always null-check before using:

```typescript
if (SleepTool) {
  tools.push(SleepTool)
}

// Or with optional chaining
reactiveCompact?.someFunction()
```

### Key Rules for Feature Flag Imports:
1. Always wrap `require()` in `/* eslint-disable/enable */` comments
2. Default to `null` when the feature is disabled
3. Use `feature('FLAG_NAME')` — flags are UPPER_SNAKE_CASE
4. Add type assertion with `as typeof import(...)` for full module imports
5. Always null-check before using the imported value

## Rule 6: Bare `src/` Path Imports

Some files use bare `src/` path imports (the build system rewrites these to relative paths):

```typescript
// This is acceptable — build.mjs rewrites it to a relative path
import { getSessionId } from 'src/bootstrap/state.js'
import type { AppState } from 'src/state/AppState.js'
import type { CanUseToolFn } from 'src/hooks/useCanUseTool.js'
```

Both bare `src/` and relative `../../` paths are valid. The build system handles `src/` paths by converting them to relative paths. Prefer relative paths for new code — `src/` paths are a legacy pattern.

## Rule 7: NPM Package Imports

External packages are imported by their package name as usual:

```typescript
// SDK packages — note the deep import paths
import type { ToolResultBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'
import type { BetaMessageStreamParams } from '@anthropic-ai/sdk/resources/beta/messages/messages.mjs'

// Node built-ins
import { readdir, readFile, stat } from 'fs/promises'
import { dirname, join, isAbsolute, sep } from 'path'
import { copyFile, link } from 'fs/promises'

// Third-party
import chalk from 'chalk'
import * as React from 'react'
import React from 'react'
```

### React Import Style

Both patterns are used:
```typescript
import * as React from 'react'   // Namespace import (more common in .tsx files)
import React from 'react'         // Default import (also used)
```

## Rule 8: Import Order Preservation

When import order matters (rare), use the biome-ignore directive:

```typescript
// biome-ignore-all assist/source/organizeImports: ANT-ONLY import markers must not be reordered
import { z } from 'zod/v4'
import { lazySchema } from '../utils/lazySchema.js'
import {
  type HookEvent,
  HOOK_EVENTS,
  type HookInput,
} from 'src/entrypoints/agentSdkTypes.js'
```

## Rule 9: Breaking Import Cycles

The codebase has a specific strategy for breaking circular dependencies:

### Strategy 1: Extract Pure Types to `src/types/`

Move type definitions (no runtime code) to dedicated files in `src/types/`:

```typescript
// src/types/permissions.ts
/**
 * Pure permission type definitions extracted to break import cycles.
 *
 * This file contains only type definitions and constants with no runtime dependencies.
 * Implementation files remain in src/utils/permissions/ but can now import from here
 * to avoid circular dependencies.
 */
export type PermissionBehavior = 'allow' | 'deny' | 'ask'
export type PermissionRuleSource = 'userSettings' | 'projectSettings' | ...
```

### Strategy 2: Separate Constants Files

Extract constants (especially tool/command names) into tiny files:

```typescript
// src/tools/BashTool/toolName.ts
// In its own file to avoid circular dependencies
export const BASH_TOOL_NAME = 'Bash'

// src/tools/FileEditTool/constants.ts
// In its own file to avoid circular dependencies
export const FILE_EDIT_TOOL_NAME = 'Edit'
export const CLAUDE_FOLDER_PERMISSION_PATTERN = '/.claude/**'
```

### Strategy 3: Re-exports for Backwards Compatibility

When moving types out of a module, add re-exports so existing imports don't break:

```typescript
// Original module — add re-export
export type { ToolPermissionRulesBySource } from '../types/permissions.js'
```

### Strategy 4: Lazy Module Loading

Commands use lazy `load()` to defer heavy imports:

```typescript
const compact = {
  type: 'local',
  name: 'compact',
  description: 'Clear conversation history...',
  load: () => import('./compact.js'),  // Deferred import
} satisfies Command
```

## Common Import Groups (Typical File Order)

A well-organized file follows this approximate import order:

```typescript
// 1. Build-time features
import { feature } from 'bun:bundle'

// 2. External SDK/library types
import type { ToolResultBlockParam } from '@anthropic-ai/sdk/resources/index.mjs'

// 3. External libraries (values)
import { readdir, readFile } from 'fs/promises'
import memoize from 'lodash-es/memoize.js'
import { join } from 'path'
import { z } from 'zod/v4'

// 4. Internal types
import type { AppState } from 'src/state/AppState.js'
import type { ToolDef, ValidationResult } from '../../Tool.js'

// 5. Internal values
import { buildTool } from '../../Tool.js'
import { getCwd } from '../../utils/cwd.js'
import { isENOENT } from '../../utils/errors.js'
import { lazySchema } from '../../utils/lazySchema.js'

// 6. Local/sibling imports
import { GREP_TOOL_NAME, getDescription } from './prompt.js'
import { renderToolUseMessage, renderToolResultMessage } from './UI.js'
```

The exact order is not strictly enforced (Biome handles some reordering), but the general grouping pattern is consistent.
