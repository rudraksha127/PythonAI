import * as fs from "fs";
import * as os from "os";
import * as path from "path";
import * as crypto from "crypto";
import initSqlJs, { Database as SqlJsDb } from "sql.js";

let SQL: Awaited<ReturnType<typeof initSqlJs>> | null = null;
let initPromise: Promise<void> | null = null;

async function ensureSqlJs(): Promise<void> {
  if (!initPromise) {
    initPromise = initSqlJs().then((sql) => {
      SQL = sql;
    });
  }
  await initPromise;
}

export interface CaptureSignal {
  signalId: string;
  signalType: "accept" | "reject" | "edit";
  timestamp: number;
  sessionId: string;
  filePath: string;
  lineNumber: number;
  language: string;
  framework: string | null;
  projectType: string;
  suggestion: string;
  suggestionMetadata: string;
  contextBefore: string;
  contextAfter: string;
  contextFull: string;
  finalCode: string | null;
  editDistance: number;
  developerId: string;
}

export interface CaptureStats {
  totalSignals: number;
  totalSessions: number;
  signalsByType: Record<string, number>;
  signalsByLanguage: Record<string, number>;
  acceptanceRate: number;
  avgEditDistance: number;
}

/**
 * CaptureEngine — matches Python SQLite schema exactly.
 * Uses sql.js (pure JS SQLite) so no native compilation needed on Windows.
 */
export class CaptureEngine {
  private db: SqlJsDb | null = null;
  private dbPath: string;
  private sessionId: string;

  constructor(dbPath: string) {
    this.dbPath = dbPath;
    this.sessionId = crypto.randomUUID();
  }

  async initialize(): Promise<void> {
    await ensureSqlJs();
    const dir = path.dirname(this.dbPath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }

    // Load or create database
    let buffer: Buffer | undefined;
    if (fs.existsSync(this.dbPath)) {
      buffer = fs.readFileSync(this.dbPath);
    }
    this.db = new SQL!.Database(buffer);

    // Enable WAL mode for concurrent access with Python
    this.db.run("PRAGMA journal_mode=WAL;");
    this.db.run("PRAGMA foreign_keys=ON;");

    this.createSchema();
  }

