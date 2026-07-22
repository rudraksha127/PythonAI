import * as fs from "fs";
import * as path from "path";
import * as crypto from "crypto";
import * as os from "os";
import initSqlJs, { Database as SqlJsDatabase, SqlJsStatic } from "sql.js";
import type { ForgeAIConfig } from "./config";

/**
 * Signal types matching the Python TrainingSignal.SignalType enum.
 */
export enum SignalType {
  ACCEPT = "accept",
  REJECT = "reject",
  EDIT = "edit",
  TEST_PASS = "test_pass",
  TEST_FAIL = "test_fail",
  PR_MERGE = "pr_merge",
  IMPLICIT_ACCEPT = "implicit_accept",
}

/**
 * Capture statistics returned by getStatistics().
 */
export interface CaptureStatistics {
  totalSignals: number;
  accepts: number;
  rejects: number;
  edits: number;
  dbPath: string;
  sessionCount: number;
}

/**
 * CaptureEngine — writes developer accept/reject/edit signals to the same
 * SQLite schema used by the Python CaptureEngine.
 *
 * Uses sql.js (pure JS/WASM SQLite) to avoid native compilation on Windows.
 * Persists to disk on every write for crash resilience.
 */
export class CaptureEngine {
  private db!: SqlJsDatabase;
  private SQL!: SqlJsStatic;
  private config: ForgeAIConfig;
  private initialized = false;
  private initPromise: Promise<void>;

  constructor(config: ForgeAIConfig) {
    this.config = config;
    this.initPromise = this._init();
  }

  /**
   * Wait for initialization to complete. Called before any DB operation.
   */
  private async _init(): Promise<void> {
    this.SQL = await initSqlJs();
    const dbDir = path.dirname(this.config.dbPath);
    if (!fs.existsSync(dbDir)) {
      fs.mkdirSync(dbDir, { recursive: true });
    }

    // Load existing database or create new one
    if (fs.existsSync(this.config.dbPath)) {
      const buffer = fs.readFileSync(this.config.dbPath);
      this.db = new this.SQL.Database(buffer);
    } else {
      this.db = new this.SQL.Database();
    }

    this.db.run("PRAGMA journal_mode = WAL");
    this._initSchema();
    this.initialized = true;
  }

  /**
   * Ensure the database is initialized before any operation.
   */
  private async _ensureInit(): Promise<void> {
    if (!this.initialized) {
      await this.initPromise;
    }
  }

  /**
   * Persist the database to disk.
   */
  private _save(): void {
    try {
      const data = this.db.export();
      const buffer = Buffer.from(data);
      fs.writeFileSync(this.config.dbPath, buffer);
    } catch (err) {
      console.error(`[ForgeAI] Failed to persist database: ${err}`);
    }
  }

  /**
   * Initialize the SQLite schema, matching the Python CaptureEngine exactly.
   */
  private _initSchema(): void {
    this.db.run(`
      CREATE TABLE IF NOT EXISTS signals (
        signal_id TEXT PRIMARY KEY,
        signal_type TEXT NOT NULL,
        timestamp REAL NOT NULL,
        session_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        line_number INTEGER NOT NULL,
        language TEXT NOT NULL,
        framework TEXT,
        project_type TEXT NOT NULL,
        suggestion TEXT NOT NULL,
        suggestion_metadata TEXT,
        context_before TEXT,
        context_after TEXT,
        full_context TEXT,
        final_code TEXT,
        edit_distance REAL DEFAULT 0.0,
        test_passed BOOLEAN,
        lint_passed BOOLEAN,
        compilation_passed BOOLEAN,
        git_sha TEXT,
        branch_name TEXT,
        pr_number INTEGER,
        developer_id TEXT
      );

      CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        start_time REAL NOT NULL,
        end_time REAL,
        project_name TEXT,
        language TEXT,
        framework TEXT,
        project_type TEXT,
        total_accepts INTEGER DEFAULT 0,
        total_rejects INTEGER DEFAULT 0,
        total_edits INTEGER DEFAULT 0
      );

      CREATE TABLE IF NOT EXISTS training_runs (
        run_id TEXT PRIMARY KEY,
        timestamp REAL NOT NULL,
        model_name TEXT NOT NULL,
        signals_used INTEGER NOT NULL,
        train_loss REAL,
        eval_loss REAL,
        acceptance_rate_before REAL,
        acceptance_rate_after REAL,
        adapter_path TEXT,
        metrics TEXT
      );

      CREATE TABLE IF NOT EXISTS acceptance_metrics (
        date TEXT PRIMARY KEY,
        total_accepts INTEGER DEFAULT 0,
        total_rejects INTEGER DEFAULT 0,
        total_suggestions INTEGER DEFAULT 0,
        acceptance_rate REAL DEFAULT 0.0,
        edit_rate REAL DEFAULT 0.0
      );

      CREATE INDEX IF NOT EXISTS idx_signals_type ON signals(signal_type);
      CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
      CREATE INDEX IF NOT EXISTS idx_signals_language ON signals(language);
      CREATE INDEX IF NOT EXISTS idx_signals_file ON signals(file_path);
      CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session_id);
    `);
    this._save();
  }

