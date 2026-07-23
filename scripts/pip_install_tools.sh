#!/bin/bash
# AI/ML GitHub - pip install tools by category
CATEGORY="${1:-all}"
install_cat() { local l="$1"; shift; echo "  [$l] $# pkgs"; for p in "$@"; do pip install -q "$p" 2>/dev/null || echo "  FAIL: $p"; done }
case "$CATEGORY" in
    core) install_cat "core" torch transformers datasets sentence-transformers scikit-learn fastapi pydantic tiktoken spacy nltk xgboost lightgbm ;;
    inference) install_cat "inference" vllm sglang litellm gpt4all exllamav2 ;;
    finetuning) install_cat "finetuning" peft trl unsloth flash-attention bitsandbytes ;;
    agents) install_cat "agents" langchain langgraph pydantic-ai phidata crewai camel-ai instructor outlines guidance openai-agents ;;
    rag) install_cat "rag" llama-index haystack ragas unstructured mem0ai chromadb faiss-cpu lancedb ;;
    vector-db) install_cat "vector-db" chromadb faiss-cpu lancedb usearch annoy ;;
    ml) install_cat "ml" transformers datasets ultralytics optuna wandb mlflow sentence-transformers ;;
    eval) install_cat "eval" deepeval ragas lm-eval ;;
    speech) install_cat "speech" openai-whisper faster-whisper bark TTS speechbrain ;;
    image) install_cat "image" diffusers ;;
    safety) install_cat "safety" guardrails-ai llm-guard ;;
    monitor) install_cat "monitor" langfuse helicone openllmetry ;;
    quant) install_cat "quant" autoawq auto-gptq bitsandbytes optimum ;;
    data) install_cat "data" beautifulsoup4 scrapy crawl4ai duckduckgo_search docling marker browser-use ;;
    ui) install_cat "ui" gradio streamlit chainlit ;;
    all)
        install_cat "core" torch transformers datasets sentence-transformers scikit-learn fastapi pydantic tiktoken spacy nltk xgboost lightgbm
        install_cat "inference" vllm sglang litellm gpt4all exllamav2
        install_cat "finetuning" peft trl unsloth flash-attention bitsandbytes
        install_cat "agents" langchain langgraph pydantic-ai phidata crewai camel-ai instructor outlines guidance openai-agents
        install_cat "rag" llama-index haystack ragas unstructured mem0ai chromadb faiss-cpu lancedb
        install_cat "vector-db" chromadb faiss-cpu lancedb usearch annoy
        install_cat "ml" transformers datasets ultralytics optuna wandb mlflow sentence-transformers
        install_cat "eval" deepeval ragas lm-eval
        install_cat "speech" openai-whisper faster-whisper bark TTS speechbrain
        install_cat "image" diffusers
        install_cat "safety" guardrails-ai llm-guard
        install_cat "monitor" langfuse helicone openllmetry
        install_cat "quant" autoawq auto-gptq bitsandbytes optimum
        install_cat "data" beautifulsoup4 scrapy crawl4ai duckduckgo_search docling marker browser-use
        install_cat "ui" gradio streamlit chainlit
        ;;
    *) echo "Categories: core inference finetuning agents rag vector-db ml eval speech image safety monitor quant data ui" ;;
esac