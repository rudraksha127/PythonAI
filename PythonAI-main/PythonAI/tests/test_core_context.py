"""
Unit tests for src.core.context — Context Management.
"""

from __future__ import annotations


class TestContextExports:
    """Verify all expected exports exist and work."""

    def test_imports(self) -> None:
        """All expected names are importable."""
        from src.core.context import PermissionResult, ToolProgress, ToolUseContext, make_context

        assert ToolUseContext is not None
        assert ToolProgress is not None
        assert PermissionResult is not None
        assert make_context is not None

    def test_make_context_defaults(self) -> None:
        """make_context() creates a ToolUseContext with default values."""
        from src.core.context import make_context

        ctx = make_context()
        assert ctx.cwd == "."
        assert ctx.verbose is False
        assert ctx.debug is False

    def test_make_context_custom(self) -> None:
        """make_context() accepts overrides for all fields."""
        from src.core.context import make_context

        ctx = make_context(
            cwd="/tmp/test",
            verbose=True,
            debug=True,
        )
        assert ctx.cwd == "/tmp/test"
        assert ctx.verbose is True
        assert ctx.debug is True

    def test_make_context_extra_kwargs(self) -> None:
        """make_context() passes **kwargs through to ToolUseContext."""
        from src.core.context import make_context

        ctx = make_context(cwd=".", verbose=False, debug=False)
        assert ctx.cwd == "."

    def test_make_context_abort_signal(self) -> None:
        """make_context() should accept an abort_signal callable."""
        from src.core.context import make_context

        ctx = make_context(cwd=".", verbose=False, debug=False)
        # abort_signal defaults to a lambda returning False
        assert ctx.abort_signal() is False

    def test_tool_use_context_re_export(self) -> None:
        """ToolUseContext from context module is the same class as from tool."""
        from src.core.context import ToolUseContext as CtxToolUseContext
        from src.core.tool import ToolUseContext as ToolToolUseContext

        assert CtxToolUseContext is ToolToolUseContext

    def test_tool_progress_re_export(self) -> None:
        """ToolProgress from context module is the same class as from tool."""
        from src.core.context import ToolProgress as CtxToolProgress
        from src.core.tool import ToolProgress as ToolToolProgress

        assert CtxToolProgress is ToolToolProgress

    def test_permission_result_re_export(self) -> None:
        """PermissionResult from context module is the same class as from tool."""
        from src.core.context import PermissionResult as CtxPermResult
        from src.core.tool import PermissionResult as ToolPermResult

        assert CtxPermResult is ToolPermResult

    def test_make_context_creates_proper_instance(self) -> None:
        """make_context() returns a proper ToolUseContext instance."""
        from src.core.context import ToolUseContext, make_context

        ctx = make_context()
        assert isinstance(ctx, ToolUseContext)
