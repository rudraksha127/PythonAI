/**
 * autocompleteClient.ts — HTTP client for the ForgeAI /inference/autocomplete endpoint.
 *
 * Calls the local FastAPI server with Fill-In-the-Middle context (prefix/suffix)
 * around the cursor position and returns the ghost-text completion.
 */

export interface AutocompleteRequest {
  prefix: string;
  suffix: string;
  language: string;
  filepath?: string;
  max_tokens: number;
  temperature: number;
}

export interface AutocompleteResponse {
  status: "success";
  completion: string;
  elapsed_ms: number;
}

export interface AutocompleteError {
  status: "error";
  error: string;
}

export type AutocompleteResult = AutocompleteResponse | AutocompleteError;

/**
 * Calls the ForgeAI /inference/autocomplete API endpoint.
 *
 * Uses Node.js built-in fetch (available in VS Code's extension host on Node 20+).
 * Falls back to the http/https module if fetch is unavailable.
 */
export async function fetchAutocomplete(
  serverUrl: string,
  request: AutocompleteRequest,
  signal?: AbortSignal
): Promise<AutocompleteResult> {
  const url = `${serverUrl.replace(/\/+$/, "")}/inference/autocomplete`;

  try {
    // VS Code extension host has fetch available (Node 20+)
    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        prefix: request.prefix,
        suffix: request.suffix,
        language: request.language,
        filepath: request.filepath,
        max_tokens: request.max_tokens,
        temperature: request.temperature,
      }),
      signal,
    });

    if (!response.ok) {
      const errorText = await response.text().catch(() => "Unknown error");
      return {
        status: "error",
        error: `HTTP ${response.status}: ${errorText}`,
      };
    }

    const data = (await response.json()) as AutocompleteResponse;
    return data;
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === "AbortError") {
      return { status: "error", error: "Request was cancelled" };
    }
    const message = err instanceof Error ? err.message : String(err);
    return { status: "error", error: message };
  }
}

/**
 * Detects the ForgeAI-supported language identifier from a VS Code language ID.
 */
export function mapLanguage(languageId: string): string {
  const langMap: Record<string, string> = {
    typescript: "typescript",
    javascript: "javascript",
    javascriptreact: "jsx",
    typescriptreact: "tsx",
    python: "python",
    go: "go",
    rust: "rust",
    java: "java",
    csharp: "csharp",
    "c++": "cpp",
    c: "c",
    ruby: "ruby",
    php: "php",
    swift: "swift",
    kotlin: "kotlin",
    scala: "scala",
    shellscript: "bash",
    bash: "bash",
    zsh: "bash",
    powershell: "powershell",
    sql: "sql",
    html: "html",
    css: "css",
    scss: "scss",
    less: "less",
    json: "json",
    yaml: "yaml",
    markdown: "markdown",
    dockerfile: "dockerfile",
    graphql: "graphql",
    vue: "vue",
    svelte: "svelte",
    astro: "astro",
  };

  return langMap[languageId] || languageId;
}
