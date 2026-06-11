from __future__ import annotations

import argparse
import json
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def evaluate(
    adapter_path: str | Path,
    prompts: list[str] | None = None,
    max_new_tokens: int = 96,
    batch: bool = False,
    reference_json: str | None = None,
) -> dict:
    """Evaluate a trained adapter and return summary metrics.

    This is the main entry point used by the training pipeline.
    Loads the adapter, runs inference on test prompts, and returns
    quality metrics (BLEU, ROUGE-L) when reference outputs are provided.

    Args:
        adapter_path: Path to the PEFT adapter directory.
        prompts: Optional list of test prompts. Uses DEFAULT_PROMPTS if None.
        max_new_tokens: Maximum tokens to generate per prompt (default: 96).
        batch: Run all prompts in a single batch for faster evaluation.
        reference_json: Optional path to a JSON file with reference outputs
            for computing BLEU/ROUGE-L scores.

    Returns:
        Dict with evaluation results including per-prompt outputs and metrics.
            Keys: "outputs", "avg_bleu", "avg_rouge_l", "num_prompts"
    """
    if prompts is None:
        prompts = DEFAULT_PROMPTS

    outputs = generate(Path(adapter_path), prompts, max_new_tokens, batch=batch)

    # Compute BLEU/ROUGE-L if reference outputs are provided
    reference_map: dict[str, str] = {}
    if reference_json:
        ref_path = Path(reference_json)
        if ref_path.exists():
            reference_map = load_reference_map(ref_path)

    for item in outputs:
        reference = reference_map.get(item["prompt"], "")
        if reference:
            item["bleu_score"] = round(compute_bleu(reference, item["output"]), 3)
            item["rouge_l"] = round(compute_rouge_l(reference, item["output"]), 3)

    bleu_scores = [o["bleu_score"] for o in outputs if "bleu_score" in o]
    rouge_scores = [o["rouge_l"] for o in outputs if "rouge_l" in o]

    return {
        "outputs": outputs,
        "avg_bleu": sum(bleu_scores) / len(bleu_scores) if bleu_scores else None,
        "avg_rouge_l": sum(rouge_scores) / len(rouge_scores) if rouge_scores else None,
        "num_prompts": len(outputs),
    }


DEFAULT_PROMPTS = [
    "Explain Python context managers like a senior engineer. Include one pitfall.",
    "Review this code and suggest a safer version:\n\n```python\nitems = []\nfor i in range(3):\n    items.append(lambda: i)\n```",
    "What changed between older Python import internals and modern importlib usage?",
]


def load_adapter_config(adapter_path: Path) -> dict:
    config_path = adapter_path / "adapter_config.json"
    if not config_path.exists():
        raise FileNotFoundError(f"Missing adapter config: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8"))


def generate(
    adapter_path: Path,
    prompts: list[str],
    max_new_tokens: int,
    batch: bool = False,
) -> list[dict[str, str]]:
    adapter_config = load_adapter_config(adapter_path)
    base_model = adapter_config["base_model_name_or_path"]

    tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model = PeftModel.from_pretrained(base, adapter_path)
    model.eval()

    outputs: list[dict[str, str]] = []

    if batch:
        # Batch evaluation: format all prompts and generate at once
        formatted = [f"### Instruction:\n{p}\n\n### Response:\n" for p in prompts]
        inputs = tokenizer(
            formatted,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        for i, prompt in enumerate(prompts):
            text = tokenizer.decode(generated[i], skip_special_tokens=True)
            outputs.append(
                {
                    "prompt": prompt,
                    "output": text[len(formatted[i]) :].strip(),
                }
            )
    else:
        # Sequential evaluation (original behavior)
        for prompt in prompts:
            formatted = f"### Instruction:\n{prompt}\n\n### Response:\n"
            inputs = tokenizer(formatted, return_tensors="pt", truncation=True, max_length=512)
            with torch.no_grad():
                generated = model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.pad_token_id,
                    eos_token_id=tokenizer.eos_token_id,
                )
            text = tokenizer.decode(generated[0], skip_special_tokens=True)
            outputs.append({"prompt": prompt, "output": text[len(formatted) :].strip()})

    return outputs


def compute_bleu(reference: str, candidate: str) -> float:
    """Simple BLEU-like score (1-gram precision) for quick quality check."""
    ref_tokens = set(reference.lower().split())
    cand_tokens = candidate.lower().split()
    if not cand_tokens or not ref_tokens:
        return 0.0
    matches = sum(1 for t in cand_tokens if t in ref_tokens)
    return matches / len(cand_tokens)


