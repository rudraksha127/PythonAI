import * as vscode from "vscode";
import * as crypto from "crypto";
import { SignalTracker, PendingSuggestion } from "./signalTracker";

/**
 * Configuration for how suggestions are generated.
 */
export interface CompletionProviderConfig {
  /** Whether to trigger on every keystroke (true) or only on explicit trigger */
  autoTrigger: boolean;

  /** Minimum delay (ms) between trigger and showing a suggestion */
  debounceMs: number;

  /** The AI model to use for generating suggestions */
  model: string;

  /** Whether the AI endpoint is available */
  aiAvailable: boolean;
}

/**
 * ForgeAI Inline Completion Provider.
 *
 * Provides inline code suggestions via VS Code's InlineCompletionItemProvider
 * API and tracks accept/reject/edit events via the SignalTracker.
 *
 * The provider generates suggestions using a local AI endpoint and reports
 * developer feedback signals back to the CaptureEngine database.
 */
export class ForgeAICompletionProvider
  implements vscode.InlineCompletionItemProvider, vscode.Disposable
{
  private _signalTracker: SignalTracker;
  private _config: CompletionProviderConfig;
  private _disposables: vscode.Disposable[] = [];
  private _debounceTimer: NodeJS.Timeout | null = null;

  constructor(
    signalTracker: SignalTracker,
    config: CompletionProviderConfig
  ) {
    this._signalTracker = signalTracker;
    this._config = config;

    // Register the inline completion provider
    this._disposables.push(
      vscode.languages.registerInlineCompletionItemProvider(
        { pattern: "**/*" },
        this
      )
    );

    // Listen for signal events from the tracker
    this._disposables.push(
      signalTracker.onSignal((event) => {
        // Log for debugging (not visible to users in production)
        console.log(
          `[ForgeAI] ${event.type}: ${event.suggestion.language} @ ${event.suggestion.filePath}:${event.suggestion.lineNumber}`
        );
      })
    );
  }

  /**
   * VS Code called this when an inline completion is requested.
   */
  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionItem[] | undefined> {
    // Check cancellation
    if (token.isCancellationRequested) return;

    // Check if we should trigger
    if (!this._config.autoTrigger && context.triggerKind !== vscode.InlineCompletionTriggerKind.Invoke) {
      return;
    }

    // Get context around cursor for better suggestions
    const linePrefix = document.lineAt(position).text.slice(0, position.character);

    // For now, provide a simple contextual completion based on document content
    // In production, this would call the AI model endpoint
    const suggestion = this._generateSuggestion(document, position, linePrefix);

    if (!suggestion) return;

    // Create the inline completion item
    const item = new vscode.InlineCompletionItem(
      suggestion,
      new vscode.Range(position, position)
    );

    // Register this as a pending suggestion
    const pendingId = crypto.randomUUID();
    const textBefore = document.getText(
      new vscode.Range(
        new vscode.Position(Math.max(0, position.line - 5), 0),
        position
      )
    );
    const textAfter = document.getText(
      new vscode.Range(
        position,
        new vscode.Position(
          Math.min(document.lineCount - 1, position.line + 5),
          document.lineAt(Math.min(document.lineCount - 1, position.line + 5)).text.length
        )
      )
    );

    const pending: PendingSuggestion = {
      id: pendingId,
      text: suggestion,
      filePath: document.uri.fsPath,
      lineNumber: position.line + 1, // 1-based line number
      language: document.languageId,
      timestamp: Date.now(),
      contextBefore: textBefore,
      contextAfter: textAfter,
      fullContext: document.getText(),
      metadata: {
        model: this._config.model,
        triggerKind: context.triggerKind,
      },
      resolved: false,
    };

    this._signalTracker.registerSuggestion(pending);

    return [item];
  }

  /**
   * Generate a suggestion for the given context.
   *
   * Uses a context-aware heuristic based on the document content.
   * In production, this would call an AI model API.
   */
  private _generateSuggestion(
    document: vscode.TextDocument,
    position: vscode.Position,
    linePrefix: string
  ): string | undefined {
    const languageId = document.languageId;

    // Extract the current line and nearby context
    const currentLine = document.lineAt(position).text;

    // Detect what the user is typing and provide relevant suggestions
    // Basic patterns:

    // 1. Function/method completion
    const funcMatch = currentLine.match(/^\s*(def |function |fun |func |async def |public |private |protected )/);
    if (funcMatch) {
      return this._generateFunctionSkeleton(languageId, currentLine);
    }

    // 2. Class completion
    if (/^\s*(class |interface |trait |struct )/.test(currentLine)) {
      return this._generateClassSkeleton(languageId, currentLine);
    }

    // 3. Import completion
    if (/^\s*(import |from |using |use )/.test(currentLine)) {
      return null; // Let the user type imports
    }

    // 4. If/for/while block completion
    const blockMatch = currentLine.match(/^\s*(if |for |while |with |try:)/);
    if (blockMatch) {
      return this._generateBlockSkeleton(languageId, currentLine);
    }

    // 5. Return statement completion
    if (/^\s*return\s*$/.test(currentLine)) {
      return "    return None";
    }

    // 6. Variable assignment completion
    const assignMatch = currentLine.match(/^\s*(\w+)\s*=\s*$/);
    if (assignMatch) {
      return this._generateAssignment(languageId, assignMatch[1]);
    }

    // 7. Closing brace/bracket completion
    if (/^\s*[}\]\)]\s*$/.test(currentLine)) {
      return null;
    }

    return null;
  }

  private _generateFunctionSkeleton(languageId: string, line: string): string {
    const indent = line.match(/^\s*/)?.[0] || "";
    const trimmed = line.trim();

    if (languageId === "python") {
      if (trimmed.endsWith(":")) {
        return `${indent}    pass`;
      }
      return `${line}:\n${indent}    pass\n`;
    }

    if (languageId === "javascript" || languageId === "typescript") {
      const funcName = trimmed.match(/(?:function|fun|func)\s+(\w+)/)?.[1] || "fn";
      if (trimmed.endsWith("{")) {
        return `${indent}    // TODO: implement ${funcName}\n${indent}}`;
      }
      return `${line} {\n${indent}    // TODO: implement ${funcName}\n${indent}}`;
    }

    if (languageId === "go") {
      if (trimmed.endsWith("{")) {
        return `${indent}    // TODO: implement\n${indent}}`;
      }
      return `${line} {\n${indent}    // TODO: implement\n${indent}}`;
    }

    if (languageId === "rust") {
      return `${line} {\n${indent}    // TODO: implement\n${indent}}`;
    }

    if (languageId === "java") {
      if (trimmed.endsWith("{")) {
        return `${indent}    // TODO: implement\n${indent}}`;
      }
      return `${line} {\n${indent}    // TODO: implement\n${indent}}`;
    }

    return `${line}\n${indent}    pass`;
  }

  private _generateClassSkeleton(languageId: string, line: string): string {
    const indent = line.match(/^\s*/)?.[0] || "";

    if (languageId === "python") {
      if (line.trim().endsWith(":")) {
        return `${indent}    pass`;
      }
      return `${line}:\n${indent}    pass\n`;
    }

    // Default brace-based languages (JS, TS, Go, Rust, Java)
    if (line.trim().endsWith("{")) {
      return `${indent}    // TODO: implement class\n${indent}}`;
    }
    return `${line} {\n${indent}    // TODO: implement\n${indent}}`;
  }

  private _generateBlockSkeleton(languageId: string, line: string): string {
    const indent = line.match(/^\s*/)?.[0] || "";

    if (languageId === "python") {
      if (line.trim().endsWith(":")) {
        return `${indent}    pass`;
      }
      return `${line}:\n${indent}    pass`;
    }

    // Brace-based languages
    if (line.trim().endsWith("{")) {
      return `${indent}    // TODO: implement block\n${indent}}`;
    }
    return `${line} {\n${indent}    // TODO: implement\n${indent}}`;
  }

  private _generateAssignment(languageId: string, varName: string): string {
    if (varName.toLowerCase().includes("count") || varName.toLowerCase().includes("num")) {
      return `${varName} = 0`;
    }
    if (varName.toLowerCase().includes("name") || varName.toLowerCase().includes("str")) {
      return `${varName} = ""`;
    }
    if (varName.toLowerCase().includes("list") || varName.toLowerCase().includes("arr") || varName.endsWith("s")) {
      return `${varName} = []`;
    }
    if (varName.toLowerCase().includes("dict") || varName.toLowerCase().includes("map")) {
      return `${varName} = {}`;
    }
    if (varName.toLowerCase().includes("flag") || varName.toLowerCase().includes("is_") || varName.toLowerCase().includes("has_")) {
      return `${varName} = False`;
    }
    if (varName.toLowerCase().includes("result") || varName.toLowerCase().includes("val")) {
      return `${varName} = calculate_${varName}()`;
    }
    return `${varName} = None`;
  }

  dispose(): void {
    if (this._debounceTimer) {
      clearTimeout(this._debounceTimer);
    }
    this._disposables.forEach((d) => d.dispose());
  }
}
