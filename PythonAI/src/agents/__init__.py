from .orchestrator import run_orchestrator_agent
from .retrieval import run_retrieval_agent
from .code import run_code_agent
from .docs import run_docs_agent
from .debug import run_debug_agent
from .performance import run_performance_agent
from .teacher import run_teacher_agent

ALL_AGENTS = {
    'orchestrator': run_orchestrator_agent,
    'retrieval': run_retrieval_agent,
    'code': run_code_agent,
    'docs': run_docs_agent,
    'debug': run_debug_agent,
    'performance': run_performance_agent,
    'teacher': run_teacher_agent,
}
