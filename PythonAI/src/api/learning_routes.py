from fastapi import APIRouter
from typing import Any, Dict
import time

from src.learning.conv_learner import ConversationLearner
from src.learning.error_patterns import _get_db as get_error_db
from src.learning.self_eval import SelfEvaluator
from src.learning.doc_watcher import DocWatcher

router = APIRouter(prefix="/learning", tags=["Learning & Statistics"])

@router.get("/stats")
def get_learning_stats() -> Dict[str, Any]:
    """
    Retrieve comprehensive statistics from all autonomous learning modules.
    Useful for populating the Learning Dashboard.
    """
    start_time = time.time()
    
    # 1. Error Patterns
    error_db = get_error_db()
    error_stats = error_db.get_stats()
    
    # 2. Conversation Learner
    try:
        conv_learner = ConversationLearner()
        conv_stats = conv_learner.get_stats()
    except Exception as e:
        conv_stats = {"error": str(e)}

    # 3. Self Evaluator
    try:
        evaluator = SelfEvaluator()
        eval_trend = evaluator.get_trend(limit=5)
    except Exception as e:
        eval_trend = [{"error": str(e)}]
        
    # 4. Doc Watcher
    try:
        doc_watcher = DocWatcher()
        doc_state = doc_watcher.get_state()
    except Exception as e:
        doc_state = {"error": str(e)}

    elapsed_ms = round((time.time() - start_time) * 1000, 2)

    return {
        "status": "success",
        "fetch_time_ms": elapsed_ms,
        "modules": {
            "error_patterns": error_stats,
            "conversations": conv_stats,
            "self_evaluation_trend": eval_trend,
            "doc_watcher": doc_state
        }
    }

@router.post("/trigger/sync-so")
def trigger_sync_so() -> Dict[str, Any]:
    """Manually trigger a StackOverflow sync job via the API."""
    from src.learning.so_sync import sync_stackoverflow
    stats = sync_stackoverflow(pages=1)
    return {"status": "success", "stats": stats}

@router.post("/trigger/eval")
def trigger_eval() -> Dict[str, Any]:
    """Manually trigger a RAG self-evaluation job via the API."""
    from src.learning.self_eval import run_self_evaluation
    stats = run_self_evaluation(sample_size=10)
    return {"status": "success", "report": stats}
