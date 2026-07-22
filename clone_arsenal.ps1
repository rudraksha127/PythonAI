# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# ForgeAI Arsenal â€” Clone ALL 262 GitHub Tools
# Source: Readme/git.txt
# Strategy: Shallow clone (--depth 1) to save disk + bandwidth
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

$ErrorActionPreference = "Continue"
$BASE = "c:\Users\lucky_vv7fub\OneDrive\Desktop\Today 1 June\arsenal"

# Create base directory
if (-not (Test-Path $BASE)) { New-Item -ItemType Directory -Path $BASE -Force | Out-Null }

# Track results
$success = @()
$failed = @()
$skipped = @()

function Clone-Repo {
    param([string]$Category, [string]$Repo)
    $catDir = Join-Path $BASE $Category
    if (-not (Test-Path $catDir)) { New-Item -ItemType Directory -Path $catDir -Force | Out-Null }
    
    $repoName = $Repo.Split("/")[-1]
    $targetDir = Join-Path $catDir $repoName
    
    if (Test-Path $targetDir) {
        Write-Host "  [SKIP] $repoName (already exists)" -ForegroundColor Yellow
        $script:skipped += "$Category/$repoName"
        return
    }
    
    Write-Host "  [CLONE] $Repo -> $Category/$repoName" -ForegroundColor Cyan
    try {
        git clone --depth 1 "https://github.com/$Repo.git" $targetDir 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  [OK] $repoName" -ForegroundColor Green
            $script:success += "$Category/$repoName"
        } else {
            Write-Host "  [FAIL] $repoName (exit code $LASTEXITCODE)" -ForegroundColor Red
            $script:failed += "$Category/$repoName"
        }
    } catch {
        Write-Host "  [FAIL] $repoName - $_" -ForegroundColor Red
        $script:failed += "$Category/$repoName"
    }
}