  private createSchema(): void {
    this.db!.run(`
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
  }

  async captureAccept(
    suggestion: string,
    filePath: string,
    lineNumber: number,
    language: string,
    contextBefore: string = "",
    contextAfter: string = "",
    contextFull: string = "",
    developerId?: string
  ): Promise<string> {
    const signalId = crypto.randomUUID();
    const ts = Date.now() / 1000;

    this.db!.run(
      `INSERT INTO signals (signal_id, signal_type, timestamp, session_id, file_path, line_number,
        language, project_type, suggestion, context_before, context_after, full_context, final_code, edit_distance, developer_id)
       VALUES (?, 'accept', ?, ?, ?, ?, ?, 'general', ?, ?, ?, ?, ?, 0.0, ?)`,
      [signalId, ts, this.sessionId, filePath, lineNumber, language,
       suggestion, contextBefore, contextAfter, contextFull, suggestion, developerId || this.getAnonymousId()]
    );

    this.updateSession("accept");
    this.updateDailyMetrics("accept");
    return signalId;
  }

  async captureReject(
    suggestion: string,
    filePath: string,
    lineNumber: number,
    language: string,
    contextBefore: string = "",
    contextAfter: string = "",
    contextFull: string = "",
    developerId?: string
  ): Promise<string> {
    const signalId = crypto.randomUUID();
    const ts = Date.now() / 1000;

    this.db!.run(
      `INSERT INTO signals (signal_id, signal_type, timestamp, session_id, file_path, line_number,
        language, project_type, suggestion, context_before, context_after, full_context, developer_id)
       VALUES (?, 'reject', ?, ?, ?, ?, ?, 'general', ?, ?, ?, ?, ?)`,
      [signalId, ts, this.sessionId, filePath, lineNumber, language,
       suggestion, contextBefore, contextAfter, contextFull, developerId || this.getAnonymousId()]
    );

    this.updateSession("reject");
    this.updateDailyMetrics("reject");
    return signalId;
  }

  async captureEdit(
    originalSuggestion: string,
    finalCode: string,
    filePath: string,
    lineNumber: number,
    language: string,
    contextBefore: string = "",
    contextAfter: string = "",
    contextFull: string = "",
    developerId?: string
  ): Promise<string> {
    const signalId = crypto.randomUUID();
    const ts = Date.now() / 1000;
    const editDistance = this.computeEditDistance(originalSuggestion, finalCode);

    this.db!.run(
      `INSERT INTO signals (signal_id, signal_type, timestamp, session_id, file_path, line_number,
        language, project_type, suggestion, context_before, context_after, full_context, final_code, edit_distance, developer_id)
       VALUES (?, 'edit', ?, ?, ?, ?, ?, 'general', ?, ?, ?, ?, ?, ?, ?)`,
      [signalId, ts, this.sessionId, filePath, lineNumber, language,
       originalSuggestion, contextBefore, contextAfter, contextFull, finalCode, editDistance, developerId || this.getAnonymousId()]
    );

    this.updateSession("edit");
    this.updateDailyMetrics("edit");
    return signalId;
  }

  async recordTrainingRun(
    runId: string,
    modelName: string,
    signalsUsed: number,
    acceptanceRateBefore: number,
    acceptanceRateAfter: number,
    trainLoss?: number,
    evalLoss?: number,
    adapterPath?: string,
    metrics?: Record<string, unknown>
  ): Promise<void> {
    const ts = Date.now() / 1000;
    this.db!.run(
      `INSERT INTO training_runs (run_id, timestamp, model_name, signals_used, train_loss, eval_loss,
        acceptance_rate_before, acceptance_rate_after, adapter_path, metrics)
       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      [runId, ts, modelName, signalsUsed, trainLoss ?? null, evalLoss ?? null,
       acceptanceRateBefore, acceptanceRateAfter, adapterPath ?? null,
       metrics ? JSON.stringify(metrics) : null]
    );
  }

  async getStatistics(): Promise<CaptureStats> {
    // Signals by type
    const typeRows = this.db!.exec(
      `SELECT signal_type, COUNT(*) as cnt FROM signals GROUP BY signal_type`
    );
    const signalsByType: Record<string, number> = {};
    if (typeRows.length > 0) {
      for (const row of typeRows[0].values) {
        signalsByType[row[0] as string] = row[1] as number;
      }
    }

    // Signals by language
    const langRows = this.db!.exec(
      `SELECT language, COUNT(*) as cnt FROM signals GROUP BY language ORDER BY cnt DESC LIMIT 10`
    );
    const signalsByLanguage: Record<string, number> = {};
    if (langRows.length > 0) {
      for (const row of langRows[0].values) {
        signalsByLanguage[row[0] as string] = row[1] as number;
      }
    }

    // Total sessions
    const sessionRows = this.db!.exec(`SELECT COUNT(*) as cnt FROM sessions`);
    const totalSessions = sessionRows.length > 0 ? (sessionRows[0].values[0][0] as number) : 0;

    // Total signals
    const totalRows = this.db!.exec(`SELECT COUNT(*) as cnt FROM signals`);
    const totalSignals = totalRows.length > 0 ? (totalRows[0].values[0][0] as number) : 0;

    // Acceptance rate
    const accepts = signalsByType["accept"] || 0;
    const rejects = signalsByType["reject"] || 0;
    const total = accepts + rejects;
    const acceptanceRate = total > 0 ? accepts / total : 0;

    // Avg edit distance
    const editRows = this.db!.exec(
      `SELECT AVG(edit_distance) as avg_ed FROM signals WHERE signal_type = 'edit'`
    );
    const avgEditDistance = editRows.length > 0 && editRows[0].values[0][0] !== null
      ? (editRows[0].values[0][0] as number) : 0;

    return {
      totalSignals,
      totalSessions,
      signalsByType,
      signalsByLanguage,
      acceptanceRate,
      avgEditDistance,
    };
  }

