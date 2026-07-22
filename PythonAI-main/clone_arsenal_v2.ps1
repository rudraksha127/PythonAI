$ErrorActionPreference = "Continue"
$BASE = "c:\Users\lucky_vv7fub\OneDrive\Desktop\Today 1 June\arsenal"
if (-not (Test-Path $BASE)) { New-Item -ItemType Directory -Path $BASE -Force | Out-Null }

$success = [System.Collections.ArrayList]@()
$failed = [System.Collections.ArrayList]@()
$skipped = [System.Collections.ArrayList]@()

function Clone-Repo {
    param([string]$Category, [string]$Repo)
    $catDir = Join-Path $BASE $Category
    if (-not (Test-Path $catDir)) { New-Item -ItemType Directory -Path $catDir -Force | Out-Null }
    $repoName = $Repo.Split("/")[-1]
    $targetDir = Join-Path $catDir $repoName
    if (Test-Path $targetDir) {
        Write-Host "  [SKIP] $repoName (exists)" -ForegroundColor Yellow
        [void]$script:skipped.Add("$Category/$repoName")
        return
    }
    Write-Host "  [CLONE] $Repo" -ForegroundColor Cyan
    $proc = Start-Process -FilePath "git" -ArgumentList "clone","--depth","1","https://github.com/$Repo.git",$targetDir -NoNewWindow -Wait -PassThru -RedirectStandardError "NUL" 2>$null
    if ($proc.ExitCode -eq 0) {
        Write-Host "  [OK] $repoName" -ForegroundColor Green
        [void]$script:success.Add("$Category/$repoName")
    } else {
        Write-Host "  [FAIL] $repoName" -ForegroundColor Red
        [void]$script:failed.Add("$Category/$repoName")
    }
}

$totalStart = Get-Date
Write-Host ""
Write-Host "========================================"
Write-Host " FORGEAI ARSENAL - CLONING ALL REPOS"
Write-Host "========================================"
Write-Host ""

# 01. AI Foundations
Write-Host "[01/26] AI Foundations" -ForegroundColor White
$repos01 = @(
    "huggingface/transformers","pytorch/pytorch","langchain-ai/langchain","langchain-ai/langgraph",
    "run-llama/llama_index","stanfordnlp/dspy","deepset-ai/haystack","guidance-ai/guidance",
    "dottxt-ai/outlines","huggingface/peft","huggingface/accelerate","huggingface/trl",
    "UKPLab/sentence-transformers","facebookresearch/faiss","scikit-learn/scikit-learn",
    "dmlc/xgboost","keras-team/keras","google/jax","microsoft/DeepSpeed","NVIDIA/Megatron-LM"
)
foreach ($r in $repos01) { Clone-Repo "01-ai-foundations" $r }

# 02. Local LLM
Write-Host "[02/26] Local LLM" -ForegroundColor White
$repos02 = @(
    "ollama/ollama","ggml-org/llama.cpp","vllm-project/vllm","sgl-project/sglang",
    "lmstudio-ai/lmstudio.js","nomic-ai/gpt4all","janhq/jan","mudler/LocalAI",
    "oobabooga/text-generation-webui","bentoml/OpenLLM","ml-explore/mlx","mlc-ai/mlc-llm",
    "bigscience-workshop/petals","turboderp/exllamav2","ggerganov/whisper.cpp",
    "Mozilla-Ocho/llamafile","LostRuins/koboldcpp","BerriAI/litellm",
    "OpenRouterTeam/openrouter-python","linkedin/Liger-Kernel"
)
foreach ($r in $repos02) { Clone-Repo "02-local-llm" $r }

# 03. Agent Frameworks
Write-Host "[03/26] Agent Frameworks" -ForegroundColor White
$repos03 = @(
    "NousResearch/hermes-agent","Significant-Gravitas/AutoGPT","openclawai/openclaw",
    "crewAIInc/crewAI","microsoft/autogen","huggingface/smolagents",
    "openai/openai-agents-python","TransformerOptimus/SuperAGI","geekan/MetaGPT",
    "reworkd/AgentGPT","OpenInterpreter/open-interpreter","pydantic/pydantic-ai",
    "agno-agi/agno","langgenius/dify","langflow-ai/langflow","FlowiseAI/Flowise",
    "n8n-io/n8n","microsoft/semantic-kernel","microsoft/TaskWeaver",
    "yoheinakajima/babyagi","THUDM/AgentBench","letta-ai/letta","BrainBlend-AI/atomic-agents"
)
foreach ($r in $repos03) { Clone-Repo "03-agent-frameworks" $r }

