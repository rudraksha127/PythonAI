from __future__ import annotations

import argparse

from src.auth import check_auth, interactive_login, logout
from src.auth.config import AuthConfig


def login_cmd(args: argparse.Namespace) -> int:
    """Handle login, logout, and check subcommands."""
    config = AuthConfig()

    if args.action == "check":
        status = check_auth(config)
        if status["authenticated"]:
            print(f"[OK] Logged in as: {status['username']}")
            print(f"   Since: {status['logged_in_at']}")
        else:
            print("[FAIL] Not logged in.")
            print("Run:  python -m src.cli login")
        return 0

    if args.action == "logout":
        result = logout(config)
        print(f"[Bye] {result['message']}")
        return 0

    if args.action == "login":
        result = interactive_login(config)
        if result["success"]:
            print(f"[OK] Logged in as: {result['username']}")
        else:
            print(f"[FAIL] Login failed: {result['error']}")
            return 1
        return 0

    return 1


def apikeys_cmd(args: argparse.Namespace) -> int:
    """Manage API keys for dataset generation."""
    from src.data.apikeys import (
        ALL_PROVIDERS,
        PROVIDER_LABELS,
        active_providers,
        delete_key,
        export_dotenv,
        list_keys,
        set_key,
    )

    if args.action == "list":
        keys = list_keys(masked=not args.show_keys)
        print("[API Keys]")
        print("=" * 60)
        active = set(active_providers())
        for prov in sorted(keys):
            label = PROVIDER_LABELS.get(prov, prov)
            icon = "[OK]" if prov in active else ""
            print(f"  {label:14s}  {keys[prov]:30s}  {icon}")
        print(f"\nActive providers: {len(active)} / {len(ALL_PROVIDERS)}")
        print("Tip:  python -m src.cli apikeys set <provider> <key>")
        return 0

    if args.action == "set":
        result = set_key(args.provider, args.key)
        if result["success"]:
            print(f"[OK] Key saved for '{result['provider']}' (env var: {result['env_var']})")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    if args.action == "delete":
        result = delete_key(args.provider)
        if result["success"]:
            print(f"[OK] Key deleted for '{result['provider']}'")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    if args.action == "export":
        result = export_dotenv(args.path)
        if result["success"]:
            print(f"[OK] Exported {result['count']} keys to {result['path']}")
        else:
            print(f"[FAIL] {result['error']}")
            return 1
        return 0

    return 1