def compute_rouge_l(reference: str, candidate: str) -> float:
    """ROUGE-L F1 score based on longest common subsequence."""
    ref_tokens = reference.split()
    cand_tokens = candidate.split()
    if not ref_tokens or not cand_tokens:
        return 0.0

    # LCS length (space-optimized DP)
    dp = [0] * (len(cand_tokens) + 1)
    for ref_token in ref_tokens:
        prev = 0
        for j, cand_token in enumerate(cand_tokens, start=1):
            temp = dp[j]
            if ref_token == cand_token:
                dp[j] = prev + 1
            else:
                dp[j] = max(dp[j], dp[j - 1])
            prev = temp

    lcs = dp[-1]
    precision = lcs / len(cand_tokens)
    recall = lcs / len(ref_tokens)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_reference_map(path: Path) -> dict[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "rows" in data and isinstance(data["rows"], list):
        items = data["rows"]
    elif isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    else:
        return {}

    refs: dict[str, str] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = item.get("prompt") or item.get("instruction") or item.get("input")
        output = item.get("output") or item.get("response")
        if prompt and output:
            refs[str(prompt)] = str(output)
    return refs


def interactive_eval(adapter_path: Path, max_new_tokens: int) -> None:
    """Interactive mode: type prompts and see real-time output."""
    print("\nInteractive Evaluation Mode")
    print("Type 'quit' to exit.\n")

    adapter_config = load_adapter_config(adapter_path)
    base_model = adapter_config["base_model_name_or_path"]

    tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        trust_remote_code=True,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
    )
    model = PeftModel.from_pretrained(base, adapter_path)
    model.eval()

    while True:
        try:
            prompt = input(">>> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting interactive mode.")
            break

        if not prompt or prompt.lower() == "quit":
            break

        formatted = f"### Instruction:\n{prompt}\n\n### Response:\n"
        inputs = tokenizer(formatted, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        text = tokenizer.decode(generated[0], skip_special_tokens=True)
        output = text[len(formatted) :].strip()
        print(f"\n{output}\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a local PEFT adapter with fixed prompts.")
    parser.add_argument("--adapter-path", default="checkpoints/local_auto_model")
    parser.add_argument("--max-new-tokens", type=int, default=96)
    parser.add_argument("--output-json", default="checkpoints/local_eval_outputs.json")
    parser.add_argument(
        "--num-prompts", type=int, default=3, help="Number of test prompts to run (uses first N from DEFAULT_PROMPTS)"
    )
    parser.add_argument(
        "--batch", action="store_true", help="Evaluate all prompts in a single batch for faster inference"
    )
    parser.add_argument(
        "--interactive", action="store_true", help="Interactive mode: type prompts and see real-time output"
    )
    parser.add_argument("--reference-json", default="", help="Optional JSON file with reference outputs for metrics")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    adapter_path = Path(args.adapter_path)

    # Interactive mode
    if args.interactive:
        interactive_eval(adapter_path, args.max_new_tokens)
        return

    # Standard evaluation with configurable number of prompts
    prompts = DEFAULT_PROMPTS[: args.num_prompts]
    outputs = generate(adapter_path, prompts, args.max_new_tokens, batch=args.batch)

    reference_map: dict[str, str] = {}
    if args.reference_json:
        reference_path = Path(args.reference_json)
        if reference_path.exists():
            reference_map = load_reference_map(reference_path)
        else:
            print(f"[WARN] Reference file not found: {reference_path}")

    output_path = Path(args.output_json)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Compute metrics if reference outputs are available
    for item in outputs:
        reference = reference_map.get(item["prompt"], "")
        item["reference_output"] = reference
        if reference:
            item["bleu_score"] = round(compute_bleu(reference, item["output"]), 3)
            item["rouge_l"] = round(compute_rouge_l(reference, item["output"]), 3)
        else:
            item["bleu_score"] = None
            item["rouge_l"] = None

    output_path.write_text(json.dumps(outputs, ensure_ascii=False, indent=2), encoding="utf-8")

    for index, item in enumerate(outputs, start=1):
        print(f"\n[Test {index}] {item['prompt']}")
        print(item["output"][:800] or "<empty>")
        if item["bleu_score"] is not None:
            print(f"  BLEU score: {item['bleu_score']:.3f}")
            print(f"  ROUGE-L   : {item['rouge_l']:.3f}")
        else:
            print("  Metrics   : reference output not provided")

    print(f"\nSaved outputs: {output_path}")


if __name__ == "__main__":
    main()
