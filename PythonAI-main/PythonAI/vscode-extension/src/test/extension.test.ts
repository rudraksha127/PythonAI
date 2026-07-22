import * as path from "path";
import * as fs from "fs";
import * as os from "os";

// Simple test runner for ForgeAI Capture Engine
let passed = 0;
let failed = 0;

function assert(condition: boolean, message: string): void {
  if (condition) {
    passed++;
    console.log(`  ✓ ${message}`);
  } else {
    failed++;
    console.error(`  ✗ ${message}`);
  }
}

async function testCaptureEngine(): Promise<void> {
  console.log("\n[Test] CaptureEngine Tests\n");

  const testDbPath = path.join(os.tmpdir(), `forgeai-test-${Date.now()}.db`);

  try {
    // Dynamic import of compiled JS
    const { CaptureEngine } = require("../captureEngine");

    // Test 1: Initialize database
    const engine = new CaptureEngine(testDbPath);
    await engine.initialize();
    assert(true, "Initialize database");

    // Test 2: Capture accept signal
    const acceptId = await engine.captureAccept(
      "def foo():\n    return 42",
      "/test/file.py",
      1,
      "python",
      "context before",
      "context after",
      "full context"
    );
    assert(acceptId.length > 0, "Capture accept signal returns valid ID");

    // Test 3: Capture reject signal
    const rejectId = await engine.captureReject(
      "def bar():\n    pass",
      "/test/file.py",
      5,
      "python",
      "",
      "",
      ""
    );
    assert(rejectId.length > 0, "Capture reject signal returns valid ID");

    // Test 4: Capture edit signal
    const editId = await engine.captureEdit(
      "def baz():\n    pass",
      "def baz():\n    return 99",
      "/test/file.py",
      10,
      "python"
    );
    assert(editId.length > 0, "Capture edit signal returns valid ID");

    // Test 5: Get statistics
    const stats = await engine.getStatistics();
    assert(stats.totalSignals === 3, `Statistics shows 3 signals (got ${stats.totalSignals})`);
    assert(stats.signalsByType["accept"] === 1, "Statistics shows 1 accept");
    assert(stats.signalsByType["reject"] === 1, "Statistics shows 1 reject");
    assert(stats.signalsByType["edit"] === 1, "Statistics shows 1 edit");
    assert(stats.totalSessions > 0, "Statistics shows at least 1 session");
    assert(typeof stats.acceptanceRate === "number", "Acceptance rate is a number");

    // Test 6: Record training run
    await engine.recordTrainingRun(
      "test-run-1",
      "test-model",
      3,
      0.5,
      0.75,
      0.1,
      0.05,
      "/checkpoints/test"
    );
    assert(true, "Record training run");

    // Test 7: Get acceptance rate
    const rates = await engine.getAcceptanceRate(30);
    assert(rates.length > 0, "Acceptance rate returns at least 1 entry");

    // Test 8: Export and re-load database
    await engine.close();
    assert(true, "Close and export database");

    // Re-open and verify data persisted
    const engine2 = new CaptureEngine(testDbPath);
    await engine2.initialize();
    const stats2 = await engine2.getStatistics();
    assert(stats2.totalSignals === 3, "Re-loaded database shows 3 signals");
    await engine2.close();

  } catch (err: any) {
    console.error(`[ERROR] ${err.message}`);
    console.error(err.stack);
    failed++;
  } finally {
    // Cleanup test database
    try {
      if (fs.existsSync(testDbPath)) fs.unlinkSync(testDbPath);
      if (fs.existsSync(testDbPath + "-wal")) fs.unlinkSync(testDbPath + "-wal");
      if (fs.existsSync(testDbPath + "-shm")) fs.unlinkSync(testDbPath + "-shm");
    } catch {}
  }

  console.log(`\nResults: ${passed} passed, ${failed} failed\n`);
  process.exit(failed > 0 ? 1 : 0);
}

testCaptureEngine();
