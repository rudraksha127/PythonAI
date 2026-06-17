#!/usr/bin/env python3
"""
Integration Matrix Generator
Shows which repos from 14.md are already integrated in the ForgeAI ecosystem
and recommends which ones to integrate next.
"""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
CATALOG_PATH = PROJECT_ROOT / "ai_ml_repo_catalog.json"

# Tools that are already integrated in the ForgeAI ecosystem
ALREADY_INTEGRATED = {
    "inference": ["ollama/ollama", "vllm-project/vllm", "sgl-project/sglang", "ggml-org/llama.cpp"],
    "finetuning": ["unslothai/unsloth", "huggingface/peft", "huggingface/trl", "OpenRLHF/OpenRLHF", "hiyouga/LLaMA-Factory"],
    "rag": ["chroma-core/chroma", "run-llama/llama_index", "HKUDS/LightRAG", "microsoft/graphrag", "infiniflow/ragflow"],
    "vector-db": ["chroma-core/chroma", "qdrant/qdrant", "facebookresearch/faiss", "lancedb/lancedb", "weaviate/weaviate"],
    "ml-framework": ["huggingface/transformers", "pytorch/pytorch", "ml-explore/mlx"],
    "agent": ["langchain-ai/langchain", "langchain-ai/langgraph", "microsoft/autogen",
              "crewAIInc/crewAI", "pydantic/pydantic-ai", "phidatahq/phidata",
              "agno-agi/agno", "Significant-Gravitas/AutoGPT", "stanfordnlp/dspy"],
    "cli": ["opencode-ai/opencode", "google-gemini/gemini-cli", "paul-gauthier/aider",
            "All-Hands-AI/OpenHands", "KillianLucas/open-interpreter"],
    "mcp": ["modelcontextprotocol/servers", "modelcontextprotocol/python-sdk"],
    "evaluation": ["explodinggradients/ragas", "confident-ai/deepeval", "EleutherAI/lm-evaluation-harness"],
    "datasets": ["huggingface/datasets", "argilla-io/distilabel", "argilla-io/argilla",
                 "HumanSignal/label-studio"],
    "monitoring": ["langfuse/langfuse", "mlflow/mlflow", "wandb/wandb"],
    "chat-ui": ["open-webui/open-webui", "langgenius/dify", "gradio-app/gradio",
                "streamlit/streamlit", "Chainlit/chainlit"],
    "quantization": ["casper-hansen/AutoAWQ", "AutoGPTQ/AutoGPTQ",
                     "bitsandbytes-foundation/bitsandbytes"],
    "safety": ["guardrails-ai/guardrails", "guidance-ai/guidance", "NVIDIA/NeMo-Guardrails"],
    "memory": ["mem0ai/mem0", "cpacker/MemGPT"],
    "speech": ["openai/whisper", "suno-ai/bark"],
    "image": ["huggingface/diffusers", "black-forest-labs/flux"],
    "knowledge-graph": ["networkx/networkx"],
    "structured-output": ["dottxt-ai/outlines"],
    "data": ["microsoft/playwright", "browser-use/browser-use", "scrapy/scrapy",
             "unclecode/crawl4ai", "mendableai/firecrawl"],
}

# Priority integration recommendations
PRIORITY_RECOMMENDATIONS = {
    "COMPLETED (Cloned + Wrappers Ready)": [
        ("dottxt-ai/outlines", "outlines", "✅ Cloned — structured output bridge ready (src/integration/outlines_bridge.py)"),
        ("stanfordnlp/dspy", "dspy", "✅ Cloned — prompt optimization bridge ready (src/integration/dspy_bridge.py)"),
        ("infiniflow/ragflow", "ragflow", "✅ Cloned — document RAG bridge ready (src/integration/ragflow_bridge.py)"),
        ("cpacker/MemGPT", "letta-ai/letta", "✅ Cloned — memory agent bridge ready (src/integration/memgpt_bridge.py)"),
        ("weaviate/weaviate", "weaviate", "✅ Cloned — vector DB bridge ready (src/integration/weaviate_bridge.py)"),
    ],
    "SHORT TERM (This Month)": [
        ("neuml/txtai", "txtai", "All-in-one embeddings database"),
        ("deepset-ai/haystack", "haystack", "Production RAG pipeline framework"),
        ("unclecode/crawl4ai", "crawl4ai", "Auto-learn from web docs"),
        ("stanford-oval/storm", "storm", "Research report generation"),
    ],
    "MEDIUM TERM (Next Month)": [
        ("getzep/graphiti", "graphiti", "Temporal knowledge graph for agent memory"),
        ("HKUDS/LightRAG", "lightrag", "Graph+Vector hybrid RAG (3x better)"),
        ("langflow-ai/langflow", "langflow", "Visual agent workflow builder"),
        ("FlowiseAI/Flowise", "flowise", "No-code LangChain workflows"),
        ("n8n-io/n8n", "n8n", "AI workflow automation"),
    ],
    "LONG TERM (This Quarter)": [
        ("NVIDIA/TensorRT-LLM", "tensorrt-llm", "Max inference performance on NVIDIA"),
        ("SearXNG/searxng", "searxng", "Self-hosted meta-search engine"),
        ("tryolabs/norfair", "norfair", "Real-time object tracking"),
        ("deepset-ai/prompt-hub", "prompthub", "Community prompt templates"),
    ],
}