  /**
   * Generate a unique session ID for this VS Code session.
   */
  async createSession(): Promise<string> {
    await this._ensureInit();
    const sessionId = crypto.randomUUID();
    const now = Date.now() / 1000;
    this.db.run(
      `INSERT OR IGNORE INTO sessions (session_id, start_time, project_name)
       VALUES (?, ?, ?)`,
      [sessionId, now, this.config.projectName]
    );
    this._save();
    return sessionId;
  }

  /**
   * Capture an accept signal: user accepted the AI suggestion as-is.
   */
  async captureAccept(
    suggestion: string,
    filePath: string,
    lineNumber: number,
    language: string,
    sessionId: string,
    contextBefore: string = "",
    contextAfter: string = "",
    fullContext: string = "",
    suggestionMetadata: Record<string, unknown> = {},
    developerId: string | null = null
  ): Promise<string> {
    await this._ensureInit();
    const signalId = crypto.randomUUID();
    const now = Date.now() / 1000;

    this._insertSignal(
      signalId,
      SignalType.ACCEPT,
      now,
      sessionId,
      filePath,
      lineNumber,
      language,
      suggestion,
      JSON.stringify(suggestionMetadata),
      contextBefore,
      contextAfter,
      fullContext,
      suggestion,
      0,
      developerId || this._anonymizeId()
    );

    this._upsertSessionStats("accept", sessionId, now);
    this._upsertDailyMetrics("accept");
    this._save();
    return signalId;
  }

  /**
   * Capture a reject signal: user dismissed or ignored the AI suggestion.
   */
  async captureReject(
    suggestion: string,
    filePath: string,
    lineNumber: number,
    language: string,
    sessionId: string,
    contextBefore: string = "",
    contextAfter: string = "",
    fullContext: string = "",
    suggestionMetadata: Record<string, unknown> = {},
    developerId: string | null = null
  ): Promise<string> {
    await this._ensureInit();
    const signalId = crypto.randomUUID();
    const now = Date.now() / 1000;

    this._insertSignal(
      signalId,
      SignalType.REJECT,
      now,
      sessionId,
      filePath,
      lineNumber,
      language,
      suggestion,
      JSON.stringify(suggestionMetadata),
      contextBefore,
      contextAfter,
      fullContext,
      null,
      0,
      developerId || this._anonymizeId()
    );

    this._upsertSessionStats("reject", sessionId, now);
    this._upsertDailyMetrics("reject");
    this._save();
    return signalId;
  }

  /**
   * Capture an edit signal: user modified the suggestion before accepting.
   */
  async captureEdit(
    originalSuggestion: string,
    finalCode: string,
    filePath: string,
    lineNumber: number,
    language: string,
    sessionId: string,
    contextBefore: string = "",
    contextAfter: string = "",
    fullContext: string = "",
    suggestionMetadata: Record<string, unknown> = {},
    developerId: string | null = null
  ): Promise<string> {
    await this._ensureInit();
    const signalId = crypto.randomUUID();
    const now = Date.now() / 1000;
    const editDistance = this._computeEditDistance(originalSuggestion, finalCode);

    this._insertSignal(
      signalId,
      SignalType.EDIT,
      now,
      sessionId,
      filePath,
      lineNumber,
      language,
      originalSuggestion,
      JSON.stringify(suggestionMetadata),
      contextBefore,
      contextAfter,
      fullContext,
      finalCode,
      editDistance,
      developerId || this._anonymizeId()
    );

    this._upsertSessionStats("edit", sessionId, now);
    this._upsertDailyMetrics("edit");
    this._save();
    return signalId;
  }

  /**
   * Get capture statistics for status display.
   */
  async getStatistics(): Promise<CaptureStatistics> {
    await this._ensureInit();

    const counts = this.db.exec(
      `SELECT
         COUNT(*) as total,
         SUM(CASE WHEN signal_type = 'accept' THEN 1 ELSE 0 END) as accepts,
         SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
         SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits
       FROM signals`
    );

    const sessionRow = this.db.exec(
      "SELECT COUNT(*) as cnt FROM sessions"
    );

    const totalSignals = counts[0]?.values[0]?.[0] ?? 0;
    const accepts = counts[0]?.values[0]?.[1] ?? 0;
    const rejects = counts[0]?.values[0]?.[2] ?? 0;
    const edits = counts[0]?.values[0]?.[3] ?? 0;
    const sessionCount = sessionRow[0]?.values[0]?.[0] ?? 0;

    return {
      totalSignals: totalSignals as number,
      accepts: accepts as number,
      rejects: rejects as number,
      edits: edits as number,
      dbPath: this.config.dbPath,
      sessionCount: sessionCount as number,
    };
  }

