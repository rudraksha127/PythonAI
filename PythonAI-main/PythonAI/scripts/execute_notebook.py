import json
import os
import sys
import traceback
import subprocess
from io import StringIO
from pathlib import Path

# Set up project root in path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class CellExecutionError(Exception):
    pass


def execute_notebook(nb_path: Path):
    print(f"Loading notebook: {nb_path}")
    with open(nb_path, "r", encoding="utf-8") as f:
        nb = json.load(f)

    cells = nb.get("cells", [])
    globals_dict = {
        "__name__": "__main__",
        "__file__": str(nb_path),
    }

    execution_count = 1

    for idx, cell in enumerate(cells):
        if cell.get("cell_type") != "code":
            continue

        source = cell.get("source", [])
        if isinstance(source, list):
            source_str = "".join(source)
        else:
            source_str = str(source)

        if not source_str.strip():
            continue

        print(f"\n--- Running Cell {idx} ---")
        print(f"Source Preview:\n{source_str[:150]}...")

        # Parse and prepare source lines
        clean_lines = []
        shell_commands = []

        for line in source_str.splitlines():
            stripped = line.strip()
            if stripped.startswith("!"):
                shell_commands.append(stripped[1:])
            elif stripped.startswith("%%"):
                # Ignore cell magics like %%capture
                print(f"Ignoring cell magic: {stripped}")
                continue
            elif stripped.startswith("%"):
                # Ignore line magics
                print(f"Ignoring line magic: {stripped}")
                continue
            else:
                clean_lines.append(line)

        python_code = "\n".join(clean_lines)

        # Clear existing cell outputs
        cell["outputs"] = []
        cell["execution_count"] = execution_count

        # Execute any shell commands first
        shell_failed = False
        for cmd in shell_commands:
            print(f"Executing shell command: !{cmd}")
            # Run the shell command in the context of our python environment
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            stdout_text = res.stdout
            stderr_text = res.stderr

            # Print to stdout/stderr of execution runner
            if stdout_text:
                sys.stdout.write(stdout_text)
            if stderr_text:
                sys.stderr.write(stderr_text)

            # Append outputs to cell
            if stdout_text:
                cell["outputs"].append(
                    {"name": "stdout", "output_type": "stream", "text": stdout_text.splitlines(keepends=True)}
                )
            if stderr_text:
                cell["outputs"].append(
                    {"name": "stderr", "output_type": "stream", "text": stderr_text.splitlines(keepends=True)}
                )

            if res.returncode != 0:
                print(f"Shell command failed with exit code {res.returncode}")
                shell_failed = True
                break

        if shell_failed:
            raise CellExecutionError(f"Shell command failed in Cell {idx}")

        # Execute python code
        if python_code.strip():
            # Capture python execution stdout/stderr
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            redirected_stdout = StringIO()
            redirected_stderr = StringIO()
            sys.stdout = redirected_stdout
            sys.stderr = redirected_stderr

            try:
                # Compile and execute
                compiled_code = compile(python_code, f"<cell_{idx}>", "exec")
                exec(compiled_code, globals_dict)
            except Exception as e:
                # Restore streams before handling traceback
                sys.stdout = old_stdout
                sys.stderr = old_stderr

                # Get traceback
                tb = traceback.format_exc()
                print(f"Error in Cell {idx}:")
                print(tb)

                # Save traceback to cell outputs
                cell["outputs"].append(
                    {
                        "ename": type(e).__name__,
                        "evalue": str(e),
                        "output_type": "error",
                        "traceback": tb.splitlines(keepends=True),
                    }
                )

                # Save the notebook so the error output is stored inside it
                with open(nb_path, "w", encoding="utf-8") as f:
                    json.dump(nb, f, indent=1, ensure_ascii=False)

                raise CellExecutionError(f"Python exception in Cell {idx}")
            finally:
                # Always restore streams if not already done
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            # Get captured outputs
            stdout_val = redirected_stdout.getvalue()
            stderr_val = redirected_stderr.getvalue()

            if stdout_val:
                sys.stdout.write(stdout_val)
                cell["outputs"].append(
                    {"name": "stdout", "output_type": "stream", "text": stdout_val.splitlines(keepends=True)}
                )
            if stderr_val:
                sys.stderr.write(stderr_val)
                cell["outputs"].append(
                    {"name": "stderr", "output_type": "stream", "text": stderr_val.splitlines(keepends=True)}
                )

        print(f"Cell {idx} completed successfully.")
        execution_count += 1

    # Save the updated notebook on full success
    print(f"Saving notebook output...")
    with open(nb_path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=1, ensure_ascii=False)
    print("Notebook saved successfully.")


if __name__ == "__main__":
    notebook_file = ROOT / "colab_export" / "finetune_qwen14b_unsloth.ipynb"
    try:
        execute_notebook(notebook_file)
        print("\nSUCCESS: All cells executed successfully!")
    except CellExecutionError as e:
        print(f"\nFAILURE: Notebook execution stopped: {e}")
        sys.exit(1)
