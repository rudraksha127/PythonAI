"""ForgeAI's extensibility kernel.

The package intentionally contains only framework-agnostic domain and
application code at its centre. Existing PythonAI features are integrated via
adapters so the platform can evolve without coupling new capabilities to the
legacy runtime.
"""

from .runtime.container import BrainContainer

__all__ = ["BrainContainer"]
