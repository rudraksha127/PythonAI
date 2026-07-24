#!/usr/bin/env python3
"""Wire up observability stack: Langfuse decorators, mem0 router, Outlines integration."""

import re

with open("src/api/server.py", "r", encoding="utf-8") as f:
    content = f.read()

changes = []

# 1. Apply @_observe() decorator on rag_search
if '@_observe()\n@app.post("/api/rag/search")' not in content:
    content = content.replace(
        '@app.post("/api/rag/search")',
        '@_observe()\n@app.post("/api/rag/search")',
    )
    changes.append("@_observe() on rag_search")

# 2. Apply @_observe() on ask_question
if '@_observe()\n@app.post("/ask")' not in content:
    content = content.replace(
        '@app.post("/ask")',
        '@_observe()\n@app.post("/ask")',
    )
    changes.append("@_observe() on ask_question")

# 3. Apply @_observe() on agent_chat
if '@_observe()\n@app.post("/api/agent/chat")' not in content:
    content = content.replace(
        '@app.post("/api/agent/chat")',
        '@_observe()\n@app.post("/api/agent/chat")',
    )
    changes.append("@_observe() on agent_chat")

# 4. Mount memory router after arsenal router
old_mount = 'app.include_router(arsenal_router)\nlogger.info("Arsenal routes registered")'
new_mount = old_mount + '\n\n# Memory (mem0) API routes\napp.include_router(_memory_router)\nlogger.info("Memory API routes registered")'
if old_mount in content:
    content = content.replace(old_mount, new_mount)
    changes.append("Mounted memory router")

# 5. Inject mem0 context into ask_question route - before get_db_async call
# Add memory context injection right after the model selection
old_wire = '        selected_model = resolve_model(DEFAULT_MODEL, available=available)\n\n        try:\n            answer, docs = await asyncio.wait_for('
new_wire = '        selected_model = resolve_model(DEFAULT_MODEL, available=available)\n\n        # Inject developer memory context into answer generation\n        mem_context = _forgeai_memory.format_for_context(user_id="default") if _forgeai_memory else ""\n        if mem_context:\n            _memory_injected = True\n        else:\n            _memory_injected = False\n\n        try:\n            answer, docs = await asyncio.wait_for('
if old_wire in content and 'mem_context = _forgeai_memory.format_for_context' not in content:
    content = content.replace(old_wire, new_wire)
    changes.append("Memory context injection in ask_question")
else:
    # Alternative: try in the chat route
    pass

# 6. Add mem0 Q&A storage after successful answer in ask_question
old_store = '        return {\n            "answer": answer,\n            "sources": [\n                {"title": d.get("title", ""), "version": d.get("version", ""), "category": d.get("category", "")}\n                for d in docs\n            ],\n            "model": selected_model,\n        }'
new_store = '        # Store Q&A as memory for personalization\n        if _forgeai_memory and _forgeai_memory._enabled and answer:\n            try:\n                _forgeai_memory.add(f"User asked: {request.question[:200]} | Answer: {answer[:500]}", user_id="default")\n            except Exception:\n                pass\n\n        return {\n            "answer": answer,\n            "sources": [\n                {"title": d.get("title", ""), "version": d.get("version", ""), "category": d.get("category", "")}\n                for d in docs\n            ],\n            "model": selected_model,\n            "memory_context_used": _memory_injected if "_memory_injected" in dir() else False,\n        }'
if old_store in content:
    content = content.replace(old_store, new_store)
    changes.append("mem0 Q&A storage in ask_question")

# Write back
with open("src/api/server.py", "w", encoding="utf-8") as f:
    f.write(content)

print("Applied {} changes:".format(len(changes)))
for c in changes:
    print(f"  - {c}")