# 04. RAG Frameworks
Write-Host "[04/26] RAG Frameworks" -ForegroundColor White
$repos04 = @(
    "HKUDS/LightRAG","infiniflow/ragflow","stanford-oval/storm","weaviate/Verba",
    "Mintplex-Labs/anything-llm","truefoundry/cognita","RUC-NLPIR/FlashRAG",
    "NirDiamant/RAG_Techniques","microsoft/graphrag","Cinnamon/kotaemon",
    "chatchat-space/Langchain-Chatchat","QuivrHQ/quivr","zylon-ai/private-gpt",
    "neuml/txtai","pathwaycom/pathway"
)
foreach ($r in $repos04) { Clone-Repo "04-rag-frameworks" $r }

# 05. Fine-tuning
Write-Host "[05/26] Fine-tuning" -ForegroundColor White
$repos05 = @(
    "unslothai/unsloth","hiyouga/LlamaFactory","axolotl-org/axolotl",
    "OpenRLHF/OpenRLHF","xfactlab/orpo","EleutherAI/gpt-neox","NVIDIA/NeMo",
    "Lightning-AI/litgpt","young-geng/EasyLM","tloen/alpaca-lora","artidoro/qlora",
    "argilla-io/distilabel","argilla-io/argilla","huggingface/datatrove",
    "togethercomputer/RedPajama-Data","allenai/dolma","allenai/open-instruct"
)
foreach ($r in $repos05) { Clone-Repo "05-fine-tuning" $r }

# 06. Vector Databases
Write-Host "[06/26] Vector Databases" -ForegroundColor White
$repos06 = @(
    "chroma-core/chroma","qdrant/qdrant","milvus-io/milvus","weaviate/weaviate",
    "lancedb/lancedb","pgvector/pgvector","vespa-engine/vespa","marqo-ai/marqo",
    "activeloopai/deeplake"
)
foreach ($r in $repos06) { Clone-Repo "06-vector-databases" $r }

# 07. Knowledge Graphs
Write-Host "[07/26] Knowledge Graphs" -ForegroundColor White
$repos07 = @(
    "getzep/graphiti","networkx/networkx","neo4j/neo4j-python-driver",
    "pyg-team/pytorch_geometric","dmlc/dgl","kingjulio8238/Memary",
    "whyhow-ai/knowledge-graph-studio","gusye1234/nano-graphrag"
)
foreach ($r in $repos07) { Clone-Repo "07-knowledge-graphs" $r }

# 08. Memory Systems
Write-Host "[08/26] Memory Systems" -ForegroundColor White
$repos08 = @("mem0ai/mem0","plastic-labs/honcho","getzep/zep","topoteretes/cognee")
foreach ($r in $repos08) { Clone-Repo "08-memory-systems" $r }

# 09. Dataset Tools
Write-Host "[09/26] Dataset Tools" -ForegroundColor White
$repos09 = @(
    "huggingface/datasets","HumanSignal/label-studio","cleanlab/cleanlab",
    "doccano/doccano","garage-bAInd/Open-Platypus"
)
foreach ($r in $repos09) { Clone-Repo "09-dataset-tools" $r }

# 10. Evaluation
Write-Host "[10/26] Evaluation" -ForegroundColor White
$repos10 = @(
    "explodinggradients/ragas","confident-ai/deepeval","EleutherAI/lm-evaluation-harness",
    "stanford-crfm/helm","sylinrl/TruthfulQA","google/BIG-bench",
    "princeton-nlp/SWE-bench","open-compass/opencompass"
)
foreach ($r in $repos10) { Clone-Repo "10-evaluation" $r }

# 11. Observability
Write-Host "[11/26] Observability" -ForegroundColor White
$repos11 = @(
    "langfuse/langfuse","Arize-AI/phoenix","MagnivOrg/prompt-layer-library",
    "wandb/wandb","mlflow/mlflow","tensorflow/tensorboard",
    "Helicone/helicone","traceloop/openllmetry"
)
foreach ($r in $repos11) { Clone-Repo "11-observability" $r }

