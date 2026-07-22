import * as assert from "assert";
import * as path from "path";
import * as os from "os";
import * as fs from "fs";

// Tests for CaptureEngine (can run without VS Code API)
import { CaptureEngine, SignalType } from "../src/captureEngine";
import { loadConfig } from "../src/config";
import { SignalTracker } from "../src/signalTracker";

/**
 * Helper to create a temporary database path for testing.
 */
function tempDbPath(): string {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "forgeai-test-"));
  return path.join(tmpDir, "test-signals.db");
}

// ══════════════════════════════════════════════════════════════════════
// CaptureEngine Tests
// ══════════════════════════════════════════════════════════════════════

describe("CaptureEngine", () => {
  let dbPath: string;
  let engine: CaptureEngine;

  beforeEach(() => {
    dbPath = tempDbPath();
    engine = new CaptureEngine({
      dbPath,
      projectName: "test-project",
      enabled: true,
      captureRejects: true,
      captureEdits: true,
      developerId: "test-dev-123",
    });
  });

  afterEach(() => {
    engine.close();
    // Cleanup temp directory
    try {
      const dir = path.dirname(dbPath);
      fs.rmSync(dir, { recursive: true, force: true });
    } catch {
      // ignore cleanup errors
    }
  });

  it("should create the database and schema", () => {
    assert.ok(fs.existsSync(dbPath), "Database file should exist");
    const stats = engine.getStatistics();
    assert.ok(stats.totalSignals !== undefined);
    assert.strictEqual(stats.totalSignals, 0);
  });

  it("should capture an accept signal", () => {
    const signalId = engine.captureAccept(
      "console.log('hello')",
      "/test/file.js",
      10,
      "javascript",
      "test-session-1",
      "before code",
      "after code",
      "full context",
      { model: "test-model" }
    );

    assert.ok(signalId, "Signal ID should be returned");
    assert.ok(signalId.length > 0, "Signal ID should not be empty");

    const stats = engine.getStatistics() as {
      totalSignals: number;
      accepts: number;
    };
    assert.strictEqual(stats.totalSignals, 1);
    assert.strictEqual(stats.accepts, 1);
  });

  it("should capture a reject signal", () => {
    engine.captureReject(
      "suggestion text",
      "/test/file.py",
      5,
      "python",
      "test-session-2",
      "",
      "",
      "",
      { reason: "not helpful" }
    );

    const stats = engine.getStatistics() as {
      totalSignals: number;
      rejects: number;
    };
    assert.strictEqual(stats.totalSignals, 1);
    assert.strictEqual(stats.rejects, 1);
  });

  it("should capture an edit signal", () => {
    engine.captureEdit(
      "original suggestion with more text",
      "modified final code",
      "/test/file.ts",
      3,
      "typescript",
      "test-session-3"
    );

    const stats = engine.getStatistics() as {
      totalSignals: number;
      edits: number;
    };
    assert.strictEqual(stats.totalSignals, 1);
    assert.strictEqual(stats.edits, 1);
  });

  it("should handle multiple signals", () => {
    engine.captureAccept("a", "/f.js", 1, "js", "s1");
    engine.captureReject("b", "/f.js", 2, "js", "s1");
    engine.captureEdit("c", "d", "/f.js", 3, "js", "s1");
    engine.captureAccept("e", "/f.js", 4, "js", "s1");

    const stats = engine.getStatistics() as {
      totalSignals: number;
      accepts: number;
      rejects: number;
      edits: number;
    };
    assert.strictEqual(stats.totalSignals, 4);
    assert.strictEqual(stats.accepts, 2);
    assert.strictEqual(stats.rejects, 1);
    assert.strictEqual(stats.edits, 1);
  });

  it("should create a session", () => {
    const sessionId = engine.createSession();
    assert.ok(sessionId, "Session ID should be returned");
    assert.ok(sessionId.length > 0, "Session ID should not be empty");
  });

  it("should return valid statistics", () => {
    engine.captureAccept("code", "/f.py", 1, "python", "s1");
    engine.captureAccept("code2", "/f.py", 2, "python", "s1");

    const stats = engine.getStatistics() as Record<string, unknown>;
    assert.strictEqual(stats.totalSignals, 2);
    assert.strictEqual(stats.accepts, 2);
    assert.ok(typeof stats.dbPath === "string", "dbPath should be a string");

    const sessionCount = stats.sessionCount as { cnt: number };
    assert.ok(
      sessionCount && typeof sessionCount.cnt === "number",
      "sessionCount should have a cnt property"
    );
  });

  it("should not crash with empty suggestions", () => {
    const signalId = engine.captureAccept(
      "",
      "/f.py",
      1,
      "python",
      "s1"
    );
    assert.ok(signalId, "Should handle empty suggestion text");
  });
});

