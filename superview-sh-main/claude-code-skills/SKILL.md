---
name: claude-code-dev
description: How to develop, modify, and extend the Claude Code codebase following its established programming style, patterns, and conventions. Use this skill whenever working on the claude-code source — adding tools, commands, utils, components, types, hooks, services, or fixing bugs. Also use when the user asks about claude-code architecture, coding standards, file organization, or wants to understand how the codebase works. This skill ensures all contributions match the existing codebase style exactly.
---

# Claude Code Development Style Guide

This skill captures the programming style, patterns, and conventions used in the Claude Code codebase (`@anthropic-ai/claude-code`). Each topic below links to a dedicated deep-dive document with comprehensive examples and rules extracted from the actual source.

## Summary

**Claude Code** is an ESM TypeScript Node.js CLI application using Ink (React for terminals) for its UI, esbuild for transpilation, and Bun internally for feature flags and dead code elimination. Key stack: TypeScript, Zod v4, lodash-es, React/Ink, esbuild.

## Detailed Guides (Resource Files)

Each topic below is covered in depth in its own resource file within this skill's directory. Read the relevant file before working on that area of the codebase.

| # | Topic | File | Summary |
|---|---|---|---|
| 01 | **Project Overview** | `01-project-overview.md` | Tech stack, build system, runtime environment, key dependencies |
| 02 | **Directory Structure** | `02-directory-structure.md` | Full `src/` layout, file organization patterns, where things go |
| 03 | **Import Conventions** | `03-import-conventions.md` | `.js` extensions, `import type`, lodash cherry-picks, feature flags, cycle breaking |
| 04 | **Naming Conventions** | `04-naming-conventions.md` | camelCase/PascalCase/UPPER_SNAKE rules, file naming, safety names |
| 05 | **TypeScript Patterns** | `05-typescript-patterns.md` | Branded types, discriminated unions, `as const`, `satisfies`, Zod schemas, generics |
| 06 | **Commenting Style** | `06-commenting-style.md` | JSDoc, why-not-what philosophy, PR references, section headers, lint suppression |
| 07 | **Error Handling** | `07-error-handling.md` | Custom error classes, utility functions, graceful degradation, catch conventions |
| 08 | **Function Patterns** | `08-function-patterns.md` | `buildTool()` factory, memoize, async generators, guard clauses, fire-and-forget |
| 09 | **Tool Architecture** | `09-tool-architecture.md` | Tool directory structure, `buildTool()` API, schemas, permissions, UI rendering |
| 10 | **Command Architecture** | `10-command-architecture.md` | Command types, index.ts pattern, lazy loading, registration |
| 11 | **State Management** | `11-state-management.md` | Module-level state, getter/setter, AppState threading, cleanup registry |
| 12 | **Testing Conventions** | `12-testing-conventions.md` | Reset helpers, NODE_ENV guards, test-only exports, deterministic sorting |
| 13 | **Formatting Rules** | `13-formatting-rules.md` | No semicolons, single quotes, trailing commas, indentation, expression style |
| 14 | **Quick References** | `14-quick-references.md` | Step-by-step checklists for adding tools, commands, utils, and types |
