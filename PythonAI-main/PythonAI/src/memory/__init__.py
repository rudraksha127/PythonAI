"""Memory module for ForgeAI — persistent user memory across sessions."""

from src.memory.mem0_wrapper import ForgeAIMemory, create_memory_backend

__all__ = ["ForgeAIMemory", "create_memory_backend"]
