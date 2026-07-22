import * as vscode from "vscode";

/**
 * A pending suggestion that has been shown to the user but not yet resolved.
 */
export interface PendingSuggestion {
  /** Unique ID for this suggestion */
  id: string;

  /** The suggested text */
  text: string;

  /** The file path where the suggestion was made */
  filePath: string;

  /** The line number where the suggestion was made (1-based) */
  lineNumber: number;

  /** The language ID of the document */
  language: string;

  /** Timestamp (epoch ms) when the suggestion was shown */
  timestamp: number;

  /** Context before the cursor position */
  contextBefore: string;

  /** Context after the cursor position */
  contextAfter: string;

  /** Full document context */
  fullContext: string;

  /** Suggestion metadata (model info, timing, etc.) */
  metadata: Record<string, unknown>;

  /** Track when the suggestion was resolved */
  resolved: boolean;
}

/**
 * Result of resolving a pending suggestion.
 */
export interface SignalEvent {
  type: "accept" | "reject" | "edit";
  suggestion: PendingSuggestion;
  /** For edit signals: the final code the user ended up with */
  finalCode?: string;
  /** For edit signals: the normalized edit distance (0-1) */
  editDistance?: number;
}

/**
 * SignalTracker monitors VS Code editor events to detect when inline
 * completions are accepted, rejected, or edited by the developer.
 *
 * Detection strategy:
 * 1. **Accept**: Document text change matches pending suggestion exactly.
 * 2. **Edit**: Document text change partially matches (>30% similarity by Levenshtein).
 * 3. **Reject**: Suggestion times out (30s), user moves cursor away, or
 *    user types completely different text (>50 chars typed without matching).
 */
export class SignalTracker implements vscode.Disposable {
  private _pending = new Map<string, PendingSuggestion>();
  private _disposables: vscode.Disposable[] = [];
  private _onSignal = new vscode.EventEmitter<SignalEvent>();

  /** Fired when a signal event (accept/reject/edit) is detected. */
  readonly onSignal: vscode.Event<SignalEvent> = this._onSignal.event;

  /** Timeout in ms before a pending suggestion is considered rejected */
  private readonly _suggestionTimeoutMs = 30000;

  /** Periodic timer for cleaning up stale suggestions */
  private _cleanupTimer: NodeJS.Timeout | null = null;

  constructor() {
    // Watch document changes to detect accepts and edits
    this._disposables.push(
      vscode.workspace.onDidChangeTextDocument(this._onTextChanged, this)
    );

    // Watch active editor changes to detect suggestion dismissals
    this._disposables.push(
      vscode.window.onDidChangeActiveTextEditor(this._onEditorChanged, this)
    );

    // Periodic cleanup every 15 seconds
    this._cleanupTimer = setInterval(() => {
      this._checkStaleSuggestions();
    }, 15000);
  }

  /**
   * Register a new pending suggestion that has been shown to the user.
   */
  registerSuggestion(suggestion: PendingSuggestion): void {
    this._pending.set(suggestion.id, suggestion);
  }

  /**
   * Remove a suggestion from the pending map without firing an event.
   */
  removeSuggestion(id: string): void {
    this._pending.delete(id);
  }

  /**
   * Get a pending suggestion by ID.
   */
  getSuggestion(id: string): PendingSuggestion | undefined {
    return this._pending.get(id);
  }

  /**
   * Get all pending suggestions.
   */
  getPending(): PendingSuggestion[] {
    return Array.from(this._pending.values());
  }

  /**
   * Manually resolve a suggestion as accepted (with optional final code for edits).
   */
  resolveAccept(
    suggestion: PendingSuggestion,
    finalCode?: string
  ): void {
    if (suggestion.resolved) return;
    suggestion.resolved = true;
    this._pending.delete(suggestion.id);

    const final = finalCode !== undefined ? finalCode : suggestion.text;
    if (final !== suggestion.text) {
      this._emitEdit(suggestion, final);
    } else {
      this._onSignal.fire({ type: "accept", suggestion });
    }
  }

  /**
   * Manually resolve a suggestion as rejected.
   */
  resolveReject(suggestion: PendingSuggestion): void {
    if (suggestion.resolved) return;
    suggestion.resolved = true;
    this._pending.delete(suggestion.id);
    this._onSignal.fire({ type: "reject", suggestion });
  }

  dispose(): void {
    this._pending.clear();
    this._disposables.forEach((d) => d.dispose());
    this._onSignal.dispose();
    if (this._cleanupTimer) {
      clearInterval(this._cleanupTimer);
      this._cleanupTimer = null;
    }
  }

  // ─── Private Event Handlers ─────────────────────────────────