  /**
   * Close the database connection.
   */
  close(): void {
    try {
      this._save();
      if (this.db) {
        this.db.close();
      }
    } catch {
      // Ignore close errors
    }
  }

  // ─── Private Helpers ──────────────────────────────────────────

  private _insertSignal(
    signalId: string,
    signalType: SignalType,
    timestamp: number,
    sessionId: string,
    filePath: string,
    lineNumber: number,
    language: string,
    suggestion: string,
    suggestionMetadata: string,
    contextBefore: string,
    contextAfter: string,
    fullContext: string,
    finalCode: string | null,
    editDistance: number,
    developerId: string
  ): void {
    this.db.run(
      `INSERT INTO signals (
        signal_id, signal_type, timestamp, session_id, file_path, line_number,
        language, framework, project_type, suggestion, suggestion_metadata,
        context_before, context_after, full_context, final_code, edit_distance,
        test_passed, lint_passed, compilation_passed, git_sha, branch_name,
        pr_number, developer_id
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [
        signalId, signalType, timestamp, sessionId, filePath, lineNumber,
        language, null, "general", suggestion, suggestionMetadata,
        contextBefore, contextAfter, fullContext, finalCode, editDistance,
        null, null, null, null, null,
        null, developerId,
      ]
    );
  }

  private _upsertSessionStats(eventType: string, sessionId: string, now: number): void {
    let column: string;
    if (eventType === "accept") column = "total_accepts";
    else if (eventType === "reject") column = "total_rejects";
    else column = "total_edits";

    this.db.run(
      `INSERT INTO sessions (session_id, start_time, project_name, ${column})
       VALUES (?, ?, ?, 1)
       ON CONFLICT(session_id) DO UPDATE SET
         ${column} = ${column} + 1,
         end_time = ?`,
      [sessionId, now, this.config.projectName, now]
    );
  }

  private _upsertDailyMetrics(eventType: string): void {
    const today = new Date().toISOString().slice(0, 10);

    if (eventType === "accept") {
      this.db.run(
        `INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, acceptance_rate)
         VALUES (?, 1, 1, 1.0)
         ON CONFLICT(date) DO UPDATE SET
           total_accepts = total_accepts + 1,
           total_suggestions = total_suggestions + 1,
           acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions`,
        [today]
      );
    } else if (eventType === "reject") {
      this.db.run(
        `INSERT INTO acceptance_metrics (date, total_rejects, total_suggestions, acceptance_rate)
         VALUES (?, 1, 1, 0.0)
         ON CONFLICT(date) DO UPDATE SET
           total_rejects = total_rejects + 1,
           total_suggestions = total_suggestions + 1,
           acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions`,
        [today]
      );
    } else if (eventType === "edit") {
      this.db.run(
        `INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, edit_rate)
         VALUES (?, 1, 1, 0.0)
         ON CONFLICT(date) DO UPDATE SET
           total_accepts = total_accepts + 1,
           total_suggestions = total_suggestions + 1,
           edit_rate = CAST(total_accepts AS REAL) / total_suggestions`,
        [today]
      );
    }
  }

  /**
   * Compute normalized edit distance between original and final code.
   * Matches the Python implementation in capture_engine.py.
   */
  private _computeEditDistance(original: string, final: string): number {
    if (!original) return final ? 1.0 : 0.0;
    if (!final) return 1.0;

    const origLines = original.trim().split("\n");
    const finalLines = final.trim().split("\n");
    const totalLines = Math.max(origLines.length, finalLines.length);
    if (totalLines === 0) return 0.0;

    let diffCount = 0;
    for (let i = 0; i < totalLines; i++) {
      const origLine = i < origLines.length ? origLines[i].trim() : "";
      const finalLine = i < finalLines.length ? finalLines[i].trim() : "";
      if (origLine !== finalLine) diffCount++;
    }

    return diffCount / totalLines;
  }

  private _anonymizeId(): string {
    try {
      const raw = `${os.hostname()}:${os.platform()}:${os.arch()}`;
      return crypto.createHash("sha256").update(raw).digest("hex").slice(0, 16);
    } catch {
      return crypto.createHash("sha256").update(String(process.pid)).digest("hex").slice(0, 16);
    }
  }
}