$totalStart = Get-Date
Write-Host "`n========================================" -ForegroundColor Magenta
Write-Host " FORGEAI ARSENAL â€” CLONING 262 REPOS" -ForegroundColor Magenta
Write-Host "========================================`n" -ForegroundColor Magenta

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 01. AI FOUNDATIONS & CORE FRAMEWORKS (20)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[01/26] AI Foundations ``& Core Frameworks" -ForegroundColor White
Clone-Repo "01-ai-foundations" "huggingface/transformers"
Clone-Repo "01-ai-foundations" "pytorch/pytorch"
Clone-Repo "01-ai-foundations" "langchain-ai/langchain"
Clone-Repo "01-ai-foundations" "langchain-ai/langgraph"
Clone-Repo "01-ai-foundations" "run-llama/llama_index"
Clone-Repo "01-ai-foundations" "stanfordnlp/dspy"
Clone-Repo "01-ai-foundations" "deepset-ai/haystack"
Clone-Repo "01-ai-foundations" "guidance-ai/guidance"
Clone-Repo "01-ai-foundations" "dottxt-ai/outlines"
Clone-Repo "01-ai-foundations" "huggingface/peft"
Clone-Repo "01-ai-foundations" "huggingface/accelerate"
Clone-Repo "01-ai-foundations" "huggingface/trl"
Clone-Repo "01-ai-foundations" "UKPLab/sentence-transformers"
Clone-Repo "01-ai-foundations" "facebookresearch/faiss"
Clone-Repo "01-ai-foundations" "scikit-learn/scikit-learn"
Clone-Repo "01-ai-foundations" "dmlc/xgboost"
Clone-Repo "01-ai-foundations" "keras-team/keras"
Clone-Repo "01-ai-foundations" "google/jax"
Clone-Repo "01-ai-foundations" "microsoft/DeepSpeed"
Clone-Repo "01-ai-foundations" "NVIDIA/Megatron-LM"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 02. LOCAL LLM & INFERENCE ENGINES (20)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[02/26] Local LLM ``& Inference Engines" -ForegroundColor White
Clone-Repo "02-local-llm" "ollama/ollama"
Clone-Repo "02-local-llm" "ggml-org/llama.cpp"
Clone-Repo "02-local-llm" "vllm-project/vllm"
Clone-Repo "02-local-llm" "sgl-project/sglang"
Clone-Repo "02-local-llm" "lmstudio-ai/lmstudio.js"
Clone-Repo "02-local-llm" "nomic-ai/gpt4all"
Clone-Repo "02-local-llm" "janhq/jan"
Clone-Repo "02-local-llm" "mudler/LocalAI"
Clone-Repo "02-local-llm" "oobabooga/text-generation-webui"
Clone-Repo "02-local-llm" "bentoml/OpenLLM"
Clone-Repo "02-local-llm" "ml-explore/mlx"
Clone-Repo "02-local-llm" "mlc-ai/mlc-llm"
Clone-Repo "02-local-llm" "bigscience-workshop/petals"
Clone-Repo "02-local-llm" "turboderp/exllamav2"
Clone-Repo "02-local-llm" "ggerganov/whisper.cpp"
Clone-Repo "02-local-llm" "Mozilla-Ocho/llamafile"
Clone-Repo "02-local-llm" "LostRuins/koboldcpp"
Clone-Repo "02-local-llm" "BerriAI/litellm"
Clone-Repo "02-local-llm" "OpenRouterTeam/openrouter-python"
Clone-Repo "02-local-llm" "linkedin/Liger-Kernel"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 03. AGENT FRAMEWORKS (25)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[03/26] Agent Frameworks" -ForegroundColor White
Clone-Repo "03-agent-frameworks" "NousResearch/hermes-agent"
Clone-Repo "03-agent-frameworks" "Significant-Gravitas/AutoGPT"
Clone-Repo "03-agent-frameworks" "openclawai/openclaw"
Clone-Repo "03-agent-frameworks" "crewAIInc/crewAI"
Clone-Repo "03-agent-frameworks" "microsoft/autogen"
Clone-Repo "03-agent-frameworks" "huggingface/smolagents"
Clone-Repo "03-agent-frameworks" "openai/openai-agents-python"
Clone-Repo "03-agent-frameworks" "TransformerOptimus/SuperAGI"
Clone-Repo "03-agent-frameworks" "geekan/MetaGPT"
Clone-Repo "03-agent-frameworks" "reworkd/AgentGPT"
Clone-Repo "03-agent-frameworks" "OpenInterpreter/open-interpreter"
Clone-Repo "03-agent-frameworks" "pydantic/pydantic-ai"
Clone-Repo "03-agent-frameworks" "agno-agi/agno"
Clone-Repo "03-agent-frameworks" "langgenius/dify"
Clone-Repo "03-agent-frameworks" "langflow-ai/langflow"
Clone-Repo "03-agent-frameworks" "FlowiseAI/Flowise"
Clone-Repo "03-agent-frameworks" "n8n-io/n8n"
Clone-Repo "03-agent-frameworks" "microsoft/semantic-kernel"
Clone-Repo "03-agent-frameworks" "microsoft/TaskWeaver"
Clone-Repo "03-agent-frameworks" "yoheinakajima/babyagi"
Clone-Repo "03-agent-frameworks" "THUDM/AgentBench"
Clone-Repo "03-agent-frameworks" "letta-ai/letta"
Clone-Repo "03-agent-frameworks" "BrainBlend-AI/atomic-agents"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 04. RAG FRAMEWORKS (15)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[04/26] RAG Frameworks" -ForegroundColor White
Clone-Repo "04-rag-frameworks" "HKUDS/LightRAG"
Clone-Repo "04-rag-frameworks" "infiniflow/ragflow"
Clone-Repo "04-rag-frameworks" "stanford-oval/storm"
Clone-Repo "04-rag-frameworks" "weaviate/Verba"
Clone-Repo "04-rag-frameworks" "Mintplex-Labs/anything-llm"
Clone-Repo "04-rag-frameworks" "truefoundry/cognita"
Clone-Repo "04-rag-frameworks" "RUC-NLPIR/FlashRAG"
Clone-Repo "04-rag-frameworks" "NirDiamant/RAG_Techniques"
Clone-Repo "04-rag-frameworks" "microsoft/graphrag"
Clone-Repo "04-rag-frameworks" "Cinnamon/kotaemon"
Clone-Repo "04-rag-frameworks" "chatchat-space/Langchain-Chatchat"
Clone-Repo "04-rag-frameworks" "QuivrHQ/quivr"
Clone-Repo "04-rag-frameworks" "zylon-ai/private-gpt"
Clone-Repo "04-rag-frameworks" "neuml/txtai"
Clone-Repo "04-rag-frameworks" "pathwaycom/pathway"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 05. FINE-TUNING & TRAINING (18)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[05/26] Fine-tuning ``& Training" -ForegroundColor White
Clone-Repo "05-fine-tuning" "unslothai/unsloth"
Clone-Repo "05-fine-tuning" "hiyouga/LlamaFactory"
Clone-Repo "05-fine-tuning" "axolotl-org/axolotl"
Clone-Repo "05-fine-tuning" "OpenRLHF/OpenRLHF"
Clone-Repo "05-fine-tuning" "xfactlab/orpo"
Clone-Repo "05-fine-tuning" "EleutherAI/gpt-neox"
Clone-Repo "05-fine-tuning" "NVIDIA/NeMo"
Clone-Repo "05-fine-tuning" "Lightning-AI/litgpt"
Clone-Repo "05-fine-tuning" "young-geng/EasyLM"
Clone-Repo "05-fine-tuning" "tloen/alpaca-lora"
Clone-Repo "05-fine-tuning" "artidoro/qlora"
Clone-Repo "05-fine-tuning" "argilla-io/distilabel"
Clone-Repo "05-fine-tuning" "argilla-io/argilla"
Clone-Repo "05-fine-tuning" "huggingface/datatrove"
Clone-Repo "05-fine-tuning" "togethercomputer/RedPajama-Data"
Clone-Repo "05-fine-tuning" "allenai/dolma"
Clone-Repo "05-fine-tuning" "allenai/open-instruct"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 06. VECTOR DATABASES (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[06/26] Vector Databases" -ForegroundColor White
Clone-Repo "06-vector-databases" "chroma-core/chroma"
Clone-Repo "06-vector-databases" "qdrant/qdrant"
Clone-Repo "06-vector-databases" "milvus-io/milvus"
Clone-Repo "06-vector-databases" "weaviate/weaviate"
Clone-Repo "06-vector-databases" "lancedb/lancedb"
Clone-Repo "06-vector-databases" "pgvector/pgvector"
Clone-Repo "06-vector-databases" "vespa-engine/vespa"
Clone-Repo "06-vector-databases" "marqo-ai/marqo"
Clone-Repo "06-vector-databases" "activeloopai/deeplake"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 07. KNOWLEDGE GRAPHS (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[07/26] Knowledge Graphs" -ForegroundColor White
Clone-Repo "07-knowledge-graphs" "getzep/graphiti"
Clone-Repo "07-knowledge-graphs" "networkx/networkx"
Clone-Repo "07-knowledge-graphs" "neo4j/neo4j-python-driver"
Clone-Repo "07-knowledge-graphs" "pyg-team/pytorch_geometric"
Clone-Repo "07-knowledge-graphs" "dmlc/dgl"
Clone-Repo "07-knowledge-graphs" "kingjulio8238/Memary"
Clone-Repo "07-knowledge-graphs" "whyhow-ai/knowledge-graph-studio"
Clone-Repo "07-knowledge-graphs" "gusye1234/nano-graphrag"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 08. MEMORY SYSTEMS (6)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[08/26] Memory Systems" -ForegroundColor White
Clone-Repo "08-memory-systems" "mem0ai/mem0"
Clone-Repo "08-memory-systems" "plastic-labs/honcho"
Clone-Repo "08-memory-systems" "getzep/zep"
Clone-Repo "08-memory-systems" "topoteretes/cognee"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 09. DATASET TOOLS (11)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[09/26] Dataset Tools" -ForegroundColor White
Clone-Repo "09-dataset-tools" "huggingface/datasets"
Clone-Repo "09-dataset-tools" "HumanSignal/label-studio"
Clone-Repo "09-dataset-tools" "cleanlab/cleanlab"
Clone-Repo "09-dataset-tools" "doccano/doccano"
Clone-Repo "09-dataset-tools" "garage-bAInd/Open-Platypus"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 10. EVALUATION & BENCHMARKS (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[10/26] Evaluation ``& Benchmarks" -ForegroundColor White
Clone-Repo "10-evaluation" "explodinggradients/ragas"
Clone-Repo "10-evaluation" "confident-ai/deepeval"
Clone-Repo "10-evaluation" "EleutherAI/lm-evaluation-harness"
Clone-Repo "10-evaluation" "stanford-crfm/helm"
Clone-Repo "10-evaluation" "sylinrl/TruthfulQA"
Clone-Repo "10-evaluation" "google/BIG-bench"
Clone-Repo "10-evaluation" "princeton-nlp/SWE-bench"
Clone-Repo "10-evaluation" "open-compass/opencompass"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 11. OBSERVABILITY & MONITORING (8)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[11/26] Observability ``& Monitoring" -ForegroundColor White
Clone-Repo "11-observability" "langfuse/langfuse"
Clone-Repo "11-observability" "Arize-AI/phoenix"
Clone-Repo "11-observability" "MagnivOrg/prompt-layer-library"
Clone-Repo "11-observability" "wandb/wandb"
Clone-Repo "11-observability" "mlflow/mlflow"
Clone-Repo "11-observability" "tensorflow/tensorboard"
Clone-Repo "11-observability" "Helicone/helicone"
Clone-Repo "11-observability" "traceloop/openllmetry"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 12. WEB UI & CHAT INTERFACES (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[12/26] Web UI ``& Chat Interfaces" -ForegroundColor White
Clone-Repo "12-web-ui" "open-webui/open-webui"
Clone-Repo "12-web-ui" "gradio-app/gradio"
Clone-Repo "12-web-ui" "streamlit/streamlit"
Clone-Repo "12-web-ui" "Chainlit/chainlit"
Clone-Repo "12-web-ui" "danny-avila/LibreChat"
Clone-Repo "12-web-ui" "lobehub/lobe-chat"
Clone-Repo "12-web-ui" "ChatGPTNextWeb/NextChat"
Clone-Repo "12-web-ui" "SillyTavern/SillyTavern"
Clone-Repo "12-web-ui" "fmaclen/hollama"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 13. API & DEPLOYMENT (9)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[13/26] API ``& Deployment" -ForegroundColor White
Clone-Repo "13-api-deployment" "fastapi/fastapi"
Clone-Repo "13-api-deployment" "bentoml/BentoML"
Clone-Repo "13-api-deployment" "ray-project/ray"
Clone-Repo "13-api-deployment" "triton-inference-server/server"
Clone-Repo "13-api-deployment" "pytorch/serve"
Clone-Repo "13-api-deployment" "SeldonIO/seldon-core"
Clone-Repo "13-api-deployment" "microsoft/onnxruntime"
Clone-Repo "13-api-deployment" "OpenNMT/CTranslate2"
Clone-Repo "13-api-deployment" "modal-labs/modal-client"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 14. CODE EXECUTION & DEV TOOLS (13)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[14/26] Code Execution ``& Dev Tools" -ForegroundColor White
Clone-Repo "14-code-dev-tools" "anthropics/claude-code"
Clone-Repo "14-code-dev-tools" "Aider-AI/aider"
Clone-Repo "14-code-dev-tools" "cline/cline"
Clone-Repo "14-code-dev-tools" "continuedev/continue"
Clone-Repo "14-code-dev-tools" "e2b-dev/e2b"
Clone-Repo "14-code-dev-tools" "plandex-ai/plandex"
Clone-Repo "14-code-dev-tools" "princeton-nlp/SWE-agent"
Clone-Repo "14-code-dev-tools" "OpenAutoCoder/Agentless"
Clone-Repo "14-code-dev-tools" "AbanteAI/mentat"
Clone-Repo "14-code-dev-tools" "sourcegraph/cody"
Clone-Repo "14-code-dev-tools" "jupyterlab/jupyter-ai"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 15. BROWSER & WEB AUTOMATION (12)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[15/26] Browser ``& Web Automation" -ForegroundColor White
Clone-Repo "15-browser-automation" "browser-use/browser-use"
Clone-Repo "15-browser-automation" "microsoft/playwright"
Clone-Repo "15-browser-automation" "SeleniumHQ/selenium"
Clone-Repo "15-browser-automation" "puppeteer/puppeteer"
Clone-Repo "15-browser-automation" "web-arena-x/webarena"
Clone-Repo "15-browser-automation" "Skyvern-AI/skyvern"
Clone-Repo "15-browser-automation" "mendableai/firecrawl"
Clone-Repo "15-browser-automation" "unclecode/crawl4ai"
Clone-Repo "15-browser-automation" "scrapy/scrapy"
Clone-Repo "15-browser-automation" "waylan/beautifulsoup"
Clone-Repo "15-browser-automation" "adbar/trafilatura"
Clone-Repo "15-browser-automation" "codelucas/newspaper"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 16. MCP SERVERS & PROTOCOL (5)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[16/26] MCP Servers ``& Protocol" -ForegroundColor White
Clone-Repo "16-mcp-servers" "modelcontextprotocol/servers"
Clone-Repo "16-mcp-servers" "punkpeye/awesome-mcp-servers"
Clone-Repo "16-mcp-servers" "modelcontextprotocol/python-sdk"
Clone-Repo "16-mcp-servers" "korchasa/awesome-mcp"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 17. IMAGE GENERATION (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[17/26] Image Generation" -ForegroundColor White
Clone-Repo "17-image-gen" "AUTOMATIC1111/stable-diffusion-webui"
Clone-Repo "17-image-gen" "comfyanonymous/ComfyUI"
Clone-Repo "17-image-gen" "huggingface/diffusers"
Clone-Repo "17-image-gen" "invoke-ai/InvokeAI"
Clone-Repo "17-image-gen" "lllyasviel/Fooocus"
Clone-Repo "17-image-gen" "lllyasviel/ControlNet"
Clone-Repo "17-image-gen" "tencent-ailab/IP-Adapter"
Clone-Repo "17-image-gen" "black-forest-labs/flux"
Clone-Repo "17-image-gen" "InstantX-Team/InstantID"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 18. SPEECH & AUDIO (12)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[18/26] Speech ``& Audio" -ForegroundColor White
Clone-Repo "18-speech-audio" "openai/whisper"
Clone-Repo "18-speech-audio" "SYSTRAN/faster-whisper"
Clone-Repo "18-speech-audio" "suno-ai/bark"
Clone-Repo "18-speech-audio" "coqui-ai/TTS"
Clone-Repo "18-speech-audio" "elevenlabs/elevenlabs-python"
Clone-Repo "18-speech-audio" "speechbrain/speechbrain"
Clone-Repo "18-speech-audio" "espnet/espnet"
Clone-Repo "18-speech-audio" "alphacep/vosk-api"
Clone-Repo "18-speech-audio" "rhasspy/piper"
Clone-Repo "18-speech-audio" "myshell-ai/MeloTTS"
Clone-Repo "18-speech-audio" "SWivid/F5-TTS"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 19. VIDEO GENERATION (7)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[19/26] Video Generation" -ForegroundColor White
Clone-Repo "19-video-gen" "guoyww/AnimateDiff"
Clone-Repo "19-video-gen" "Stability-AI/generative-models"
Clone-Repo "19-video-gen" "TMElyralab/MusePose"
Clone-Repo "19-video-gen" "THUDM/CogVideo"
Clone-Repo "19-video-gen" "hpcaitech/Open-Sora"
Clone-Repo "19-video-gen" "Lightricks/LTX-Video"
Clone-Repo "19-video-gen" "Wan-Video/Wan2.1"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 20. MULTIMODAL MODELS (10)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[20/26] Multimodal Models" -ForegroundColor White
Clone-Repo "20-multimodal" "haotian-liu/LLaVA"
Clone-Repo "20-multimodal" "Vision-CAIR/MiniGPT-4"
Clone-Repo "20-multimodal" "OpenGVLab/InternVL"
Clone-Repo "20-multimodal" "QwenLM/Qwen-VL"
Clone-Repo "20-multimodal" "OpenBMB/MiniCPM-o"
Clone-Repo "20-multimodal" "THUDM/CogVLM"
Clone-Repo "20-multimodal" "salesforce/LAVIS"
Clone-Repo "20-multimodal" "mlfoundations/open_flamingo"
Clone-Repo "20-multimodal" "baaivision/Emu3"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 21. SAFETY & GUARDRAILS (6)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[21/26] Safety ``& Guardrails" -ForegroundColor White
Clone-Repo "21-safety" "guardrails-ai/guardrails"
Clone-Repo "21-safety" "NVIDIA/NeMo-Guardrails"
Clone-Repo "21-safety" "protectai/llm-guard"
Clone-Repo "21-safety" "protectai/rebuff"
Clone-Repo "21-safety" "deadbits/vigil-llm"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 22. SEARCH & DATA COLLECTION (8)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[22/26] Search ``& Data Collection" -ForegroundColor White
Clone-Repo "22-search" "searxng/searxng"
Clone-Repo "22-search" "spider-rs/spider"
Clone-Repo "22-search" "assafelovic/gpt-researcher"
Clone-Repo "22-search" "deedy5/duckduckgo_search"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 23. MLOps & INFRASTRUCTURE (12)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[23/26] MLOps ``& Infrastructure" -ForegroundColor White
Clone-Repo "23-mlops" "iterative/dvc"
Clone-Repo "23-mlops" "zenml-io/zenml"
Clone-Repo "23-mlops" "Netflix/metaflow"
Clone-Repo "23-mlops" "kubeflow/kubeflow"
Clone-Repo "23-mlops" "apache/airflow"
Clone-Repo "23-mlops" "PrefectHQ/prefect"
Clone-Repo "23-mlops" "docker/compose"
Clone-Repo "23-mlops" "supabase/supabase"
Clone-Repo "23-mlops" "redis/redis"
Clone-Repo "23-mlops" "postgres/postgres"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 24. ROBOTICS & EMBODIED AI (5)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[24/26] Robotics ``& Embodied AI" -ForegroundColor White
Clone-Repo "24-robotics" "huggingface/lerobot"
Clone-Repo "24-robotics" "ros2/ros2"
Clone-Repo "24-robotics" "isaac-sim/IsaacLab"
Clone-Repo "24-robotics" "openvla/openvla"
Clone-Repo "24-robotics" "octo-models/octo"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 25. LEARNING RESOURCES & ROADMAPS (11)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[25/26] Learning Resources ``& Roadmaps" -ForegroundColor White
Clone-Repo "25-learning" "codecrafters-io/build-your-own-x"
Clone-Repo "25-learning" "kamranahmedse/developer-roadmap"
Clone-Repo "25-learning" "TheAlgorithms/Python"
Clone-Repo "25-learning" "EbookFoundation/free-programming-books"
Clone-Repo "25-learning" "donnemartin/system-design-primer"
Clone-Repo "25-learning" "mlabonne/llm-course"
Clone-Repo "25-learning" "vinta/awesome-python"
Clone-Repo "25-learning" "eriklindernoren/ML-From-Scratch"
Clone-Repo "25-learning" "janishar/mit-deep-learning-book-pdf"
Clone-Repo "25-learning" "HandsOnLLM/Hands-On-Large-Language-Models"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 26. AWESOME META-LISTS (11)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
Write-Host "`n[26/26] Awesome Meta-Lists" -ForegroundColor White
Clone-Repo "26-awesome-lists" "caramaschiHG/awesome-ai-agents-2026"
Clone-Repo "26-awesome-lists" "tensorchord/Awesome-LLMOps"
Clone-Repo "26-awesome-lists" "ethicals7s/awesome-local-ai"
Clone-Repo "26-awesome-lists" "Hannibal046/Awesome-LLM"
Clone-Repo "26-awesome-lists" "Yigtwxx/Awesome-RAG-Production"
Clone-Repo "26-awesome-lists" "kyrolabs/awesome-agents"
Clone-Repo "26-awesome-lists" "xlite-dev/Awesome-LLM-Inference"
Clone-Repo "26-awesome-lists" "PavelGrigoryevDS/awesome-data-analysis"
Clone-Repo "26-awesome-lists" "jim-schwoebel/awesome_ai_agents"
Clone-Repo "26-awesome-lists" "ARUNAGIRINATHAN-K/awesome-ai-agents-2026"

# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# FINAL REPORT
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
$elapsed = (Get-Date) - $totalStart
Write-Host "`n========================================" -ForegroundColor Magenta
Write-Host " CLONE COMPLETE!" -ForegroundColor Magenta
Write-Host "========================================" -ForegroundColor Magenta
Write-Host " SUCCESS: $($success.Count)" -ForegroundColor Green
Write-Host " SKIPPED: $($skipped.Count)" -ForegroundColor Yellow
Write-Host " FAILED:  $($failed.Count)" -ForegroundColor Red
Write-Host " TIME:    $([math]::Round($elapsed.TotalMinutes, 1)) minutes" -ForegroundColor Cyan
Write-Host "========================================`n" -ForegroundColor Magenta

if ($failed.Count -gt 0) {
    Write-Host "FAILED REPOS:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

# Save report
$report = @"
# Arsenal Clone Report
Date: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
Duration: $([math]::Round($elapsed.TotalMinutes, 1)) minutes

## Success ($($success.Count))
$($success | ForEach-Object { "- $_" } | Out-String)

## Skipped ($($skipped.Count))
$($skipped | ForEach-Object { "- $_" } | Out-String)

## Failed ($($failed.Count))
$($failed | ForEach-Object { "- $_" } | Out-String)
"@

$report | Out-File -FilePath (Join-Path $BASE "CLONE_REPORT.md") -Encoding utf8
Write-Host "Report saved to: arsenal\CLONE_REPORT.md" -ForegroundColor Cyan

