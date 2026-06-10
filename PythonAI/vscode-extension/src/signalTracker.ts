import * as vscode from "vscode";
import { CaptureEngine } from "./captureEngine";

interface SuggestionState {
  suggestion: string;
  filePath: string;
  lineNumber: number;
  language: string;
  contextBefore: string;
  contextAfter: string;
  contextFull: string;
  timestamp: number;
  isStale: boolean;
}

/**
 * SignalTracker — monitors editor events to detect accept/reject/edit signals.
 *
 * Detection strategy:
 * - Accept: Inline completion accepted → check if text content matches suggestion
 * - Reject: Inline completion dismissed (Escape) with no match
 * - Edit: Inline completion accepted → text diverges from original suggestion
 */
export class SignalTracker implements vscode.Disposable {
  private engine: CaptureEngine;
  private currentSuggestion: SuggestionState | null = null;
  private lastTextBeforeInsert: string = "";
  private disposables: vscode.Disposable[] = [];

  constructor(engine: CaptureEngine) {
    this.engine = engine;
  }

  start(): void {
    // Track inline completion accept/reject events
    this.disposables.push(
      vscode.commands.registerCommand("forgeai.completionAccepted", (args: any) => {
        this.onCompletionAccepted(args);
      })
    );

    // Track text document changes for edit detection
    this.disposables.push(
      vscode.workspace.onDidChangeTextDocument((e) => {
        this.onTextChanged(e);
      })
    );
  }

  /**
   * Called when an inline completion is shown to the user.
   */
  setCurrentSuggestion(
    suggestion: string,
    filePath: string,
    lineNumber: number,
    language: string,
    contextBefore: string,
    contextAfter: string,
    contextFull: string
  ): void {
    this.currentSuggestion = {
      suggestion,
      filePath,
      lineNumber,
      language,
      contextBefore,
      contextAfter,
      contextFull,
      timestamp: Date.now(),
      isStale: false,
    };
    this.lastTextBeforeInsert = this.getCurrentLineText();
  }

  /**
   * Called when an inline completion is accepted.
   */
  private onCompletionAccepted(args: any): void {
    if (!this.currentSuggestion || this.currentSuggestion.isStale) return;

    const insertedText = args?.text || "";
    const suggestion = this.currentSuggestion.suggestion;

    // Normalize for comparison
    const insertedTrimmed = insertedText.trim();
    const suggestionTrimmed = suggestion.trim();

    // Accept: text matches suggestion exactly
    if (insertedTrimmed === suggestionTrimmed) {
      this.engine.captureAccept(
        suggestion,
        this.currentSuggestion.filePath,
        this.currentSuggestion.lineNumber,
        this.currentSuggestion.language,
        this.currentSuggestion.contextBefore,
        this.currentSuggestion.contextAfter,
        this.currentSuggestion.contextFull
      );
    }
    // Edit: text differs from suggestion
    else if (insertedTrimmed.length > 0) {
      this.engine.captureEdit(
        suggestion,
        insertedText,
        this.currentSuggestion.filePath,
        this.currentSuggestion.lineNumber,
        this.currentSuggestion.language,
        this.currentSuggestion.contextBefore,
        this.currentSuggestion.contextAfter,
        this.currentSuggestion.contextFull
      );
    }

    this.currentSuggestion = null;
  }

  /**
   * Called when text changes in the editor.
   * Detects implicit completions and rejections.
   */
  private onTextChanged(event: vscode.TextDocumentChangeEvent): void {
    if (!this.currentSuggestion || this.currentSuggestion.isStale) return;

    // Check if suggestion became stale (> 30 seconds)
    if (Date.now() - this.currentSuggestion.timestamp > 30000) {
      this.currentSuggestion.isStale = true;
      // Capture implicit reject (timed out)
      this.engine.captureReject(
        this.currentSuggestion.suggestion,
        this.currentSuggestion.filePath,
        this.currentSuggestion.lineNumber,
        this.currentSuggestion.language,
        this.currentSuggestion.contextBefore,
        this.currentSuggestion.contextAfter,
        this.currentSuggestion.contextFull
      );
      return;
    }

    // Check if user typed something different from the suggestion
    const currentText = this.getCurrentLineText();
    const suggestion = this.currentSuggestion.suggestion.trim();

    if (currentText.length > 0 && currentText !== this.lastTextBeforeInsert) {
      // User is typing something — if it doesn't match the suggestion start, it's a reject
      const typed = currentText.slice(this.lastTextBeforeInsert.length);
      if (typed.length > 3 && !suggestion.startsWith(typed)) {
        this.engine.captureReject(
          suggestion,
          this.currentSuggestion.filePath,
          this.currentSuggestion.lineNumber,
          this.currentSuggestion.language,
          this.currentSuggestion.contextBefore,
          this.currentSuggestion.contextAfter,
          this.currentSuggestion.contextFull
        );
        this.currentSuggestion.isStale = true;
      }
    }

    this.lastTextBeforeInsert = currentText;
  }

  private getCurrentLineText(): string {
    const editor = vscode.window.activeTextEditor;
    if (!editor) return "";
    const position = editor.selection.active;
    const line = editor.document.lineAt(position.line);
    return line.text;
  }

  dispose(): void {
    for (const d of this.disposables) {
      d.dispose();
    }
    this.disposables = [];
  }
}