  /**
   * Handle document text changes to detect accepts and edits.
   */
  private _onTextChanged(event: vscode.TextDocumentChangeEvent): void {
    if (event.contentChanges.length === 0) return;
    if (this._pending.size === 0) return;

    const change = event.contentChanges[0];
    const insertedText = change.text;
    if (!insertedText.trim()) return;

    const doc = event.document;
    const filePath = doc.uri.fsPath;

    for (const [id, suggestion] of this._pending) {
      if (suggestion.resolved) continue;
      if (suggestion.filePath !== filePath) continue;

      const matchResult = this._matchText(insertedText, suggestion.text);

      if (matchResult === "accept") {
        suggestion.resolved = true;
        this._pending.delete(id);
        this._onSignal.fire({ type: "accept", suggestion });
        return;
      } else if (matchResult === "edit") {
        suggestion.resolved = true;
        this._pending.delete(id);
        this._emitEdit(suggestion, insertedText);
        return;
      }
      // "different" — no match. If user has typed a lot (>50 chars) without
      // matching, implicitly reject.
      if (insertedText.trim().length > 50 &&
          this._levenshteinRatio(insertedText.trim(), suggestion.text.trim()) < 0.3) {
        this.resolveReject(suggestion);
      }
    }

    // Clean stale suggestions after each text change
    this._checkStaleSuggestions();
  }

  /**
   * Handle editor changes to detect implicit rejections when switching files.
   */
  private _onEditorChanged(editor: vscode.TextEditor | undefined): void {
    if (!editor) return;

    const currentFile = editor.document.uri.fsPath;
    for (const [id, suggestion] of this._pending) {
      if (suggestion.resolved) continue;
      if (suggestion.filePath !== currentFile && Date.now() - suggestion.timestamp > 5000) {
        this.resolveReject(suggestion);
      }
    }

    this._checkStaleSuggestions();
  }

  /**
   * Clean up suggestions that have exceeded the timeout.
   */
  private _checkStaleSuggestions(): void {
    const now = Date.now();
    for (const [id, suggestion] of this._pending) {
      if (suggestion.resolved) continue;
      if (now - suggestion.timestamp > this._suggestionTimeoutMs) {
        this.resolveReject(suggestion);
      }
    }
  }

  /**
   * Compare inserted text against a suggestion to determine the signal type.
   *
   * Returns:
   *   "accept"    — exact match
   *   "edit"      — partial match >30% similarity
   *   "different" — no meaningful match
   */
  private _matchText(
    inserted: string,
    suggestion: string
  ): "accept" | "edit" | "different" {
    const insertedTrimmed = inserted.trim();
    const suggestionTrimmed = suggestion.trim();

    if (!insertedTrimmed) return "different";

    // 1. Exact match → accept
    if (insertedTrimmed === suggestionTrimmed) return "accept";

    // 2. Suggestion is a substring of inserted text (user added to it) → edit
    if (suggestionTrimmed.length > 0 && insertedTrimmed.includes(suggestionTrimmed)) {
      return "edit";
    }

    // 3. Inserted text is a substring of suggestion → still typing, don't classify yet
    if (suggestionTrimmed.startsWith(insertedTrimmed)) return "different";

    // 4. Compute similarity ratio using Levenshtein
    const similarity = this._levenshteinRatio(insertedTrimmed, suggestionTrimmed);
    if (similarity > 0.3) return "edit";

    // 5. Low similarity → user wrote something different
    return "different";
  }

  /**
   * Compute Levenshtein similarity ratio between two strings.
   * Returns 1.0 for identical, 0.0 for completely different.
   */
  private _levenshteinRatio(a: string, b: string): number {
    if (a === b) return 1.0;
    if (a.length === 0 || b.length === 0) return 0.0;

    const maxLen = Math.max(a.length, b.length);
    if (maxLen === 0) return 1.0;

    // Quick character-set check: if they share <30% of unique chars, skip DP
    const aChars = new Set(a.toLowerCase());
    const bChars = new Set(b.toLowerCase());
    const intersection = new Set([...aChars].filter((c) => bChars.has(c)));
    if (intersection.size < Math.min(aChars.size, bChars.size) * 0.3) {
      return 0.0;
    }

    // Full Levenshtein distance (DP matrix)
    const m = a.length;
    const n = b.length;
    const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));

    for (let i = 0; i <= m; i++) dp[i][0] = i;
    for (let j = 0; j <= n; j++) dp[0][j] = j;

    for (let i = 1; i <= m; i++) {
      for (let j = 1; j <= n; j++) {
        const cost = a[i - 1].toLowerCase() === b[j - 1].toLowerCase() ? 0 : 1;
        dp[i][j] = Math.min(
          dp[i - 1][j] + 1,
          dp[i][j - 1] + 1,
          dp[i - 1][j - 1] + cost
        );
      }
    }

    const distance = dp[m][n];
    return 1.0 - distance / maxLen;
  }

  /**
   * Fire an edit signal with computed edit distance.
   */
  private _emitEdit(suggestion: PendingSuggestion, finalCode: string): void {
    const origLines = suggestion.text.trim().split("\n");
    const finalLines = finalCode.trim().split("\n");
    const total = Math.max(origLines.length, finalLines.length);
    let diffCount = 0;

    for (let i = 0; i < total; i++) {
      const origLine = i < origLines.length ? origLines[i].trim() : "";
      const finalLine = i < finalLines.length ? finalLines[i].trim() : "";
      if (origLine !== finalLine) diffCount++;
    }

    const editDistance = total > 0 ? diffCount / total : 0;

    this._onSignal.fire({
      type: "edit",
      suggestion,
      finalCode,
      editDistance,
    });
  }
}
