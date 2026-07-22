from __future__ import annotations

import argparse


def provider_cmd(args: argparse.Namespace) -> int:
    """Manage provider selection and routing."""
    from src.core.providers import (
        ProfileManager,
        ProviderDiscovery,
        ProviderRouter,
    )

    router = ProviderRouter()
    profile_mgr = ProfileManager()

    if args.action == "list":
        statuses = router.get_provider_status()
        print("\n[Provider] Available Providers")
        print(f"{'=' * 60}")
        print(f"  {'ID':14s} {'Status':10s} {'Default Model':30s}")
        print(f"  {'=' * 14} {'=' * 10} {'=' * 30}")
        for s in statuses:
            status_str = "[OK]" if s["available"] else "[--]"
            print(f"  {s['id']:14s} {status_str:10s} {s['default_model']:30s}")
        print()
        return 0

    if args.action == "current":
        current = profile_mgr.get_current()
        print("\n[Provider] Current Selection")
        print(f"{'=' * 50}")
        print(f"  Provider : {current['provider']}")
        print(f"  Model    : {current['model'] or '(default)'}")
        print(f"  Label    : {current['label']}")
        if current.get("base_url"):
            print(f"  Base URL : {current['base_url']}")
        print(f"  Strategy : {current.get('strategy', 'auto')}")
        print(f"  Saved    : {current.get('is_saved', False)}")
        print()

        # Show route result
        result = router.route(
            provider=current["provider"],
            model=current["model"],
        )
        if result.error:
            print(f"  [!] {result.error}")
        else:
            print("  Active Route:")
            print(f"    Provider: {result.provider}")
            print(f"    Model   : {result.model}")
            print(f"    API     : {result.base_url}")
            print(f"    Key     : {'...' + result.api_key[-4:] if result.api_key else 'N/A'}")
            print(f"    Type    : {result.api_type}")
        print()
        return 0

    if args.action == "switch":
        provider = args.provider
        if not provider:
            print("[Error] Please specify a provider. Use: python -m src.cli provider switch <provider>")
            return 1

        from src.core.providers import get_registry

        provider_info = get_registry().get_provider(provider)

        if not provider_info:
            print(f"[Error] Unknown provider '{provider}'. Use 'python -m src.cli provider list' to see available.")
            return 1

        if provider_info.requires_key and not router.has_key(provider):
            print(f"[!] No API key found for '{provider}'. Set {provider_info.env_key} env var or use:")
            print(f"    python -m src.cli apikeys set {provider} <your-key>")
            return 1

        profile = profile_mgr.set_provider(
            provider=provider,
            model=args.model or "",
            base_url=args.base_url or "",
            strategy=args.strategy or "auto",
            goal=args.goal or "coding",
        )
        print(f"[OK] Switched to provider: {profile.label} ({profile.provider})")
        if profile.model:
            print(f"     Model: {profile.model}")
        print(f"     Saved to: {profile_mgr.profile_path}")
        print()
        print("  Next: Run 'python -m src.cli ask \"your question\" --tools' to use with tools")
        print("        Or run 'python -m src.cli ask \"your question\"' for RAG mode")
        return 0

    if args.action == "reset":
        profile_mgr.delete()
        print("[OK] Provider profile cleared. Will auto-select provider on next run.")
        return 0

    if args.action == "discover":
        discovery = ProviderDiscovery()
        print("[Provider] Discovering local models...")
        print()

        ollama = discovery.discover_ollama()
        if ollama:
            print(f"  Ollama Models ({len(ollama)}):")
            for m in ollama:
                print(f"    - {m['name']}")
            print()
        else:
            print("  Ollama: Not found or no models installed.")
            print()

        endpoints = discovery.detect_local_endpoints()
        if endpoints:
            print(f"  Local Endpoints ({len(endpoints)}):")
            for ep in endpoints:
                print(f"    - {ep['label']}: {ep['base_url']}")
            print()

        statuses = router.get_provider_status()
        cloud = [s for s in statuses if not s["is_local"] and s["available"]]
        if cloud:
            print(f"  Cloud Providers with keys ({len(cloud)}):")
            for s in cloud:
                print(f"    - {s['label']} ({s['id']}): {s['default_model']}")
            print()

        return 0

    return 1


def models_cmd(args: argparse.Namespace) -> int:
    """List available models."""
    from src.core.providers import get_registry

    registry = get_registry()
    provider = args.provider
    models = registry.list_models(provider=provider if provider else None)

    if provider:
        models = [m for m in models if m.provider == provider]
        if not models:
            print(f"[Models] No models found for provider '{provider}'")
            return 1

    print(f"\n[Models] Known Models ({len(models)})")
    print(f"{'=' * 70}")
    print(f"  {'Model ID':30s} {'Provider':12s} {'Context':10s} {'Capabilities'}")
    print(f"  {'=' * 30} {'=' * 12} {'=' * 10} {'=' * 20}")

    for m in models:
        caps = []
        if m.capabilities.vision:
            caps.append("vision")
        if m.capabilities.reasoning:
            caps.append("reasoning")
        if "coding" in m.classification:
            caps.append("coding")
        cap_str = ", ".join(caps) if caps else "chat"

        ctx = f"{m.context_window:,}"
        default_mark = " [D]" if m.default_model else ""
        print(f"  {m.id:30s} {m.provider:12s} {ctx:10s} {cap_str}{default_mark}")

    print()
    print("  [D] = Default model for provider")
    print()
    return 0
