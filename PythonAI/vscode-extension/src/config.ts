import * as vscode from "vscode";
import * as path from "path";
import * as os from "os";

const EXTENSION_SECTION = "forgeai";

export interface ForgeAIConfig {
  dbPath: string;
  enabled: boolean;
  captureRejects: boolean;
  captureEdits: boolean;
  developerId: string;
}

function expandPath(p: string): string {
  // Expand ~ to home directory
  if (p.startsWith("~/") || p === "~") {
    p = path.join(os.homedir(), p.slice(1));
  }
  // Expand environment variables like %APPDATA% or $HOME
  p = p.replace(/%([^%]+)%/g, (_match, varName) => process.env[varName] || "");
  p = p.replace(/\$([A-Z_]+)/g, (_match, varName) => process.env[varName] || "");
  return path.resolve(p);
}

export function loadConfig(): ForgeAIConfig {
  const forgeaiConfig = vscode.workspace.getConfiguration(EXTENSION_SECTION);
  return {
    dbPath: expandPath(forgeaiConfig.get<string>("dbPath", "~/.forgeai/signals.db")),
    enabled: forgeaiConfig.get<boolean>("enabled", true),
    captureRejects: forgeaiConfig.get<boolean>("captureRejects", true),
    captureEdits: forgeaiConfig.get<boolean>("captureEdits", true),
    developerId: forgeaiConfig.get<string>("developerId", ""),
  };
}

export function onConfigChanged(
  listener: (config: ForgeAIConfig) => void
): vscode.Disposable {
  return vscode.workspace.onDidChangeConfiguration((e) => {
    if (e.affectsConfiguration(EXTENSION_SECTION)) {
      listener(loadConfig());
    }
  });
}
