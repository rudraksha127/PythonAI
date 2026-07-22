from __future__ import annotations

import argparse
import shlex


def tools_cmd(args: argparse.Namespace) -> int:
    from src.tools import ALL_TOOLS as MCP_TOOLS

    print("\n[Tools] Registered Tools")
    print(f"{'=' * 55}")

    print(f"\n  MCP Tools ({len(MCP_TOOLS)}):")
    for t in MCP_TOOLS:
        print(f"    - {t.name}: {t.description}")

    try:
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass
        if registry.total_count > 0:
            print(f"\n  Core Tools ({registry.total_count}):")
            for t in registry.list_all():
                ro = " [RO]" if t.is_readonly() else ""
                print(f"    - {t.name}: {t.description}{ro}")
    except ImportError:
        pass

    print()
    return 0


def mcp_cmd(args: argparse.Namespace) -> int:
    """Manage MCP server connections, configs, and tools."""
    from src.core.mcp import (
        HTTPConfig,
        MCPClient,
        MCPConfigManager,
        MCPScope,
        SSEConfig,
        StdioConfig,
        discover_mcp_servers,
        find_mcp_json_files,
    )

    if args.action == "list":
        config_mgr = MCPConfigManager()
        summary = config_mgr.summary()

        print(f"\n[MCP] Configured Servers ({summary['total']})")
        print(f"{'=' * 60}")

        if not summary["servers"]:
            print("  No MCP servers configured.")
            print("  Run 'python -m src.cli mcp add <name> --command <cmd>' to add one.")
        else:
            for s in summary["servers"]:
                print(f"  {s['name']:25s} {s['type']:25s} [{s['scope']}]")

        json_files = find_mcp_json_files()
        if json_files:
            print("\n  Config files:")
            for f in json_files:
                print(f"    {f}")
        print()
        return 0

    if args.action == "discover":
        print("\n[MCP] Discovery")
        print(f"{'=' * 60}")

        json_files = find_mcp_json_files()
        if json_files:
            print("\n  Config files found:")
            for f in json_files:
                size = f.stat().st_size
                print(f"    - {f} ({size} bytes)")
        else:
            print("\n  No .mcp.json or mcp.json config files found.")

        import os

        env_servers = {}
        for key in os.environ:
            if key.startswith("PYTHONAI_MCP_") and key.endswith("_COMMAND"):
                name = key[len("PYTHONAI_MCP_") : -len("_COMMAND")].lower()
                env_servers[name] = os.environ[key]

        if env_servers:
            print(f"\n  Environment-defined servers ({len(env_servers)}):")
            for name, cmd in env_servers.items():
                print(f"    - {name}: {cmd}")

        config_mgr = MCPConfigManager()
        servers = config_mgr.get_servers()
        if servers:
            print(f"\n  Registered servers ({len(servers)}):")
            for name in servers:
                print(f"    - {name}")
        print()
        return 0

    if args.action == "add":
        name = args.name
        transport_type = args.type or "stdio"

        if transport_type == "stdio":
            if not args.command:
                print("[Error] --command is required for stdio servers")
                return 1
            args_list = shlex.split(args.args) if args.args else []
            config = StdioConfig(command=args.command, args=args_list)
        elif transport_type == "sse":
            if not args.url:
                print("[Error] --url is required for SSE servers")
                return 1
            config = SSEConfig(url=args.url)
        elif transport_type == "http":
            if not args.url:
                print("[Error] --url is required for HTTP servers")
                return 1
            config = HTTPConfig(url=args.url)
        else:
            print(f"[Error] Unsupported transport: {transport_type}")
            return 1

        scope_map = {
            "project": MCPScope.PROJECT,
            "local": MCPScope.LOCAL,
            "user": MCPScope.USER,
        }
        scope = scope_map.get(args.scope or "local", MCPScope.LOCAL)

        config_mgr = MCPConfigManager()
        config_mgr.add(name, config, scope)

        print(f"[OK] MCP server '{name}' added ({transport_type}, scope: {scope.value})")
        print(f"  Run 'python -m src.cli mcp connect --server {name}' to connect")
        return 0

    if args.action == "remove":
        name = args.name
        config_mgr = MCPConfigManager()
        if config_mgr.remove(name):
            print(f"[OK] MCP server '{name}' removed")
        else:
            print(f"[Error] MCP server '{name}' not found")
            return 1
        return 0

    if args.action == "connect":
        if args.server:
            server_name = args.server
            config_mgr = MCPConfigManager()
            config = config_mgr.get(server_name)
            if not config:
                print(f"[Error] Server '{server_name}' not found in config")
                print("  Run 'python -m src.cli mcp discover' to see available servers")
                return 1

            print(f"\n[MCP] Connecting to '{server_name}'...")

            from src.core.mcp import MCPClient

            client = MCPClient()
            connection = client.connect(config, server_name)

            if connection.state.name == "CONNECTED":
                print("  [OK] Connected!")
                print(f"  Tools: {len(connection.tools)}")
                print(f"  Resources: {len(connection.resources)}")
                print()

                if connection.tools:
                    print(f"  {'Tool Name':45s} {'Description'}")
                    print(f"  {'=' * 45} {'=' * 40}")
                    for t in connection.tools:
                        desc = t.description[:50] + "..." if len(t.description) > 50 else t.description
                        print(f"  {t.name:45s} {desc}")

                from src.core.registry import get_registry

                registry = get_registry()
                count = registry.register_mcp_server(connection)
                print(f"\n  Registered {count} MCP tools in PythonAI registry")
                print(f"  Total tools: {registry.total_count}")
            else:
                print(f"  [FAIL] {connection.error}")
            print()
        else:
            print("\n[MCP] Connecting to all configured servers...")
            connections = discover_mcp_servers()

            connected = 0
            total_tools = 0
            for name, conn in connections.items():
                if conn.state.name == "CONNECTED":
                    connected += 1
                    total_tools += len(conn.tools)
                    from src.core.registry import get_registry

                    get_registry().register_mcp_server(conn)
                    print(f"  [OK] {name}: {len(conn.tools)} tools, {len(conn.resources)} resources")
                else:
                    print(f"  [--] {name}: {conn.error or 'failed'}")

            print(f"\n  Connected: {connected}/{len(connections)}")
            print(f"  Total MCP tools registered: {total_tools}")
            print()
        return 0

    if args.action == "start":
        """Start PythonAI as an MCP server."""
        from src.core.mcp import MCPServer, start_mcp_server
        from src.core.registry import get_registry
        from src.core.tools import register_all_tools

        registry = get_registry()
        try:
            register_all_tools(registry)
        except Exception:
            pass

        def get_tools_list():
            registry = get_registry()
            return [t.to_dict() for t in registry.list_all()]

        server = MCPServer(
            name="pythonai",
            version="2.1.0",
            get_tools_fn=get_tools_list,
        )

        print(f"\n[MCP] Starting PythonAI MCP server ({args.transport})...")
        print(f"  Tools available: {len(get_tools_list())}")

        if args.transport == "sse":
            print(f"  SSE endpoint: http://{args.host}:{args.port}/sse")
            print(f"  Message endpoint: http://{args.host}:{args.port}/message")
            print("  Press Ctrl+C to stop\n")
        else:
            print("  Stdio mode — reading from stdin, writing to stdout")
            print("  Use with: claude mcp add pythonai -- python -m src.cli mcp start")
            print()

        start_mcp_server(
            server,
            transport=args.transport,
            host=args.host,
            port=args.port,
        )
        return 0

    return 1