# 12. Web UI
Write-Host "[12/26] Web UI" -ForegroundColor White
$repos12 = @(
    "open-webui/open-webui","gradio-app/gradio","streamlit/streamlit",
    "Chainlit/chainlit","danny-avila/LibreChat","lobehub/lobe-chat",
    "ChatGPTNextWeb/NextChat","SillyTavern/SillyTavern","fmaclen/hollama"
)
foreach ($r in $repos12) { Clone-Repo "12-web-ui" $r }

# 13. API Deployment
Write-Host "[13/26] API Deployment" -ForegroundColor White
$repos13 = @(
    "fastapi/fastapi","bentoml/BentoML","ray-project/ray",
    "triton-inference-server/server","pytorch/serve","SeldonIO/seldon-core",
    "microsoft/onnxruntime","OpenNMT/CTranslate2","modal-labs/modal-client"
)
foreach ($r in $repos13) { Clone-Repo "13-api-deployment" $r }

# 14. Code Dev Tools
Write-Host "[14/26] Code Dev Tools" -ForegroundColor White
$repos14 = @(
    "anthropics/claude-code","Aider-AI/aider","cline/cline","continuedev/continue",
    "e2b-dev/e2b","plandex-ai/plandex","princeton-nlp/SWE-agent",
    "OpenAutoCoder/Agentless","AbanteAI/mentat","sourcegraph/cody","jupyterlab/jupyter-ai"
)
foreach ($r in $repos14) { Clone-Repo "14-code-dev-tools" $r }

# 15. Browser Automation
Write-Host "[15/26] Browser Automation" -ForegroundColor White
$repos15 = @(
    "browser-use/browser-use","microsoft/playwright","SeleniumHQ/selenium",
    "puppeteer/puppeteer","web-arena-x/webarena","Skyvern-AI/skyvern",
    "mendableai/firecrawl","unclecode/crawl4ai","scrapy/scrapy",
    "waylan/beautifulsoup","adbar/trafilatura","codelucas/newspaper"
)
foreach ($r in $repos15) { Clone-Repo "15-browser-automation" $r }

# 16. MCP Servers
Write-Host "[16/26] MCP Servers" -ForegroundColor White
$repos16 = @(
    "modelcontextprotocol/servers","punkpeye/awesome-mcp-servers",
    "modelcontextprotocol/python-sdk","korchasa/awesome-mcp"
)
foreach ($r in $repos16) { Clone-Repo "16-mcp-servers" $r }

# 17. Image Generation
Write-Host "[17/26] Image Generation" -ForegroundColor White
$repos17 = @(
    "AUTOMATIC1111/stable-diffusion-webui","comfyanonymous/ComfyUI",
    "huggingface/diffusers","invoke-ai/InvokeAI","lllyasviel/Fooocus",
    "lllyasviel/ControlNet","tencent-ailab/IP-Adapter","black-forest-labs/flux",
    "InstantX-Team/InstantID"
)
foreach ($r in $repos17) { Clone-Repo "17-image-gen" $r }

# 18. Speech Audio
Write-Host "[18/26] Speech Audio" -ForegroundColor White
$repos18 = @(
    "openai/whisper","SYSTRAN/faster-whisper","suno-ai/bark","coqui-ai/TTS",
    "elevenlabs/elevenlabs-python","speechbrain/speechbrain","espnet/espnet",
    "alphacep/vosk-api","rhasspy/piper","myshell-ai/MeloTTS","SWivid/F5-TTS"
)
foreach ($r in $repos18) { Clone-Repo "18-speech-audio" $r }

# 19. Video Generation
Write-Host "[19/26] Video Generation" -ForegroundColor White
$repos19 = @(
    "guoyww/AnimateDiff","Stability-AI/generative-models","TMElyralab/MusePose",
    "THUDM/CogVideo","hpcaitech/Open-Sora","Lightricks/LTX-Video","Wan-Video/Wan2.1"
)
foreach ($r in $repos19) { Clone-Repo "19-video-gen" $r }

# 20. Multimodal
Write-Host "[20/26] Multimodal" -ForegroundColor White
$repos20 = @(
    "haotian-liu/LLaVA","Vision-CAIR/MiniGPT-4","OpenGVLab/InternVL",
    "QwenLM/Qwen-VL","OpenBMB/MiniCPM-o","THUDM/CogVLM",
    "salesforce/LAVIS","mlfoundations/open_flamingo","baaivision/Emu3"
)
foreach ($r in $repos20) { Clone-Repo "20-multimodal" $r }

