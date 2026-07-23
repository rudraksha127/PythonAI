#!/usr/bin/env python3
"""Temporary import check script for M1 environment setup."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

modules = [
    'src.config',
    'src.rag.rag_engine',
    'src.learning.capture_engine',
    'src.training.run',
    'src.api.server',
    'src.agents.code',
    'src.agents.orchestrator',
    'src.core.providers.registry',
    'src.review.engine',
    'src.battle.engine',
    'src.cloud.auth',
    'src.data.collector',
    'src.data.orchestrator',
    'src.data.generator',
    'src.data.quality',
    'src.integration.hermes_bridge',
    'src.integration.outlines_bridge',
    'src.integration.dspy_bridge',
    'src.integration.weaviate_bridge',
    'src.learning.daemon',
    'src.learning.self_eval',
    'src.training.trainer',
    'src.training.grpo_trainer',
    'src.training.sdft_trainer',
]

success = 0
fail = 0

print("=" * 60)
print("FORGEAI - IMPORT CHECK")
print("=" * 60)

for m in modules:
    try:
        __import__(m)
        print("  [OK] %s" % m)
        success += 1
    except ImportError as e:
        print("  [FAIL] %s -> %s" % (m, str(e)))
        fail += 1
    except Exception as e:
        print("  [WARN] %s -> %s: %s" % (m, type(e).__name__, str(e)))
        fail += 1

print("=" * 60)
print(f"Results: {success} passed, {fail} failed out of {len(modules)}")
print("=" * 60)

# Exit with error code if any failed
sys.exit(0 if fail == 0 else 1)