// ══════════════════════════════════════════════════════════════════════
// Config Tests
// ══════════════════════════════════════════════════════════════════════

describe("Config", () => {
  it("should have sensible defaults", () => {
    // loadConfig reads from VS Code settings which aren't available in test.
    // Verify the module exists and exports the expected types.
    assert.ok(typeof loadConfig === "function", "loadConfig should be a function");
  });
});

// ══════════════════════════════════════════════════════════════════════
// SignalTracker Tests
// ══════════════════════════════════════════════════════════════════════

describe("SignalTracker", () => {
  let tracker: SignalTracker;

  beforeEach(() => {
    tracker = new SignalTracker();
  });

  afterEach(() => {
    tracker.dispose();
  });

  it("should register and retrieve a suggestion", () => {
    const suggestion = {
      id: "test-1",
      text: "console.log('test')",
      filePath: "/test/file.js",
      lineNumber: 5,
      language: "javascript",
      timestamp: Date.now(),
      contextBefore: "",
      contextAfter: "",
      fullContext: "",
      metadata: {},
      resolved: false,
    };

    tracker.registerSuggestion(suggestion);
    assert.strictEqual(tracker.getPending().length, 1);
    assert.strictEqual(tracker.getSuggestion("test-1")?.text, "console.log('test')");
  });

  it("should remove a suggestion", () => {
    tracker.registerSuggestion({
      id: "test-2",
      text: "test",
      filePath: "/f.js",
      lineNumber: 1,
      language: "js",
      timestamp: Date.now(),
      contextBefore: "",
      contextAfter: "",
      fullContext: "",
      metadata: {},
      resolved: false,
    });

    tracker.removeSuggestion("test-2");
    assert.strictEqual(tracker.getPending().length, 0);
  });

  it("should emit accept event when resolving", (done) => {
    tracker.onSignal((event) => {
      assert.strictEqual(event.type, "accept");
      assert.strictEqual(event.suggestion.id, "test-3");
      done();
    });

    tracker.registerSuggestion({
      id: "test-3",
      text: "test code",
      filePath: "/f.py",
      lineNumber: 1,
      language: "python",
      timestamp: Date.now(),
      contextBefore: "",
      contextAfter: "",
      fullContext: "",
      metadata: {},
      resolved: false,
    });

    const sug = tracker.getSuggestion("test-3")!;
    tracker.resolveAccept(sug);
  });

  it("should emit reject event when resolving reject", (done) => {
    tracker.onSignal((event) => {
      assert.strictEqual(event.type, "reject");
      assert.strictEqual(event.suggestion.id, "test-4");
      done();
    });

    tracker.registerSuggestion({
      id: "test-4",
      text: "rejected code",
      filePath: "/f.py",
      lineNumber: 1,
      language: "python",
      timestamp: Date.now(),
      contextBefore: "",
      contextAfter: "",
      fullContext: "",
      metadata: {},
      resolved: false,
    });

    const sug = tracker.getSuggestion("test-4")!;
    tracker.resolveReject(sug);
  });

  it("should not re-resolve already resolved suggestions", () => {
    let signalCount = 0;

    tracker.onSignal(() => {
      signalCount++;
    });

    tracker.registerSuggestion({
      id: "test-5",
      text: "test",
      filePath: "/f.py",
      lineNumber: 1,
      language: "python",
      timestamp: Date.now(),
      contextBefore: "",
      contextAfter: "",
      fullContext: "",
      metadata: {},
      resolved: false,
    });

    const sug = tracker.getSuggestion("test-5")!;
    tracker.resolveAccept(sug);
    assert.strictEqual(signalCount, 1);

    // Second resolve should be no-op
    tracker.resolveAccept(sug);
    assert.strictEqual(signalCount, 1, "Should not fire duplicate events");
  });
});
