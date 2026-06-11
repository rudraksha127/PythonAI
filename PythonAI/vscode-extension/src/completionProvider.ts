import * as vscode from "vscode";
import { CaptureEngine } from "./captureEngine";
import { SignalTracker } from "./signalTracker";
import {
  fetchAutocomplete,
  mapLanguage,
  type AutocompleteResult,
} from "./autocompleteClient";
import type { ForgeAIConfig } from "./config";

/**
 * ForgeAICompletionProvider — provides real AI-powered inline ghost text
 * completions via the /inference/autocomplete FIM API, and tracks
 * accept/reject/edit signals through the SignalTracker.
 */
export class ForgeAICompletionProvider
  implements vscode.InlineCompletionItemProvider, vscode.Disposable
{
  private engine: CaptureEngine;
  private signalTracker: SignalTracker;
  private disposables: vscode.Disposable[] = [];

  /** Current config, reloaded when settings change. */
  private config: ForgeAIConfig;

  /** AbortController for in-flight autocomplete requests. */
  private pendingRequest: AbortController | null = null;

  constructor(engine: CaptureEngine, config: ForgeAIConfig) {
    this.engine = engine;
    this.config = config;
    this.signalTracker = new SignalTracker(engine);

    // Register the inline completion provider for all files
    this.disposables.push(
      vscode.languages.registerInlineCompletionItemProvider({ pattern: "**" }, this)
    );

    // Start signal tracking
    this.signalTracker.start();
  }

  /** Reload config (called when settings change). */
  updateConfig(config: ForgeAIConfig): void {
    this.config = config;
  }

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionItem[] | vscode.InlineCompletionList> {
    // Skip if autocomplete is disabled by config
    if (!this.config.autoCompleteEnabled) {
      return [];
    }

    // Quick heuristics to skip trivial/noisy positions:
    // - Empty lines (just whitespace)
    // - Comment-only lines
    // - Import statements
    const lineText = document.lineAt(position.line).text;
    const linePrefix = lineText.slice(0, position.character).trim();
    if (
      linePrefix.length === 0 ||
      linePrefix.startsWith("#") ||
      linePrefix.startsWith("//") ||
      linePrefix.startsWith("/*") ||
      linePrefix.startsWith("*") ||
      linePrefix.startsWith("--") ||
      /^(import|from|using|#include|require)\b/.test(linePrefix)
    ) {
      return [];
    }

    // Cancel any in-flight request
    if (this.pendingRequest) {
      this.pendingRequest.abort();
      this.pendingRequest = null;
    }

    // Extract prefix and suffix around the cursor position
    const prefix = document.getText(
      new vscode.Range(new vscode.Position(0, 0), position)
    );
    const suffix = document.getText(
      new vscode.Range(position, document.lineAt(document.lineCount - 1).range.end)
    );

    const language = mapLanguage(document.languageId);
    const filepath = document.uri.fsPath;

    // Build the abort controller (we use our own + the VS Code token)
    const abortController = new AbortController();
    this.pendingRequest = abortController;

    // If VS Code cancels, propagate
    token.onCancellationRequested(() => {
      abortController.abort();
    });

    // Debounce: wait a brief period before firing (configurable via settings)
    if (this.config.autoCompleteDebounceMs > 0) {
      await this.delay(this.config.autoCompleteDebounceMs);
    }

    // If cancelled during debounce, skip
    if (abortController.signal.aborted) {
      return [];
    }

    // Call the ForgeAI autocomplete API
    const result: AutocompleteResult = await fetchAutocomplete(
      this.config.serverUrl,
      {
        prefix,
        suffix,
        language,
        filepath,
        max_tokens: this.config.autoCompleteMaxTokens,
        temperature: this.config.autoCompleteTemperature,
      },
      abortController.signal
    );

    // Clear the pending flag (this request completed)
    if (this.pendingRequest === abortController) {
      this.pendingRequest = null;
    }

    // Handle errors gracefully — just show no ghost text
    if (result.status === "error") {
      return [];
    }

    const completion = result.completion;

    // Only show completion if it has meaningful content
    if (!completion || completion.trim().length < 2) {
      return [];
    }

    const contextStart = Math.max(0, position.line - 5);
    const contextEnd = Math.min(document.lineCount, position.line + 3);
    const contextBeforeBlock = document.getText(
      new vscode.Range(contextStart, 0, position.line, 0)
    );
    const contextAfterBlock = document.getText(
      new vscode.Range(position.line, 0, contextEnd, 0)
    );
    const fullContext = document.getText();

    this.signalTracker.setCurrentSuggestion(
      completion,
      filepath,
      position.line,
      language,
      contextBeforeBlock,
      contextAfterBlock,
      fullContext
    );

    // Return as an inline completion item
    return [
      new vscode.InlineCompletionItem(
        completion,
        new vscode.Range(position, position)
      ),
    ];
  }

  private delay(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  dispose(): void {
    if (this.pendingRequest) {
      this.pendingRequest.abort();
      this.pendingRequest = null;
    }
    for (const d of this.disposables) {
      d.dispose();
    }
    this.signalTracker.dispose();
  }
}
