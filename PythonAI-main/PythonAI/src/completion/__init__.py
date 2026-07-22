"""Shell completion support for ForgeAI CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

__all__ = [
    "generate_bash_completion",
    "generate_zsh_completion",
    "generate_fish_completion",
    "find_possible_completions",
    "print_completion",
]

# ── Internal flag sent by the shell completion scripts ────────
_AUTO_COMPLETE_FLAG = "--_forgeai-complete"


def find_possible_completions(
    parser: argparse.ArgumentParser,
    args: list[str],
) -> list[str]:
    """Given a partial command line, return possible completions.

    This is the core function called by shell completion scripts.
    """
    # Remove the program name and any internal flags
    clean_args = [a for a in args if not a.startswith(_AUTO_COMPLETE_FLAG)]

    # Find the partial word being completed (last element if it doesn't start with -)
    partial = clean_args[-1] if clean_args else ""

    # ForgeAI top-level commands
    top_commands = []
    for action in parser._subparsers._group_actions if parser._subparsers else []:  # type: ignore[union-attr]
        if isinstance(action, argparse._SubParsersAction):  # type: ignore[attr-defined]
            top_commands = list(action.choices.keys())

    # If no args yet, complete with top-level commands + global flags
    if not clean_args:
        completions = list(top_commands)
        for action in parser._actions:
            if action.option_strings:
                completions.extend(action.option_strings)
        return sorted(set(c for c in completions if c.startswith(partial)))

    # Try to find the current subparser context
    tokens = clean_args  # e.g. ["review", "code", "--file", "./te"]
    subparser = None
    used_tokens = []

    # Walk through tokens to find current subparser
    current_parser = parser
    i = 0
    while i < len(tokens):
        token = tokens[i]
        # Skip options that take a value
        if token.startswith("--") or token.startswith("-"):
            # Check if this option takes a value
            for action in current_parser._actions:
                if token in action.option_strings:
                    if action.nargs is None or action.nargs == 1:  # takes one value
                        # If this is the last token and next doesn't start with -, the value is being completed
                        if i + 1 < len(tokens):
                            if tokens[i + 1].startswith("-"):
                                break  # next is another flag, so current is a store_true/bool
                        break
                    break
            i += 1
            continue

        # Check if token is a subcommand
        if current_parser._subparsers:
            for group_action in current_parser._subparsers._group_actions:  # type: ignore[union-attr]
                if token in group_action.choices:
                    current_parser = group_action.choices[token]
                    break
        i += 1

    # Generate completions from the current parser
    completions: list[str] = []

    # Subcommands of current parser
    if current_parser._subparsers:
        for group_action in current_parser._subparsers._group_actions:  # type: ignore[union-attr]
            completions.extend(group_action.choices.keys())

    # Options of current parser
    for action in current_parser._actions:
        if action.option_strings:
            completions.extend(action.option_strings)

    # If we're completing a value for an option with choices, suggest those
    # Check the last two tokens
    if len(clean_args) >= 2:
        prev = clean_args[-2]
        for action in current_parser._actions:
            if prev in action.option_strings:
                if action.choices:
                    completions.extend(str(c) for c in action.choices)
                elif action.type == str:
                    # Suggest file paths if no explicit choices
                    completions.extend(_file_completions(partial))

    # Filter by partial match
    if partial:
        completions = [c for c in completions if c.startswith(partial)]

    return sorted(set(completions))


def _file_completions(partial: str) -> list[str]:
    """Return file/directory completions for the given partial path."""
    try:
        path = Path(partial or ".")
        parent = path.parent if partial else Path(".")
        if not parent.exists():
            return []
        matches = []
        for entry in parent.iterdir():
            name = entry.name
            if name.startswith(".") and not partial.startswith("."):
                continue
            if name.startswith(path.name) or not partial:
                if entry.is_dir():
                    matches.append(name + "/")
                else:
                    matches.append(name)
        return matches
    except (OSError, PermissionError):
        return []


def generate_bash_completion(script_path: str) -> str:
    """Generate a bash completion script for forgeai.py."""
    return f"""#/usr/bin/env bash
# ForgeAI CLI bash completion
_forgeai_completions() {{
    local cur prev words cword
    # Fallback if _init_completion is unavailable
    if type _init_completion &>/dev/null; then
        _init_completion -n = || return
    else
        cur="${{COMP_WORDS[COMP_CWORD]}}"
        prev="${{COMP_WORDS[COMP_CWORD-1]}}"
    fi

    # Collect full command line args (skip program name)
    local all_args=()
    for ((i=1; i < ${{#COMP_WORDS[@]}}-1; i++)); do
        all_args+=("${{COMP_WORDS[i]}}")
    done

    {script_path} {_AUTO_COMPLETE_FLAG} -- "${{all_args[@]}}" "$cur" 2>/dev/null | while IFS= read -r line; do
        COMPREPLY+=("$line")
    done
    return 0
}}
complete -F _forgeai_completions forgeai.py
complete -F _forgeai_completions forgeai
"""


def generate_zsh_completion(script_path: str) -> str:
    """Generate a zsh completion script for forgeai.py."""
    return f"""#compdef forgeai.py forgeai
# ForgeAI CLI zsh completion
_forgeai_completions() {{
    local -a completions
    local completion_file="${{TMPDIR:-/tmp}}/forgeai_completions.$$"

    # Call forgeai's internal completion helper
    ${{script_path}} {_AUTO_COMPLETE_FLAG} -- $@ > "$completion_file" 2>/dev/null
    if [[ -f "$completion_file" ]]; then
        completions=($(cat "$completion_file"))
        rm -f "$completion_file"
    fi

    _describe 'forgeai' completions
    return 0
}}

compdef _forgeai_completions forgeai.py
compdef _forgeai_completions forgeai
"""


def generate_fish_completion(script_path: str) -> str:
    """Generate a fish shell completion script for forgeai.py."""
    return f"""# ForgeAI CLI fish completion
function __forgeai_completions
    set -l tokens (commandline -opc)
    {script_path} {_AUTO_COMPLETE_FLAG} -- $tokens[2..-1] 2>/dev/null | tr '\\n' '\\t'
end

complete -c forgeai.py -f -a '(__forgeai_completions)'
complete -c forgeai -f -a '(__forgeai_completions)'
"""


def print_completion(parser: argparse.ArgumentParser, shell: str, script_path: str) -> str:
    """Print the completion script for the given shell."""
    if shell == "bash":
        return generate_bash_completion(script_path)
    elif shell == "zsh":
        return generate_zsh_completion(script_path)
    elif shell == "fish":
        return generate_fish_completion(script_path)
    else:
        raise ValueError(f"Unsupported shell: {shell}")


def handle_auto_complete(parser: argparse.ArgumentParser) -> None:
    """Handle the internal --_forgeai-complete flag for dynamic completion."""
    if _AUTO_COMPLETE_FLAG not in sys.argv:
        return

    # Find the separator
    try:
        sep_idx = sys.argv.index("--")
    except ValueError:
        return

    # Everything after -- is the partial command
    partial_args = sys.argv[sep_idx + 1 :]

    completions = find_possible_completions(parser, partial_args)
    for c in completions:
        print(c)
    sys.exit(0)
