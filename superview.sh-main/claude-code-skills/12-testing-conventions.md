# Testing Conventions

This document covers every testing pattern and convention used in the Claude Code codebase. Tests use Vitest and follow specific patterns for resettability, determinism, and isolation.

## Test Framework

- **Vitest** — Test runner (Jest-compatible API)
- **Configuration** in `vitest.config.*`
- Run with: `npm test` or `npx vitest`

## Reset Helpers for Module State

Since the codebase uses module-level state extensively, every stateful module provides a `_reset*ForTesting()` function:

### Pattern: `_resetForTesting()`

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

### Naming Convention

- Prefix with `_` (indicates internal/private)
- Include `ForTesting` suffix
- Tag with `@internal` in JSDoc
- Reset ALL module-level mutable state

### Usage in Tests

```typescript
import { _resetErrorLogForTesting } from '../src/utils/log.js'

beforeEach(() => {
  _resetErrorLogForTesting()
})

afterEach(() => {
  _resetErrorLogForTesting()
})
```

## `NODE_ENV` Guards

Production code uses `process.env.NODE_ENV === 'test'` to alter behavior in tests:

### Suppressing Side Effects

```typescript
function shouldLogDebugMessage(message: string): boolean {
  // Don't write debug logs during tests (noisy, filesystem side effects)
  if (process.env.NODE_ENV === 'test' && !isDebugToStdErr()) {
    return false
  }
  // ... normal logic
}
```

### Deterministic Sorting

```typescript
const sortedMatches = results
  .map((_, i) => [_, stats[i]!] as const)
  .sort((a, b) => {
    if (process.env.NODE_ENV === 'test') {
      // In tests, always sort by filename for deterministic results
      return a[0].localeCompare(b[0])
    }
    // In production, sort by modification time
    return b[1] - a[1]
  })
```

### Test-Only Behavior

```typescript
// Disable error reporting in tests
if (process.env.NODE_ENV === 'test') {
  return
}
```

## Test-Only Exports

Some modules export values exclusively for testing:

### Test-Only Tool Implementations

```typescript
// src/tools/testing/
// Contains tool implementations only used in tests
export const TestingPermissionTool = buildTool({
  name: 'TestingPermission',
  // ... simplified for testing
})
```

### Exported for Testing Comments

```typescript
// Exported for testing purposes
export const getDebugFilter = memoize((): DebugFilter | null => { ... })
```

## Deterministic Output

Tests must produce deterministic results. Key patterns:

### Sort by Name in Tests

```typescript
if (process.env.NODE_ENV === 'test') {
  return a[0].localeCompare(b[0])  // Alphabetical, not by mtime
}
```

### Fixed Timestamps

Use fixed dates/timestamps in test fixtures instead of `Date.now()`.

### Seeded Random Values

When randomness is needed, use deterministic seeds in tests.

## Test File Organization

Tests typically mirror the source structure:

```
src/
├── utils/
│   ├── errors.ts
│   └── __tests__/
│       └── errors.test.ts
├── tools/
│   ├── GrepTool/
│   │   ├── GrepTool.ts
│   │   └── __tests__/
│   │       └── GrepTool.test.ts
```

Or in a top-level `test/` directory:

```
test/
├── utils/
│   └── errors.test.ts
├── tools/
│   └── GrepTool.test.ts
```

## Mocking Patterns

### Mocking Module-Level State

Use the `_resetForTesting()` helpers rather than mocking internals:

```typescript
beforeEach(() => {
  _resetErrorLogForTesting()
})
```

### Mocking Environment Variables

```typescript
beforeEach(() => {
  process.env.NODE_ENV = 'test'
  process.env.USER_TYPE = 'ant'
})

afterEach(() => {
  delete process.env.USER_TYPE
})
```

### Clearing Memoize Caches

```typescript
beforeEach(() => {
  isDebugMode.cache.clear?.()
  getDebugFilter.cache.clear?.()
})
```

## Test Naming

Follow descriptive test names that explain the behavior:

```typescript
describe('toError', () => {
  it('returns the same Error if given an Error', () => { ... })
  it('wraps a string in a new Error', () => { ... })
  it('converts undefined to Error("undefined")', () => { ... })
})

describe('isENOENT', () => {
  it('returns true for ENOENT errors', () => { ... })
  it('returns false for other errno codes', () => { ... })
  it('returns false for non-Error values', () => { ... })
})
```

## Promise Testing

### Testing Async Functions

```typescript
it('handles abort signal', async () => {
  const controller = new AbortController()
  const promise = sleep(10000, controller.signal)
  controller.abort()
  await promise  // Should resolve immediately
})
```

### Testing Timeouts

```typescript
it('rejects after timeout', async () => {
  const slowPromise = new Promise(() => {})  // Never resolves
  await expect(
    withTimeout(slowPromise, 100, 'Timed out')
  ).rejects.toThrow('Timed out')
})
```

## Integration Testing Patterns

### Testing Tools

```typescript
it('searches for pattern in files', async () => {
  const result = await GrepTool.call(
    { pattern: 'function', path: testDir },
    mockContext,
  )
  expect(result.data.numFiles).toBeGreaterThan(0)
})
```

### Testing Commands

```typescript
it('compacts conversation', async () => {
  const result = await call('', mockContext)
  expect(result.type).toBe('compact')
})
```

## Key Testing Guidelines

1. **Always reset module state** in `beforeEach`/`afterEach`
2. **Use `NODE_ENV === 'test'` guards** for non-deterministic behavior
3. **Sort deterministically** in tests (by name, not by time)
4. **Don't test internal implementation** — test public API behavior
5. **Mock at boundaries** (filesystem, network) not at function level
6. **Clear memoize caches** between tests to prevent state leakage
7. **Use descriptive test names** that explain expected behavior
8. **Keep test files close** to the code they test
