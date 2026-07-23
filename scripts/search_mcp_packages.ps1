# Script to test candidate MCP package availability on NPM and PyPI

$nodeCandidates = @(
    "@modelcontextprotocol/server-filesystem",
    "@modelcontextprotocol/server-memory",
    "@modelcontextprotocol/server-sequential-thinking",
    "@modelcontextprotocol/server-puppeteer",
    "@modelcontextprotocol/server-everything",
    "@modelcontextprotocol/server-postgres",
    "@modelcontextprotocol/server-github",
    "@modelcontextprotocol/server-gitlab",
    "@modelcontextprotocol/server-google-maps",
    "@modelcontextprotocol/server-slack",
    "@modelcontextprotocol/server-brave-search",
    "mcp-server-sqlite",
    "mcp-server-fetch",
    "mcp-server-ollama",
    "mcp-server-docker"
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " NPM MCP PACKAGE VERIFICATION " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

foreach ($pkg in $nodeCandidates) {
    $info = npm info $pkg name 2>&1
    if ($info -and $info -notlike "*npm error*") {
        Write-Host (" [NPM AVAILABLE] {0}" -f $pkg) -ForegroundColor Green
    } else {
        Write-Host (" [NPM NOT FOUND] {0}" -f $pkg) -ForegroundColor DarkGray
    }
}

$pyCandidates = @(
    "mcp-server-git",
    "mcp-server-redis",
    "mcp-server-qdrant",
    "mcp-server-sqlite",
    "mcp-server-docker",
    "mcp-server-ollama",
    "mcp-server-fetch",
    "mcp-server-time"
)

Write-Host "`n=====================================================" -ForegroundColor Cyan
Write-Host " PYPI MCP PACKAGE VERIFICATION " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

foreach ($pkg in $pyCandidates) {
    $res = uv pip install --dry-run $pkg 2>&1
    if ($LASTEXITCODE -eq 0 -or $res -like "*Would install*" -or $res -like "*Satisfied*") {
        Write-Host (" [PYPI AVAILABLE] {0}" -f $pkg) -ForegroundColor Green
    } else {
        Write-Host (" [PYPI NOT FOUND] {0}" -f $pkg) -ForegroundColor DarkGray
    }
}
