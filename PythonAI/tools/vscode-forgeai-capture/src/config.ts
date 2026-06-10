import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";

/**
 * ForgeAI Capture Extension Configuration.
 *
 * Reads from VS Code settings with sensible defaults matching the Python
 * CaptureEngine configuration (~/.forgeai/signals.db by default).
 */
export interface ForgeAIConfig {
  /** Absolute path to the SQLite signals database */
  dbPath: string;

  /** Project name for session identification */
  projectName: string;

  /** Whether signal capture is enabled */
  enabled: boolean;

  /** Whether to capture reject signals */
  captureRejects: boolean;

  /** Whether to capture edit signals */
  captureEdits: boolean;

  /** Anonymized developer ID (auto-generated if empty) */
  developerId: string;
}

/**
 * Resolve a path that may contain ~ or environment variables.
 */
function resolvePath(p: string): string {
  // Expand ~ to home directory
  if (p.startsWith("~")) {
    p = path.join(os.homedir(), p.slice(1));
  }
  // Expand environment variables (cross-platform)
  p = p.replace(/\$([a-zA-Z_][a-zA-Z0-9_]*)/g, (_, varName) =>
    process.env[varName] || ""
  );
  p = p.replace(/%([a-zA-Z_][a-zA-Z0-9_]*)%/g, (_, varName) =>
    process.env[varName] || ""
  );
  return path.resolve(p);
}

/**
 * Get the active workspace folder name, or "default" if none.
 */
function getWorkspaceName(): string {
  const folders = vscode.workspace.workspaceFolders;
  if (folders && folders.length > 0) {
    return folders[0].name;
  }
  return "default";
}

/**
 * Load the ForgeAI Capture configuration from VS Code settings.
 */
export function loadConfig(): ForgeAIConfig {
  const settings = vscode.workspace.getConfiguration("forgeai");

  const config: ForgeAIConfig = {
    dbPath: resolvePath(settings.get<string>("dbPath", "~/.forgeai/signals.db")),
    projectName: settings.get<string>("projectName", "") || getWorkspaceName(),
    enabled: settings.get<boolean>("enabled", true),
    captureRejects: settings.get<boolean>("captureRejects", true),
    captureEdits: settings.get<boolean>("captureEdits", true),
    developerId: settings.get<string>("developerId", ""),
  };

  return config;
}

/**
 * Listen for configuration changes and re-apply.
 */
export function watchConfig(onChange: (config: ForgeAIConfig) => void): vscode.Disposable {
  return vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration("forgeai")) {
      onChange(loadConfig());
    }
  });
}