  async getAcceptanceRate(days: number = 7): Promise<Array<{
    date: string; accepts: number; rejects: number; edits: number; total: number; rate: number;
  }>> {
    const cutoff = Date.now() / 1000 - days * 86400;
    const rows = this.db!.exec(`
      SELECT DATE(timestamp, 'unixepoch') as date,
        SUM(CASE WHEN signal_type = 'accept' THEN 1 ELSE 0 END) as accepts,
        SUM(CASE WHEN signal_type = 'reject' THEN 1 ELSE 0 END) as rejects,
        SUM(CASE WHEN signal_type = 'edit' THEN 1 ELSE 0 END) as edits,
        COUNT(*) as total
      FROM signals
      WHERE timestamp >= ${cutoff}
      GROUP BY date
      ORDER BY date
    `);

    if (rows.length === 0) return [];
    return rows[0].values.map((row: any[]) => ({
      date: row[0] as string,
      accepts: row[1] as number,
      rejects: row[2] as number,
      edits: row[3] as number,
      total: row[4] as number,
      rate: (row[4] as number) > 0 ? (row[1] as number) / (row[4] as number) : 0,
    }));
  }

  async close(): Promise<void> {
    if (this.db) {
      const data = this.db.export();
      const buffer = Buffer.from(data);
      fs.writeFileSync(this.dbPath, buffer);
      this.db.close();
      this.db = null;
    }
  }

  // ── Private helpers ──

  private updateSession(eventType: string): void {
    const column = eventType === "accept" ? "total_accepts"
      : eventType === "reject" ? "total_rejects"
      : "total_edits";

    this.db!.run(`
      INSERT INTO sessions (session_id, start_time, project_name)
      VALUES ('${this.sessionId}', ${Date.now() / 1000}, 'vscode')
      ON CONFLICT(session_id) DO UPDATE SET ${column} = ${column} + 1
    `);
  }

  private updateDailyMetrics(eventType: string): void {
    const today = new Date().toISOString().slice(0, 10);

    if (eventType === "accept") {
      this.db!.run(`
        INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, acceptance_rate)
        VALUES ('${today}', 1, 1, 1.0)
        ON CONFLICT(date) DO UPDATE SET
          total_accepts = total_accepts + 1,
          total_suggestions = total_suggestions + 1,
          acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions
      `);
    } else if (eventType === "reject") {
      this.db!.run(`
        INSERT INTO acceptance_metrics (date, total_rejects, total_suggestions, acceptance_rate)
        VALUES ('${today}', 1, 1, 0.0)
        ON CONFLICT(date) DO UPDATE SET
          total_rejects = total_rejects + 1,
          total_suggestions = total_suggestions + 1,
          acceptance_rate = CAST(total_accepts AS REAL) / total_suggestions
      `);
    } else if (eventType === "edit") {
      this.db!.run(`
        INSERT INTO acceptance_metrics (date, total_accepts, total_suggestions, edit_rate)
        VALUES ('${today}', 1, 1, 0.0)
        ON CONFLICT(date) DO UPDATE SET
          total_accepts = total_accepts + 1,
          total_suggestions = total_suggestions + 1,
          edit_rate = CAST(total_accepts AS REAL) / total_suggestions
      `);
    }
  }

  private getAnonymousId(): string {
    const machineId = os.hostname() + os.arch();
    return crypto.createHash("sha256").update(machineId).digest("hex").slice(0, 16);
  }

  private computeEditDistance(original: string, finalCode: string): number {
    if (!original) return finalCode ? 1.0 : 0.0;
    if (!finalCode) return 1.0;

    const origLines = original.trim().split("\n");
    const finalLines = finalCode.trim().split("\n");
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
}
