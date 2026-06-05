"""End-to-end tests for the CLI argument parsing stage.

Covers argument parsing for all subcommands and flags.
"""

from __future__ import annotations


def test_cli_status_with_json_and_verbose() -> None:
    """status command should parse --json and --verbose flags."""
    from src.cli import build_parser

    parser = build_parser()
    args = parser.parse_args(["status", "--json"])
    assert args.command == "status"
    assert args.json_output is True
    assert args.verbose is False

    args2 = parser.parse_args(["status", "--verbose"])
    assert args2.command == "status"
    assert args2.verbose is True


def test_cli_ask_with_all_flags() -> None:
    """ask command should parse all RAG-related flags."""
    from src.cli import build_parser

    parser = build_parser()
    ask_args = parser.parse_args([
        "ask", "What is a list?",
        "--rebuild", "--stats", "--no-exec", "--exec-timeout", "10",
        "--query-expansion", "--mmr", "--version", "3.12", "--category", "library",
    ])
    assert ask_args.command == "ask"
    assert ask_args.question == "What is a list?"
    assert ask_args.rebuild is True
    assert ask_args.stats is True
    assert ask_args.no_exec is True
    assert ask_args.exec_timeout == 10
    assert ask_args.query_expansion is True
    assert ask_args.mmr is True
    assert ask_args.version == "3.12"
    assert ask_args.category == "library"


def test_cli_train_with_flags() -> None:
    """train command should parse mode, steps, skip, no-auth flags."""
    from src.cli import build_parser

    parser = build_parser()
    train_args = parser.parse_args([
        "train", "--mode", "smoke", "--max-steps", "5",
        "--skip-train", "--no-auth",
    ])
    assert train_args.command == "train"
    assert train_args.mode == "smoke"
    assert train_args.max_steps == 5
    assert train_args.skip_train is True
    assert train_args.no_auth is True


def test_cli_login_subcommands() -> None:
    """login command should parse check and logout subcommands."""
    from src.cli import build_parser

    parser = build_parser()
    login_args = parser.parse_args(["login", "check"])
    assert login_args.command == "login"
    assert login_args.action == "check"

    login_args2 = parser.parse_args(["login", "logout"])
    assert login_args2.action == "logout"

    login_args3 = parser.parse_args(["login"])
    assert login_args3.action == "login"


def test_cli_eval_probe_clean_dataset_augment_merge() -> None:
    """All other CLI commands should parse correctly."""
    from src.cli import build_parser

    parser = build_parser()

    # eval
    eval_args = parser.parse_args(["eval", "--adapter-path", "test/path", "--output-json", "test.json"])
    assert eval_args.command == "eval"
    assert eval_args.adapter_path == "test/path"

    # probe
    probe_args = parser.parse_args(["probe", "--prompt", "Hello", "--num-ctx", "1024"])
    assert probe_args.command == "probe"
    assert probe_args.prompt == "Hello"
    assert probe_args.num_ctx == 1024

    # clean
    clean_args = parser.parse_args(["clean", "--apply"])
    assert clean_args.command == "clean"
    assert clean_args.apply is True

    # dataset
    dataset_args = parser.parse_args(["dataset", "--path", "data/custom.json"])
    assert dataset_args.command == "dataset"
    assert dataset_args.path == "data/custom.json"

    # augment
    augment_args = parser.parse_args(["augment", "--model", "qwen:7b", "--limit", "5", "--merge", "--dry-run"])
    assert augment_args.command == "augment"
    assert augment_args.model == "qwen:7b"
    assert augment_args.limit == 5
    assert augment_args.merge is True
    assert augment_args.dry_run is True

    # merge
    merge_args = parser.parse_args(["merge", "--base", "a.json", "--add", "b.json", "--output", "c.json"])
    assert merge_args.command == "merge"
    assert merge_args.base == "a.json"
    assert merge_args.add == "b.json"
    assert merge_args.output == "c.json"
