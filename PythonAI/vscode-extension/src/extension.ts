import * as vscode from "vscode";
import { CaptureEngine } from "./captureEngine";
import { ForgeAICompletionProvider } from "./completionProvider";
import { loadConfig, onConfigChanged, ForgeAIConfig } from "./config";

let captureEngine: CaptureEngine | null = null;
let completionProvider: ForgeAICompletionProvider | null = null;

export function activate(context: vscode.ExtensionContext): void {
  console.log("[ForgeAI] Extension activating...");

  const config = loadConfig();
  if (!config.enabled) {
    console.log("[ForgeAI] Disabled by configuration.");
    return;
  }

  // Initialize CaptureEngine
  captureEngine = new CaptureEngine(config.dbPath);

  // Initialize asynchronously (must happen after activation)
  captureEngine.initialize().then(() => {
    console.log("[ForgeAI] CaptureEngine initialized.");

    // Register inline completion provider with signal tracking and config
    completionProvider = new ForgeAICompletionProvider(captureEngine!, config);
    context.subscriptions.push(completionProvider);

    // Show stats command
    context.subscriptions.push(
      vscode.commands.registerCommand("forgeai.showStats", async () => {
        await showStats();
      })
    );

    // Export training data command
    context.subscriptions.push(
      vscode.commands.registerCommand("forgeai.exportTrainingData", async () => {
        await exportTrainingData();
      })
    );

    // Watch for config changes — also update the completion provider
    context.subscriptions.push(
      onConfigChanged((newConfig: ForgeAIConfig) => {
        if (!newConfig.enabled && captureEngine) {
          captureEngine.close();
          captureEngine = null;
        }
        if (completionProvider) {
          completionProvider.updateConfig(newConfig);
        }
        console.log("[ForgeAI] Configuration updated.");
      })
    );

    vscode.window.showInformationMessage("[ForgeAI] Signal capture active.");
  }).catch((err) => {
    console.error("[ForgeAI] Failed to initialize CaptureEngine:", err);
    vscode.window.showErrorMessage(
      `[ForgeAI] Failed to initialize signal capture: ${err.message}`
    );
  });
}

async function showStats(): Promise<void> {
  if (!captureEngine) {
    vscode.window.showWarningMessage("[ForgeAI] CaptureEngine not initialized.");
    return;
  }

  try {
    const stats = await captureEngine.getStatistics();
    const rates = await captureEngine.getAcceptanceRate(7);

    const panel = vscode.window.createWebviewPanel(
      "forgeaiStats",
      "ForgeAI Capture Statistics",
      vscode.ViewColumn.Two,
      { enableScripts: false }
    );

    const rateRows = rates.map((r) =>
      `<tr><td>${r.date}</td><td>${(r.rate * 100).toFixed(1)}%</td><td>${r.accepts}</td><td>${r.rejects}</td><td>${r.edits}</td></tr>`
    ).join("\n");

    const typeRows = Object.entries(stats.signalsByType)
      .map(([type, count]) => `<tr><td>${type}</td><td>${count}</td></tr>`)
      .join("\n");

    panel.webview.html = `<!DOCTYPE html>
<html>
<head><style>
  body { font-family: -apple-system, sans-serif; padding: 16px; }
  h2 { color: var(--vscode-editor-foreground); }
  table { border-collapse: collapse; width: 100%; margin: 12px 0; }
  th, td { text-align: left; padding: 6px 12px; border: 1px solid var(--vscode-panel-border); }
  th { background: var(--vscode-editor-lineHighlightBackground); }
  .rate { color: var(--vscode-charts-green); font-weight: bold; }
</style></head>
<body>
  <h2>ForgeAI Capture Statistics</h2>
  <p>Total Signals: <strong>${stats.totalSignals}</strong> | Sessions: <strong>${stats.totalSessions}</strong></p>
  <p>Acceptance Rate: <span class="rate">${(stats.acceptanceRate * 100).toFixed(1)}%</span></p>
  <p>Avg Edit Distance: ${stats.avgEditDistance.toFixed(3)}</p>

  <h3>Signals by Type</h3>
  <table><tr><th>Type</th><th>Count</th></tr>${typeRows}</table>

  <h3>Last 7 Days</h3>
  <table><tr><th>Date</th><th>Rate</th><th>Accepts</th><th>Rejects</th><th>Edits</th></tr>${rateRows}</table>
</body></html>`;
  } catch (err: any) {
    vscode.window.showErrorMessage(`[ForgeAI] Failed to get stats: ${err.message}`);
  }
}

async function exportTrainingData(): Promise<void> {
  if (!captureEngine) {
    vscode.window.showWarningMessage("[ForgeAI] CaptureEngine not initialized.");
    return;
  }

  const uri = await vscode.window.showSaveDialog({
    filters: { "JSON Lines": ["jsonl"], "JSON": ["json"] },
    defaultUri: vscode.Uri.file("forgeai_training_data.jsonl"),
  });

  if (!uri) return;

  try {
    const stats = await captureEngine.getStatistics();
    const exportData = {
      exported_at: new Date().toISOString(),
      stats: stats,
      signals: [] as any[],
    };

    // Read signals from DB (simplified — full export via Python CLI)
    const json = JSON.stringify(exportData, null, 2);
    const fs = require("fs") as typeof import("fs");
    fs.writeFileSync(uri.fsPath, json, "utf-8");

    vscode.window.showInformationMessage(
      `[ForgeAI] Statistics exported to ${uri.fsPath}`
    );
    vscode.window.showInformationMessage(
      `[ForgeAI] For full training data export, run:\n  python -m src.cli grpo export-pairs --output training_pairs.jsonl`
    );
  } catch (err: any) {
    vscode.window.showErrorMessage(`[ForgeAI] Export failed: ${err.message}`);
  }
}

export function deactivate(): void {
  console.log("[ForgeAI] Extension deactivating...");
  if (captureEngine) {
    captureEngine.close();
    captureEngine = null;
  }
}
