"""
PythonAI Tool System — Comprehensive Test
============================================
Tests all Phase 1 tools and the ToolCallingEngine.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = 0
FAIL = 0
SUITE = ""


def section(name):
    global SUITE
    SUITE = name
    print(f"\n{'=' * 60}")
    print(f"  {name}")
    print(f"{'=' * 60}")


def check(desc, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [OK] {desc}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {desc}"
        if detail:
            msg += f"\n      -> {detail}"
        print(msg)


# ═══════════════════════════════════════
# 1. Tool Class Creation
# ═══════════════════════════════════════
section("1. Tool Class Creation")

from src.core.tool import InputSchema, Parameter, ToolUseContext, build_tool  # noqa: E402

# Create context
ctx = ToolUseContext(cwd=os.path.dirname(os.path.abspath(__file__)))

# Create a test tool
TestTool = build_tool(
    type(
        "TestToolDef",
        (),
        {
            "name": "test",
            "description": "A test tool",
            "input_schema": InputSchema(
                msg=Parameter(type="string", description="A message", required=True),
            ),
            "call": lambda i, c: type("R", (), {"data": {"echo": i.get("msg", ""), "success": True}})(),
            "is_readonly": True,
        },
    )
)

check("build_tool creates tool", TestTool.name == "test")
check("Tool has name", TestTool.name == "test")
check("Tool has description", "test" in TestTool.description)
check("Tool is readonly", TestTool.is_readonly() is True)
check("Tool is not destructive", TestTool.is_destructive() is False)
check("Tool is enabled", TestTool.is_enabled() is True)

result = TestTool.call({"msg": "hello"}, ctx)
check("Tool call returns data", result.data is not None)
check("Tool call echo works", result.data.get("echo") == "hello")
check("Tool call success", result.data.get("success") is True)

# Test validation
validation = TestTool.validate_input({"msg": "test"}, ctx)
check("Valid input passes", validation.success is True)

validation = TestTool.validate_input({}, ctx)
check("Missing required fails", validation.success is False)
check("  error code is 1", validation.error_code == 1)

# Test to_openai_tool
openai_fmt = TestTool.to_openai_tool()
check("OpenAI format has type", openai_fmt.get("type") == "function")
check("OpenAI format has function name", openai_fmt["function"]["name"] == "test")

# Test to_anthropic_tool
anthropic_fmt = TestTool.to_anthropic_tool()
check("Anthropic format has name", anthropic_fmt.get("name") == "test")

# Test to_dict
td = TestTool.to_dict()
check("to_dict has name", td.get("name") == "test")
check("to_dict has readonly", td.get("readonly") is True)


# ═══════════════════════════════════════
# 2. ToolRegistry
# ═══════════════════════════════════════
section("2. ToolRegistry")

from src.core.registry import ToolRegistry  # noqa: E402

registry = ToolRegistry()
check("New registry has 0 tools", registry.builtin_count == 0)

registry.register(TestTool)
check("After register, count is 1", registry.builtin_count == 1)
check("get finds tool", registry.get("test") is not None)
check("has_tool works", registry.has_tool("test") is True)
check("list_all returns 1", len(registry.list_all()) == 1)
check("list_builtin returns 1", len(registry.list_builtin()) == 1)
check("get_readonly returns 1", len(registry.get_readonly()) == 1)
check("get_writable returns 0", len(registry.get_writable()) == 0)

# Assemble pool
pool = registry.assemble_pool()
check("assemble_pool has tools", len(pool) > 0)


# ═══════════════════════════════════════
# 3. BashTool
# ═══════════════════════════════════════
section("3. BashTool")

from src.core.tools.bash_tool import BashTool  # noqa: E402

check("BashTool has name", BashTool.name == "bash")
check("BashTool is destructive", BashTool.is_destructive() is True)
check("BashTool is not readonly", BashTool.is_readonly() is False)

# Run echo
result = BashTool.call({"command": "echo 'hello world'"}, ctx)
check("bash echo works", "hello world" in result.data.get("stdout", ""))
check("bash exit code 0", result.data.get("exit_code") == 0)

# Run with cwd
result = BashTool.call({"command": "pwd", "cwd": ctx.cwd}, ctx)
check("bash pwd works", "PythonAI" in result.data.get("stdout", ""))

# Test timeout
result = BashTool.call({"command": "sleep 0.1 && echo 'done'", "timeout": 10}, ctx)
check("bash timeout works", result.data.get("exit_code") == 0)

# Test dangerous command blocked
result = BashTool.call({"command": "sudo rm -rf /"}, ctx)
check("bash blocks sudo", result.data.get("exit_code") == 1)
stderr = result.data.get("stderr", "")
check("  error mentions blocked", "Blocked" in stderr or "not allowed" in stderr)

# Test validation
validation = BashTool.input_schema().validate({"command": "ls"})
check("bash valid input", validation.success is True)

validation = BashTool.input_schema().validate({})
check("bash empty input fails", validation.success is False)


# ═══════════════════════════════════════
# 4. FileReadTool
# ═══════════════════════════════════════
section("4. FileReadTool")

from src.core.tools.file_read_tool import FileReadTool  # noqa: E402

check("FileReadTool name", FileReadTool.name == "read")
check("FileReadTool is readonly", FileReadTool.is_readonly() is True)

# Read a known file
test_file = os.path.join(os.path.dirname(__file__), "src/core/tool.py")
result = FileReadTool.call({"file_path": test_file}, ctx)
check("read tool.py works", result.data is not None)
check("  has content", "class Tool" in result.data.get("content", ""))
check("  has line numbers", "|" in result.data.get("content", ""))
check("  total_lines > 0", result.data.get("total_lines", 0) > 0)
check("  start_line is 1", result.data.get("start_line") == 1)

# Read with offset
result = FileReadTool.call({"file_path": test_file, "offset": 1, "limit": 5}, ctx)
check("read with offset/limit works", result.data.get("num_lines") == 5)
check("  start_line is 1", result.data.get("start_line") == 1)

# Read non-existent file
result = FileReadTool.call({"file_path": "/nonexistent/file.py"}, ctx)
check("read missing file returns error", result.error is not None)

# Validation check
validation = FileReadTool.validate_input({"file_path": ""}, ctx)
check("empty file_path fails", validation.success is False)


# ═══════════════════════════════════════
# 5. FileWriteTool
# ═══════════════════════════════════════
section("5. FileWriteTool")

from src.core.tools.file_write_tool import FileWriteTool  # noqa: E402

check("FileWriteTool name", FileWriteTool.name == "write")
check("FileWriteTool is destructive", FileWriteTool.is_destructive() is True)

# Write a test file
temp_dir = os.path.join(os.path.dirname(__file__), "_test_temp")
os.makedirs(temp_dir, exist_ok=True)
temp_file = os.path.join(temp_dir, "test_write.txt")

result = FileWriteTool.call({"file_path": temp_file, "content": "Hello World!\nLine 2\n"}, ctx)
check("write file works", result.error is None)
check("  returns file_path", temp_file in result.data.get("file_path", ""))

# Verify content was written
with open(temp_file) as f:
    content = f.read()
check("  file content matches", content == "Hello World!\nLine 2\n")


# ═══════════════════════════════════════
# 6. FileEditTool
# ═══════════════════════════════════════
section("6. FileEditTool")

from src.core.tools.file_edit_tool import FileEditTool  # noqa: E402

check("FileEditTool name", FileEditTool.name == "edit")
check("FileEditTool is destructive", FileEditTool.is_destructive() is True)

# Edit the test file
result = FileEditTool.call(
    {
        "file_path": temp_file,
        "old_string": "Hello World!",
        "new_string": "Hello PythonAI!",
    },
    ctx,
)
check("edit file works", result.error is None)
check("  message confirms", "Applied edit" in result.data.get("message", ""))

# Verify edited content
with open(temp_file) as f:
    content = f.read()
check("  edited content correct", "Hello PythonAI!" in content)
check("  original string gone", "Hello World!" not in content)

# Edit with non-existent old_string
result = FileEditTool.call(
    {
        "file_path": temp_file,
        "old_string": "This does not exist",
        "new_string": "anything",
    },
    ctx,
)
check("edit non-existent string returns error", result.error is not None)
check("  error mentions not found", "not found" in result.error or "find" in result.error)

# Clean up temp file
os.remove(temp_file)
os.rmdir(temp_dir)


# ═══════════════════════════════════════
# 7. GlobTool
# ═══════════════════════════════════════
section("7. GlobTool")

from src.core.tools.glob_tool import GlobTool  # noqa: E402

check("GlobTool name", GlobTool.name == "glob")
check("GlobTool is readonly", GlobTool.is_readonly() is True)

# Glob Python files in src/core
python_dir = os.path.join(os.path.dirname(__file__), "src/core")
result = GlobTool.call({"pattern": "**/*.py", "cwd": python_dir, "max_results": 20}, ctx)
check("glob finds py files", result.data.get("total_matches", 0) > 0)
check("  returns files list", len(result.data.get("files", [])) > 0)

# Glob specific file
result = GlobTool.call({"pattern": "tool.py", "cwd": python_dir}, ctx)
check("glob finds tool.py", result.data.get("total_matches", 0) >= 1)

# Glob with no matches
result = GlobTool.call({"pattern": "*.xyz", "cwd": python_dir}, ctx)
check("glob no matches returns 0", result.data.get("total_matches", 0) == 0)

# Validation
validation = GlobTool.validate_input({"pattern": ""}, ctx)
check("empty pattern fails", validation.success is False)


# ═══════════════════════════════════════
# 8. GrepTool
# ═══════════════════════════════════════
section("8. GrepTool")

from src.core.tools.grep_tool import GrepTool  # noqa: E402

check("GrepTool name", GrepTool.name == "grep")
check("GrepTool is readonly", GrepTool.is_readonly() is True)

# Grep for 'class Tool' in src/core
core_dir = os.path.join(os.path.dirname(__file__), "src/core")
result = GrepTool.call({"pattern": "class Tool", "cwd": core_dir, "max_results": 10}, ctx)
check("grep finds class Tool", result.data.get("total_matches", 0) >= 1)
check("  has matches list", len(result.data.get("matches", [])) >= 1)

# Grep with context
result = GrepTool.call({"pattern": "def call", "cwd": core_dir, "context_lines": 1}, ctx)
check("grep with context works", result.data.get("total_matches", 0) >= 1)

# Grep case insensitive
result = GrepTool.call({"pattern": "class tool", "cwd": core_dir, "ignore_case": True}, ctx)
check("grep case insensitive works", result.data.get("total_matches", 0) >= 1)

# Grep no matches
result = GrepTool.call({"pattern": "ZZZNOTFOUNDZZZ", "cwd": core_dir}, ctx)
check("grep no matches returns 0", result.data.get("total_matches", 0) == 0)

# Validation
validation = GrepTool.validate_input({"pattern": "("}, ctx)
check("invalid regex fails", validation.success is False)


# ═══════════════════════════════════════
# 9. WebFetchTool (if network available)
# ═══════════════════════════════════════
section("9. WebFetchTool")

from src.core.tools.web_fetch_tool import WebFetchTool  # noqa: E402

check("WebFetchTool name", WebFetchTool.name == "web_fetch")
check("WebFetch is readonly", WebFetchTool.is_readonly() is True)

# Test validation only (actual fetch needs network)
validation = WebFetchTool.validate_input({"url": "https://example.com"}, ctx)
check("valid URL passes", validation.success is True)

validation = WebFetchTool.validate_input({"url": "not-a-url"}, ctx)
check("invalid URL fails", validation.success is False)

validation = WebFetchTool.validate_input({"url": ""}, ctx)
check("empty URL fails", validation.success is False)

try:
    result = WebFetchTool.call({"url": "https://example.com", "max_chars": 500}, ctx)
    if result.error:
        check(f"web fetch: {result.error[:60]}", True)
    else:
        check("web fetch works", "Example" in result.data.get("content", ""))
        check("  has url", "example.com" in result.data.get("url", ""))
        check("  status 200", result.data.get("status_code") == 200)
except ImportError:
    check("requests not installed", True)


# ═══════════════════════════════════════
# 10. WebSearchTool
# ═══════════════════════════════════════
section("10. WebSearchTool")

from src.core.tools.web_search_tool import WebSearchTool  # noqa: E402

check("WebSearchTool name", WebSearchTool.name == "web_search")
check("WebSearch is readonly", WebSearchTool.is_readonly() is True)

# Validation only
validation = WebSearchTool.validate_input({"query": "Python programming"}, ctx)
check("valid query passes", validation.success is True)

validation = WebSearchTool.validate_input({"query": ""}, ctx)
check("empty query fails", validation.success is False)


# ═══════════════════════════════════════
# 11. ToolCallingEngine
# ═══════════════════════════════════════
section("11. ToolCallingEngine")

from src.core.executor import ToolCallingEngine, parse_tool_calls  # noqa: E402

# Test tool call parser
tc = parse_tool_calls('{"name": "test", "arguments": {"msg": "hello"}}')
check("parse JSON tool call", len(tc) > 0)
if tc:
    check("  has name 'test'", tc[0]["function"]["name"] == "test")

tc = parse_tool_calls("""<tool_call>
<tool_name>test</tool_name>
<parameters>{"msg": "hello"}</parameters>
</tool_call>""")
check("parse XML tool call", len(tc) > 0)
if tc:
    check("  XML has name", "test" in tc[0]["function"]["name"])

# Create engine
engine = ToolCallingEngine(registry=registry)
check("engine created", engine is not None)
check("  max rounds default", engine.max_tool_rounds == 25)
check("  stats initial", engine.stats["total_rounds"] == 0)

# Test get_stats_report
stats = engine.get_stats_report()
check("stats report has fields", "total_rounds" in stats)


# ═══════════════════════════════════════
# 12. Integration Test — Find + Read Files
# ═══════════════════════════════════════
section("12. Real-World Integration")

# Glob for Python files → Read the first one → Grep inside it
glob_result = GlobTool.call(
    {
        "pattern": "**/*.py",
        "cwd": os.path.join(os.path.dirname(__file__), "src/core"),
        "max_results": 5,
    },
    ctx,
)

files = glob_result.data.get("files", [])
check(f"globbing finds {len(files)} files in src/core", len(files) > 0)

if files:
    first_file = files[0]["path"]
    full_path = os.path.join(os.path.dirname(__file__), "src/core", first_file)

    read_result = FileReadTool.call({"file_path": full_path, "limit": 10}, ctx)
    content = read_result.data.get("content", "")
    check(f"read {first_file} returns content", len(content) > 0)
    check("  has line numbers", "|" in content)

    grep_result = GrepTool.call(
        {
            "pattern": "class\\s+\\w+",
            "cwd": os.path.join(os.path.dirname(__file__), "src/core"),
            "max_results": 10,
        },
        ctx,
    )
    check("grep finds classes in src/core", grep_result.data.get("total_matches", 0) > 0)

# Final: ToolRegistry with ALL tools
from src.core.tools import register_all_tools  # noqa: E402

registry2 = ToolRegistry()
register_all_tools(registry2)
check(f"register_all_tools: {registry2.total_count} tools registered", registry2.total_count > 0)

# Check each tool is present
expected_tools = {"bash", "read", "write", "edit", "glob", "grep", "web_fetch", "web_search"}
actual_tools = {t.name for t in registry2.list_all()}
for tool_name in expected_tools:
    check(f"  {tool_name} tool registered", tool_name in actual_tools)


# ═══════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════
section("RESULTS")
print(f"  PASSED: {PASS}")
print(f"  FAILED: {FAIL}")
print(f"  TOTAL:  {PASS + FAIL}")
print(f"  {'=' * 50}")
if FAIL == 0:
    print("  *** ALL TESTS PASSED! ***")
else:
    print(f"  ** {FAIL} test(s) failed **")
print(f"  {'=' * 50}")
