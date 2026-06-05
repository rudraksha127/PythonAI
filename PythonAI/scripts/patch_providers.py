"""Patch live_server.py to replace racing with round-robin provider distribution."""
import re

with open('live_server.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Change import and docstring
old1 = """async def worker_synthetic():
    \"\"\"Generate synthetic training data using PARALLEL RACING across ALL available providers.\"\"\"
    from src.utils.llm import generate_parallel_async"""

new1 = """async def worker_synthetic():
    \"\"\"Generate synthetic training data using ALL available API providers in parallel.
    Each prompt is assigned round-robin to a specific provider so ALL providers contribute.\"\"\"
    from src.utils.llm import generate_async, get_provider_status as _get_provider_status"""

assert old1 in content, "Old1 not found!"
content = content.replace(old1, new1, 1)

# 2. Add provider discovery after PHASE_START
old2 = """    phase = "Synthetic Data Generation"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    out_dir = BASE_DATA_DIR / "synthetic\""""

new2 = """    phase = "Synthetic Data Generation"
    SYSTEM_STATE["phases"][phase] = "RUNNING"
    SYSTEM_STATE["stats"]["active_tasks"] += 1
    await broadcast("PHASE_START", {"phase": phase})

    # -- Discover ALL available API providers (excluding local) --
    statuses = _get_provider_status()
    active_providers = [s["name"] for s in statuses if s["available"] and s["name"] != "local"]
    if not active_providers:
        active_providers = ["local"]

    await broadcast("LOG", {
        "level": "info",
        "msg": f"[Synthetic-LLM] ALL {len(active_providers)} providers activated: {', '.join(active_providers)}"
    })

    # Per-provider tracking
    provider_stats = {}
    for p in active_providers:
        provider_stats[p] = {"assigned": 0, "success": 0, "failed": 0, "tokens": 0}

    out_dir = BASE_DATA_DIR / "synthetic\""""

assert old2 in content, "Old2 not found!"
content = content.replace(old2, new2, 1)

# 3. Replace generate_and_save and the Semaphore
old3 = """    total_generated = 0
    sem = asyncio.Semaphore(4)  # Run 4 concurrent generations

    async def generate_and_save(task_type: str, system_prompt: str, prompt: str, idx: int, file_handle):
        \"\"\"Generate a single sample using parallel racing and save to file.\"\"\"
        async with sem:
            try:
                response = await generate_parallel_async(
                    prompt,
                    system_prompt=system_prompt,
                )

                row = {
                    "id": f"{task_type}_{idx}_0",
                    "task_type": task_type,
                    "instruction": prompt,
                    "output": response,
                    "source": "parallel_llm",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                line = json.dumps(row, ensure_ascii=False) + "\\n"
                file_handle.write(line)
                file_handle.flush()

                return {"idx": idx, "success": True, "size": len(line)}
            except Exception as e:
                return {"idx": idx, "success": False, "error": str(e)[:100]}"""

new3 = """    total_generated = 0

    async def generate_and_save(task_type: str, system_prompt: str, prompt: str, idx: int, provider_name: str, file_handle):
        \"\"\"Generate a single sample using a specific provider and save to file.\"\"\"
        try:
            response = await generate_async(
                prompt,
                provider=provider_name,
                system_prompt=system_prompt,
            )

            provider_stats[provider_name]["assigned"] += 1
            provider_stats[provider_name]["success"] += 1
            provider_stats[provider_name]["tokens"] += len(response)

            row = {
                "id": f"{task_type}_{idx}_0",
                "task_type": task_type,
                "instruction": prompt,
                "output": response,
                "provider": provider_name,
                "source": "parallel_llm",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            line = json.dumps(row, ensure_ascii=False) + "\\n"
            file_handle.write(line)
            file_handle.flush()

            return {"idx": idx, "success": True, "size": len(line), "provider": provider_name}
        except Exception as e:
            provider_stats[provider_name]["assigned"] += 1
            provider_stats[provider_name]["failed"] += 1
            # Fallback: try with next available provider
            try:
                fallback_providers = [p for p in active_providers if p != provider_name]
                if fallback_providers:
                    fb = fallback_providers[idx % len(fallback_providers)]
                    response = await generate_async(prompt, provider=fb, system_prompt=system_prompt)
                    provider_stats[fb]["assigned"] += 1
                    provider_stats[fb]["success"] += 1
                    provider_stats[fb]["tokens"] += len(response)
                    row = {
                        "id": f"{task_type}_{idx}_0",
                        "task_type": task_type,
                        "instruction": prompt,
                        "output": response,
                        "provider": fb,
                        "source": "parallel_llm",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    line = json.dumps(row, ensure_ascii=False) + "\\n"
                    file_handle.write(line)
                    file_handle.flush()
                    return {"idx": idx, "success": True, "size": len(line), "provider": fb}
            except Exception:
                pass
            return {"idx": idx, "success": False, "error": str(e)[:100], "provider": provider_name}"""

assert old3 in content, "Old3 not found!"
content = content.replace(old3, new3, 1)

# 4. Replace the task creation loop and broadcast messages
old4 = """            await broadcast("LOG", {"level": "info", "msg": f"[Synthetic-LLM] Generating: {task_type} ({len(config['prompts'])} prompts via parallel racing)"})
            SYSTEM_STATE["agents"]["code"]["status"] = "active"
            SYSTEM_STATE["agents"]["code"]["last_action"] = f"Generating {task_type} (racing all providers)"""

new4 = """            # Build per-provider assignment list for this task
            provider_assignments = {}
            for i, _ in enumerate(config["prompts"]):
                p = active_providers[i % len(active_providers)]
                provider_assignments[p] = provider_assignments.get(p, 0) + 1
            assignment_str = ", ".join(f"{p}:{c}" for p, c in sorted(provider_assignments.items()))

            await broadcast("LOG", {"level": "info", "msg": f"[Synthetic-LLM] Generating: {task_type} ({len(config['prompts'])} prompts -> {assignment_str})"})
            SYSTEM_STATE["agents"]["code"]["status"] = "active"
            SYSTEM_STATE["agents"]["code"]["last_action"] = f"Distributing {task_type} across {len(active_providers)} providers"""

assert old4 in content, "Old4 not found!"
content = content.replace(old4, new4, 1)

# 5. Replace the task creation loop body
old5 = """                # Create ALL generation tasks upfront for concurrent execution
                tasks = []
                for i, prompt in enumerate(config["prompts"]):
                    task = asyncio.create_task(
                        generate_and_save(task_type, config["system"], prompt, i, f)
                    )
                    tasks.append(task)

                # Wait for all to complete
                results = await asyncio.gather(*tasks, return_exceptions=False)

            # Summarize results
            success_count = sum(1 for r in results if r.get("success"))
            total_size = sum(r.get("size", 0) for r in results if r.get("success"))
            total_generated += success_count

            SYSTEM_STATE["stats"]["synthetic_rows"] = total_generated
            await broadcast("LOG", {
                "level": "success",
                "msg": f"[Synthetic-LLM] [OK] {task_type}: {success_count}/{len(config['prompts'])} samples saved ({total_size/1024:.1f} KB)"
            })"""

new5 = """                # Create ALL generation tasks upfront for concurrent execution
                # Each prompt assigned to a specific provider round-robin
                tasks = []
                for i, prompt in enumerate(config["prompts"]):
                    provider_name = active_providers[i % len(active_providers)]
                    task = asyncio.create_task(
                        generate_and_save(task_type, config["system"], prompt, i, provider_name, f)
                    )
                    tasks.append(task)

                # Wait for all to complete
                results = await asyncio.gather(*tasks, return_exceptions=True)

            # Summarize results
            success_count = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
            total_size = sum(r.get("size", 0) for r in results if isinstance(r, dict) and r.get("success"))
            total_generated += success_count

            # Per-provider summary for this task
            provider_summary = {}
            for r in results:
                if isinstance(r, dict) and r.get("success"):
                    p = r.get("provider", "unknown")
                    provider_summary[p] = provider_summary.get(p, 0) + 1
            summary_str = ", ".join(f"{p}:{c}" for p, c in sorted(provider_summary.items())) if provider_summary else "all failed"

            SYSTEM_STATE["stats"]["synthetic_rows"] = total_generated
            await broadcast("LOG", {
                "level": "success",
                "msg": f"[Synthetic-LLM] [OK] {task_type}: {success_count}/{len(config['prompts'])} saved ({total_size/1024:.1f} KB) [{summary_str}]"
            })"""

assert old5 in content, "Old5 not found!"
content = content.replace(old5, new5, 1)

# Write back
with open('live_server.py', 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open('live_server.py', 'r', encoding='utf-8', newline='') as f:
    final = f.read()

checks = [
    ("active_providers", "active_providers" in final),
    ("generate_async", "from src.utils.llm import generate_async" in final),
    ("NOT generate_parallel_async", "generate_parallel_async" not in final),
    ("provider_name in loop", "provider_name = active_providers[i % len(active_providers)]" in final),
    ("return_exceptions=True", "return_exceptions=True" in final),
    ("provider_summary", "provider_summary" in final),
]

all_ok = True
for label, result in checks:
    status = "OK" if result else "FAIL"
    if not result:
        all_ok = False
    print(f"  [{status}] {label}")

if all_ok:
    print("\n All 6 changes applied successfully!")
else:
    print("\n Some changes failed!")
    exit(1)