def load_catalog() -> dict:
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def is_integrated(full_name: str) -> bool:
    """Check if a repo is already integrated (exact match only)."""
    fn_lower = full_name.lower()
    for cat_repos in ALREADY_INTEGRATED.values():
        for r in cat_repos:
            if fn_lower == r.lower():
                return True
    return False


def generate_matrix_report(catalog: dict) -> str:
    lines = []
    lines.append("# AI/ML Repo Integration Matrix")
    lines.append("## ForgeAI Ecosystem — From 14.md Research Document")
    lines.append("")
    lines.append(f"Total repos in catalog: {catalog['total_repos']}")
    lines.append(f"Already integrated: {sum(len(v) for v in ALREADY_INTEGRATED.values())}")
    lines.append("")

    # Section 1: Already integrated
    lines.append("## ✅ Already Integrated in ForgeAI")
    lines.append("")
    for cat, repos in sorted(ALREADY_INTEGRATED.items()):
        lines.append(f"### {cat.title()}")
        for repo in repos:
            full_name = repo
            desc = ""
            for r in catalog["all_repos"]:
                if r["full_name"].lower() == repo.lower() or repo.lower() in r["full_name"].lower():
                    desc = r.get("details", {}).get("description", "") or r.get("details", {}).get("specialty", "")
                    break
            desc_str = f" — {desc}" if desc else ""
            lines.append(f"- [{full_name}](https://github.com/{full_name}){desc_str}")
        lines.append("")

    # Section 2: Integration recommendations
    lines.append("## 🎯 Integration Recommendations")
    lines.append("")
    for priority, repos in PRIORITY_RECOMMENDATIONS.items():
        lines.append(f"### {priority}")
        for full_name, name, reason in repos:
            lines.append(f"- **[{full_name}](https://github.com/{full_name})** — {reason}")
        lines.append("")

    # Section 3: Stats by category
    lines.append("## 📊 Coverage by Category")
    lines.append("")
    lines.append("| Category | Total Repos | Integrated | Coverage |")
    lines.append("|----------|------------|------------|----------|")
    for cat in sorted(catalog["categories"], key=lambda c: len(c["repos"]), reverse=True):
        cat_slug = cat["slug"]
        total = len(cat["repos"])
        integrated_count = sum(1 for repo in cat["repos"] if is_integrated(repo["full_name"]))
        coverage = f"{integrated_count}/{total}"
        lines.append(f"| {cat['name']} | {total} | {integrated_count} | {coverage} |")

    lines.append("")
    lines.append("---")
    lines.append("*Generated from 14.md research document*")
    lines.append("")

    return "\n".join(lines)


def main():
    print("Loading catalog...")
    catalog = load_catalog()
    print(f"Loaded {catalog['total_repos']} repos")

    print("Generating integration matrix...")
    report = generate_matrix_report(catalog)

    output_path = PROJECT_ROOT / "docs" / "INTEGRATION_MATRIX.md"
    output_path.parent.mkdir(exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Saved to {output_path}")

    # Stats
    total_integrated = sum(len(v) for v in ALREADY_INTEGRATED.values())
    print(f"\nAlready integrated: {total_integrated} repos")
    print(f"Priority recommendations: {sum(len(v) for v in PRIORITY_RECOMMENDATIONS.values())}")
    print(f"\nNext steps by priority:")
    for priority, repos in PRIORITY_RECOMMENDATIONS.items():
        print(f"  {priority}:")
        for full_name, name, reason in repos:
            print(f"    - {full_name}: {reason}")


if __name__ == "__main__":
    main()
