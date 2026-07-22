"""Dedicated unit tests for the CLI completion module."""

from __future__ import annotations

import argparse


class TestCompletionCore:
    """Tests for the completion module core functions."""

    def test_find_possible_completions_top_level(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        sub.add_parser("install")
        sub.add_parser("train")
        sub.add_parser("status")
        comps = find_possible_completions(parser, [""])
        assert "install" in comps
        assert "train" in comps
        assert "status" in comps

    def test_find_possible_completions_subcommand(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        train_parser = sub.add_parser("train")
        train_parser.add_argument("--model", type=str)
        train_parser.add_argument("--epochs", type=int)
        comps = find_possible_completions(parser, ["train", ""])
        assert "--model" in comps
        assert "--epochs" in comps

    def test_find_possible_completions_flags(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        parser.add_argument("--verbose", action="store_true")
        parser.add_argument("--config", type=str)
        sub = parser.add_subparsers()
        sub.add_parser("start")
        comps = find_possible_completions(parser, ["--"])
        assert "--verbose" in comps
        assert "--config" in comps

    def test_find_possible_completions_partial_flag(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        parser.add_argument("--verbose", action="store_true")
        parser.add_argument("--version", action="store_true")
        parser.add_argument("--config", type=str)
        comps = find_possible_completions(parser, ["--ver"])
        assert "--verbose" in comps
        assert "--version" in comps
        assert "--config" not in comps

    def test_find_possible_completions_nested_subcommands(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        adapter = sub.add_parser("adapter")
        adapter_sub = adapter.add_subparsers()
        adapter_sub.add_parser("list")
        adapter_sub.add_parser("install")
        adapter_sub.add_parser("remove")
        adapter.add_argument("--format", type=str)

        comps = find_possible_completions(parser, ["adapter", ""])
        assert "list" in comps
        assert "install" in comps
        assert "remove" in comps
        assert "--format" in comps

    def test_find_possible_completions_no_partial(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        sub.add_parser("install")
        sub.add_parser("train")
        # With no partial word, return all
        comps = find_possible_completions(parser, [])
        assert "install" in comps
        assert "train" in comps

    def test_find_possible_completions_nested_partial(self) -> None:
        from src.completion import find_possible_completions
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        train = sub.add_parser("train")
        train_sub = train.add_subparsers()
        train_sub.add_parser("start")
        train_sub.add_parser("stop")
        train.add_argument("--model", type=str)

        comps = find_possible_completions(parser, ["train", "--mode"])
        assert "--model" in comps


class TestCompletionGenerate:
    """Tests for completion script generation."""

    def test_generate_bash_completion(self) -> None:
        from src.completion import generate_bash_completion
        script = generate_bash_completion("/usr/local/bin/forgeai")
        assert "forgeai" in script
        assert "_forgeai_completions" in script
        assert "bash" in script or "COMPREPLY" in script

    def test_generate_zsh_completion(self) -> None:
        from src.completion import generate_zsh_completion
        script = generate_zsh_completion("/usr/local/bin/forgeai")
        assert "forgeai" in script
        assert "_forgeai_completions" in script

    def test_generate_fish_completion(self) -> None:
        from src.completion import generate_fish_completion
        script = generate_fish_completion("/usr/local/bin/forgeai")
        assert "forgeai" in script
        assert "complete -c forgeai" in script or "__forgeai_completions" in script

    def test_print_completion_bash(self) -> None:
        from src.completion import print_completion
        parser = argparse.ArgumentParser()
        script = print_completion(parser, "bash", "/usr/bin/forgeai")
        assert "bash" in script

    def test_print_completion_invalid_shell(self) -> None:
        from src.completion import print_completion
        parser = argparse.ArgumentParser()
        try:
            print_completion(parser, "invalid-shell", "/usr/bin/forgeai")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Unsupported shell" in str(e)
