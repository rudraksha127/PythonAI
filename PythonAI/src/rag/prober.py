from __future__ import annotations

import argparse
import subprocess
import sys
import types
from pathlib import Path

import torch


DEFAULT_PROMPT = (
    "You are PYTHON MASTER. Explain Python list comprehensions with one runnable "
    "example and one common pitfall."
)


def install_airllm_transformers5_shim() -> None:
    module = types.ModuleType("optimum.bettertransformer")

    class BetterTransformer:
        @staticmethod
        def transform(model):
            return model

    module.BetterTransformer = BetterTransformer
    sys.modules["optimum.bettertransformer"] = module


def run_ollama(model: str, prompt: str, num_ctx: int) -> str:
    try:
        import ollama

        response = ollama.generate(
            model=model,
            prompt=prompt,
            options={"num_ctx": num_ctx, "temperature": 0.2},
        )
        return str(response.get("response", "")).strip()
    except Exception as api_exc:
        command = ["ollama", "run", model, prompt]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"{api_exc}; CLI fallback failed: {detail}")
        return completed.stdout.strip()


def run_airllm(model: str, prompt: str, max_new_tokens: int) -> str:
    if not torch.cuda.is_available():
        return "AirLLM probe skipped: CUDA is not available on this machine."

    install_airllm_transformers5_shim()
    from airllm import AutoModel

    air_model = AutoModel.from_pretrained(model)
    tokenizer = air_model.tokenizer
    inputs = tokenizer([prompt], return_tensors="pt", return_attention_mask=False)
    output = air_model.generate(
        inputs["input_ids"].cuda(),
        max_new_tokens=max_new_tokens,
        use_cache=True,
        return_dict_in_generate=True,
    )
    return tokenizer.decode(output.sequences[0])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe local Qwen through Ollama and optional AirLLM.")
    parser.add_argument("--ollama-model", default="qwen2.5-coder:14b")
    parser.add_argument("--airllm-model", default="")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT)
    parser.add_argument("--num-ctx", type=int, default=512)
    parser.add_argument("--max-new-tokens", type=int, default=96)
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    print("Ollama probe")
    print("-" * 72)
    try:
        print(run_ollama(args.ollama_model, args.prompt, args.num_ctx)[:2000])
    except Exception as exc:
        print(f"Ollama probe failed: {exc}")

    if args.airllm_model:
        print("\nAirLLM probe")
        print("-" * 72)
        try:
            print(run_airllm(args.airllm_model, args.prompt, args.max_new_tokens)[:2000])
        except Exception as exc:
            print(f"AirLLM probe failed: {exc}")
    else:
        print("\nAirLLM probe skipped: pass --airllm-model with an HF-format model path or id.")


if __name__ == "__main__":
    main()
