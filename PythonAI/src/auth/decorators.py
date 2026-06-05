from __future__ import annotations

import functools
import sys
from typing import Any, Callable

from src.auth.config import AuthConfig


# ASCII-safe symbols (Windows terminal compatible)
_LOCK = "[!]"
_LINE = "-" * 40


def requires_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator that checks if user is authenticated before running the command.

    Usage:
        @requires_auth
        def my_protected_command(args: Namespace) -> int:
            ...

    Supports --no-auth flag to skip auth check.
    """

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        # Check if --no-auth was passed (accessible via args[0] which is Namespace)
        if args and hasattr(args[0], "no_auth") and args[0].no_auth:
            return func(*args, **kwargs)

        config = AuthConfig()
        if not config.is_logged_in():
            print(f"\n{_LOCK} Authentication Required")
            print(_LINE)
            print("This command requires you to be logged in.")
            print("Run:  python -m src.cli login")
            print("Or pass --no-auth to skip authentication for local use.\n")
            return 1

        return func(*args, **kwargs)

    return wrapper