# 21. Safety
Write-Host "[21/26] Safety" -ForegroundColor White
$repos21 = @(
    "guardrails-ai/guardrails","NVIDIA/NeMo-Guardrails","protectai/llm-guard",
    "protectai/rebuff","deadbits/vigil-llm"
)
foreach ($r in $repos21) { Clone-Repo "21-safety" $r }

# 22. Search
Write-Host "[22/26] Search" -ForegroundColor White
$repos22 = @(
    "searxng/searxng","spider-rs/spider","assafelovic/gpt-researcher",
    "deedy5/duckduckgo_search"
)
foreach ($r in $repos22) { Clone-Repo "22-search" $r }

# 23. MLOps
Write-Host "[23/26] MLOps" -ForegroundColor White
$repos23 = @(
    "iterative/dvc","zenml-io/zenml","Netflix/metaflow","kubeflow/kubeflow",
    "apache/airflow","PrefectHQ/prefect","docker/compose",
    "supabase/supabase","redis/redis","postgres/postgres"
)
foreach ($r in $repos23) { Clone-Repo "23-mlops" $r }

# 24. Robotics
Write-Host "[24/26] Robotics" -ForegroundColor White
$repos24 = @(
    "huggingface/lerobot","ros2/ros2","isaac-sim/IsaacLab",
    "openvla/openvla","octo-models/octo"
)
foreach ($r in $repos24) { Clone-Repo "24-robotics" $r }

# 25. Learning
Write-Host "[25/26] Learning Resources" -ForegroundColor White
$repos25 = @(
    "codecrafters-io/build-your-own-x","kamranahmedse/developer-roadmap",
    "TheAlgorithms/Python","EbookFoundation/free-programming-books",
    "donnemartin/system-design-primer","mlabonne/llm-course",
    "vinta/awesome-python","eriklindernoren/ML-From-Scratch",
    "janishar/mit-deep-learning-book-pdf","HandsOnLLM/Hands-On-Large-Language-Models"
)
foreach ($r in $repos25) { Clone-Repo "25-learning" $r }

# 26. Awesome Lists
Write-Host "[26/26] Awesome Meta-Lists" -ForegroundColor White
$repos26 = @(
    "caramaschiHG/awesome-ai-agents-2026","tensorchord/Awesome-LLMOps",
    "ethicals7s/awesome-local-ai","Hannibal046/Awesome-LLM",
    "Yigtwxx/Awesome-RAG-Production","kyrolabs/awesome-agents",
    "xlite-dev/Awesome-LLM-Inference","PavelGrigoryevDS/awesome-data-analysis",
    "jim-schwoebel/awesome_ai_agents","ARUNAGIRINATHAN-K/awesome-ai-agents-2026"
)
foreach ($r in $repos26) { Clone-Repo "26-awesome-lists" $r }

# Final Report
$elapsed = (Get-Date) - $totalStart
Write-Host ""
Write-Host "========================================"
Write-Host " CLONE COMPLETE!"
Write-Host "========================================"
Write-Host " SUCCESS: $($success.Count)" -ForegroundColor Green
Write-Host " SKIPPED: $($skipped.Count)" -ForegroundColor Yellow
Write-Host " FAILED:  $($failed.Count)" -ForegroundColor Red
Write-Host " TIME:    $([math]::Round($elapsed.TotalMinutes, 1)) minutes"
Write-Host "========================================"

if ($failed.Count -gt 0) {
    Write-Host "FAILED REPOS:" -ForegroundColor Red
    $failed | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

# Save report to file
$reportLines = @("# Arsenal Clone Report")
$reportLines += "Date: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
$reportLines += "Duration: $([math]::Round($elapsed.TotalMinutes, 1)) minutes"
$reportLines += ""
$reportLines += "## Success ($($success.Count))"
foreach ($s in $success) { $reportLines += "- $s" }
$reportLines += ""
$reportLines += "## Skipped ($($skipped.Count))"
foreach ($s in $skipped) { $reportLines += "- $s" }
$reportLines += ""
$reportLines += "## Failed ($($failed.Count))"
foreach ($s in $failed) { $reportLines += "- $s" }

$reportLines | Out-File -FilePath (Join-Path $BASE "CLONE_REPORT.md") -Encoding utf8
Write-Host "Report saved to: arsenal\CLONE_REPORT.md"
