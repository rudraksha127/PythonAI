import * as vscode from "vscode";
import { CaptureEngine } from "./captureEngine";
import { SignalTracker } from "./signalTracker";

/**
 * ForgeAICompletionProvider — provides inline completions and tracks accept/reject/edit signals.
 *
 * The provider watches for inline completions, and the SignalTracker detects
 * whether the user accepted, rejected, or edited the suggestion.
 */
export class ForgeAICompletionProvider
  implements vscode.InlineCompletionItemProvider, vscode.Disposable
{
  private engine: CaptureEngine;
  private signalTracker: SignalTracker;
  private disposables: vscode.Disposable[] = [];

  constructor(engine: CaptureEngine) {
    this.engine = engine;
    this.signalTracker = new SignalTracker(engine);

    // Register the inline completion provider
    this.disposables.push(
      vscode.languages.registerInlineCompletionItemProvider({ pattern: "**" }, this)
    );

    // Start signal tracking
    this.signalTracker.start();
  }

  async provideInlineCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _context: vscode.InlineCompletionContext,
    _token: vscode.CancellationToken
  ): Promise<vscode.InlineCompletionItem[] | vscode.InlineCompletionList> {
    // Get context around cursor
    const lineText = document.lineAt(position.line).text;
    const contextBefore = lineText.slice(0, position.character);
    const filePath = document.uri.fsPath;
    const language = document.languageId;

    // Generate skeleton completion based on context
    const suggestions = this.generateSuggestions(contextBefore, language);

    if (suggestions.length === 0) {
      return [];
    }

    // Track the suggestion for accept/reject detection
    for (const suggestion of suggestions) {
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
        suggestion.insertText as string,
        filePath,
        position.line,
        language,
        contextBeforeBlock,
        contextAfterBlock,
        fullContext
      );
    }

    return suggestions;
  }

  /**
   * Generate simple skeleton code completions.
   * These provide enough structure for accept/reject signal capture.
   */
  private generateSuggestions(
    context: string,
    language: string
  ): vscode.InlineCompletionItem[] {
    const items: vscode.InlineCompletionItem[] = [];
    const trimmed = context.trimEnd();

    // Function definition completion
    if (/def\s+\w+\s*$/.test(trimmed)) {
      const funcName = trimmed.match(/def\s+(\w+)/)?.[1] || "func";
      items.push(
        new vscode.InlineCompletionItem(
          `    pass\n`,
          new vscode.Range(
            new vscode.Position(
              vscode.window.activeTextEditor?.selection.active.line || 0,
              0
            ),
            new vscode.Position(
              vscode.window.activeTextEditor?.selection.active.line || 0,
              0
            )
          )
        )
      );
    }

    // Class definition completion
    if (/class\s+\w+\s*$/.test(trimmed)) {
      items.push(
        new vscode.InlineCompletionItem(`    def __init__(self):\n        pass\n`)
      );
    }

    // Import completion
    if (/^import\s+\w*$/.test(trimmed) || /^from\s+\w+$/.test(trimmed)) {
      // Don't suggest imports — user knows what they want
      return [];
    }

    // If statement
    if (/^if\s+.+:/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(`    pass`));
    }

    // For loop
    if (/^for\s+.+:/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(`    pass`));
    }

    // Return statement
    if (/^\s+return\s*$/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(`None`));
    }

    // Method body in classes
    if (/^\s+def\s+\w+\(.*\)\s*$/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(`\n        pass`));
    }

    // JavaScript/TypeScript functions
    if (/function\s+\w+\s*\([^)]*\)\s*$/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(` {\n    \n}`));
    }

    // Arrow functions
    if (/const\s+\w+\s*=\s*\([^)]*\)\s*=>\s*$/.test(trimmed)) {
      items.push(new vscode.InlineCompletionItem(` {\n    \n}`));
    }

    return items;
  }

  dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
    this.signalTracker.dispose();
  }
}
