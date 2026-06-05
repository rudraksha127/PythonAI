"""
Agent Memory Module using ChromaDB.
Provides persistent context across sessions for Swarm Agents.
"""
import os
from loguru import logger

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    chromadb = None

class AgentMemory:
    def __init__(self, db_path: str = "python_brain_godmode/memory_db"):
        self.db_path = db_path
        if not chromadb:
            logger.warning("chromadb not installed, agent memory will be disabled")
            self.collection = None
            return
            
        # Ensure dir exists
        os.makedirs(db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=db_path)
        
        # We create a collection for conversational memory
        self.collection = self.client.get_or_create_collection(
            name="swarm_memory",
            metadata={"hnsw:space": "cosine"}
        )

    def add_memory(self, session_id: str, role: str, text: str):
        """Add a turn of conversation to the memory."""
        if not self.collection:
            return
            
        import uuid
        doc_id = f"{session_id}_{uuid.uuid4().hex[:8]}"
        
        self.collection.add(
            documents=[text],
            metadatas=[{"session_id": session_id, "role": role}],
            ids=[doc_id]
        )

    def search_memory(self, session_id: str, query: str, n_results: int = 3) -> list:
        """Find relevant past context for a given session and query."""
        if not self.collection:
            return []
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                where={"session_id": session_id}
            )
            
            memories = []
            if results and results["documents"] and results["documents"][0]:
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    role = meta.get("role", "unknown")
                    memories.append(f"{role.capitalize()}: {doc}")
            return memories
        except Exception as e:
            logger.error(f"Error querying memory: {e}")
            return []
