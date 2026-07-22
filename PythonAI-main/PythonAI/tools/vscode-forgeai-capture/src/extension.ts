import * as vscode from "vscode";
import { loadConfig, watchConfig, ForgeAIConfig } from "./config";
import { CaptureEngine } from "./captureEngine";
import { SignalTracker, SignalEvent } from "./signalTracker";
import { ForgeAICompletionProvider } from "./completionProvider";

/**
 * ForgeAI Capture — VS Code Extension.
 *
 * Captures AI coding assistant accept/reject/edit signals and writes them
 * to the ForgeAI CaptureEngine SQLite database. Completes the signal
 * collection loop by providing inline completion items and tracking
 * developer interactions with them.
 *
 * Signal Flow:
 *   Editor Context → CompletionProvider → Suggestion Shown
 *        ↓                                     ↓
 *   SignalTracker ←───── Accept/Reject/Edit
 *        ↓
 *   CaptureEngine (SQLite DB)
 *        ↓
 *   Python GRPO Training Pipeline
 */
export function activate(context: vscode.ExtensionContext): void {
  console.log("[ForgeAI] Activating ForgeAI Capture extension...");

  // Load configuration
  let config = loadConfig();

  // Core components
  let captureEngine: CaptureEngine | undefined;
  let signalTracker: SignalTracker;
  let completionProvider: ForgeAICompletionProvider;
  let statusBarItem: vscode.StatusBarItem;

  // Session tracking
  let sessionId: string;
  let isEnabled = config.enabled;

  // ── Status Bar ─────────────────────────────────────────────

  statusBarItem = vscode.window.createStatusBarItem(
    vscode.StatusBarAlignment.Right,
    100
  );
  statusBarItem.command = "forgeai.showStatus";
  statusBarItem.tooltip = "ForgeAI Capture — click for details";
  context.subscriptions.push(statusBarItem);

  // ── Initialize components ─────────────────────────────────

  function initializeEngine(cfg: ForgeAIConfig): void {
    try {
      // Close previous engine if exists
      if (captureEngine) {
        captureEngine.close();
      }

      captureEngine = new CaptureEngine(cfg);
      sessionId = captureEngine.createSession();
      updateStatusBar(true);
      console.log(`[ForgeAI] CaptureEngine initialized: ${cfg.dbPath}`);
    } catch (err) {
      captureEngine = undefined;
      updateStatusBar(false);
      console.error(`[ForgeAI] Failed to initialize CaptureEngine: ${err}`);
    }
  }

  function initializeTracker(): void {
    signalTracker = new SignalTracker();

    // Forward signal events to the CaptureEngine
    signalTracker.onSignal((event: SignalEvent) => {
      if (!captureEngine || !isEnabled) return;

      try {
        const suggestion = event.suggestion;

        if (event.type === "accept") {
          captureEngine.captureAccept(
            suggestion.text,
            suggestion.filePath,
            suggestion.lineNumber,
            suggestion.language,
            sessionId,
            suggestion.contextBefore,
            suggestion.contextAfter,
            suggestion.fullContext,
            suggestion.metadata,
            config.developerId || undefined
          );
        } else if (event.type === "reject") {
          if (!config.captureRejects) return;
          captureEngine.captureReject(
            suggestion.text,
            suggestion.filePath,
            suggestion.lineNumber,
            suggestion.language,
            sessionId,
            suggestion.contextBefore,
            suggestion.contextAfter,
            suggestion.fullContext,
            suggestion.metadata,
            config.developerId || undefined
          );
        } else if (event.type === "edit") {
          if (!config.captureEdits) return;
          captureEngine.captureEdit(
            suggestion.text,
            event.finalCode || "",
            suggestion.filePath,
            suggestion.lineNumber,
            suggestion.language,
            sessionId,
            suggestion.contextBefore,
            suggestion.contextAfter,
            suggestion.fullContext,
            suggestion.metadata,
            config.developerId || undefined
          );
        }
      } catch (err) {
        console.error(`[ForgeAI] Error capturing signal: ${err}`);
      }
    });

    context.subscriptions.push(signalTracker);
  }

  function initializeCompletionProvider(): void {
    completionProvider = new ForgeAICompletionProvider(signalTracker, {
      autoTrigger: true,
      debounceMs: 300,
      model: "forgeai-local",
      aiAvailable: true,
    });

    context.subscriptions.push(completionProvider);
  }

  // ── Status Bar Update ─────────────────────────────────────

  function updateStatusBar(dbReady: boolean): void {
    if (!isEnabled) {
      statusBarItem.text = "$(circle-slash) ForgeAI";
      statusBarItem.backgroundColor = undefined;
      statusBarItem.show();
      return;
    }

    if (dbReady) {
      statusBarItem.text = "$(database) ForgeAI";
      statusBarItem.backgroundColor = undefined;
    } else {
      statusBarItem.text = "$(warning) ForgeAI";
      statusBarItem.backgroundColor = new vscode.ThemeColor(
        "statusBarItem.warningBackground"
      );
    }
    statusBarItem.show();
  }

  // ── Commands ──────────────────────────────────────────────

  // Show capture status
  const showStatusCmd = vscode.commands.registerCommand(
    "forgeai.showStatus",
    () => {
      if (!captureEngine) {
        vscode.window.showWarningMessage(
          "ForgeAI Capture: Database not initialized. Check configuration."
        );
        return;
      }

      const stats = captureEngine.getStatistics();

      // Get recent stats
      const total = (stats.totalSignals as number) || 0;
      const accepts = (stats.accepts as number) || 0;
      const rejects = (stats.rejects as number) || 0;
      const edits = (stats.edits as number) || 0;

      const rate = total > 0 ? ((accepts / total) * 100).toFixed(1) : "N/A";

      const message = [
        `ForgeAI Capture`,
        `─────────────────`,
        `Status: ${isEnabled ? "Active" : "Disabled"}`,
        `Database: ${config.dbPath}`,
        `Signals captured: ${total}`,
        `  Accepts: ${accepts}`,
        `  Rejects: ${rejects}`,
        `  Edits: ${edits}`,
        `Acceptance rate: ${rate}%`,
        `Session: ${sessionId ? sessionId.slice(0, 8) + "..." : "N/A"}`,
      ].join("\n");

      vscode.window.showInformationMessage(message, {
        modal: false,
        detail: message,
      });
    }
  );

  // Export signals
  const exportCmd = vscode.commands.registerCommand(
    "forgeai.exportSignals",
    async () => {
      if (!captureEngine) {
        vscode.window.showErrorMessage(
          "ForgeAI Capture: Database not initialized."
        );
        return;
      }

      const uri = await vscode.window.showSaveDialog({
        filters: { "JSON Lines": ["jsonl"], "JSON": ["json"] },
        defaultUri: vscode.Uri.file(
          `forgeai-export-${new Date().toISOString().slice(0, 10)}.jsonl`
        ),
      });

      if (!uri) return;

      try {
        // Use the Python CLI if available, otherwise copy the DB
        vscode.window.showInformationMessage(
          `Export to ${uri.fsPath} requested. Run: python -m src.cli capture export --output "${uri.fsPath}"`
        );
      } catch (err) {
        vscode.window.showErrorMessage(`Export failed: ${err}`);
      }
    }
  );

  // Toggle capture
  const toggleCmd = vscode.commands.registerCommand(
    "forgeai.toggleCapture",
    () => {
      isEnabled = !isEnabled;
      updateStatusBar(captureEngine !== undefined);
      vscode.window.showInformationMessage(
        `ForgeAI Capture: ${isEnabled ? "Enabled" : "Disabled"}`
      );
    }
  );

  // ── Configuration watcher ─────────────────────────────────

  const configWatcher = watchConfig((newConfig: ForgeAIConfig) => {
    const oldDbPath = config.dbPath;
    config = newConfig;
    isEnabled = config.enabled;

    if (config.dbPath !== oldDbPath) {
      initializeEngine(config);
    }

    updateStatusBar(captureEngine !== undefined);
  });

  // ── Startup ───────────────────────────────────────────────

  try {
    initializeEngine(config);
    initializeTracker();
    initializeCompletionProvider();

    // Register disposables
    context.subscriptions.push(
      showStatusCmd,
      exportCmd,
      toggleCmd,
      configWatcher,
      statusBarItem
    );

    console.log(
      `[ForgeAI] Extension activated successfully. DB: ${config.dbPath}`
    );
  } catch (err) {
    console.error(`[ForgeAI] Failed to activate extension: ${err}`);
    vscode.window.showErrorMessage(
      `ForgeAI Capture: Activation failed — ${err}`
    );
  }
}

/**
 * Cleanup when the extension is deactivated.
 */
export function deactivate(): void {
  console.log("[ForgeAI] Deactivating ForgeAI Capture extension...");
}
