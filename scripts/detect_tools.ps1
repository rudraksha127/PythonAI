# Detect all installed runtimes, CLIs, databases, and SDKs

$tools = @(
    'git', 'gh', 'docker', 'kubectl', 'aws', 'gcloud', 'az',
    'python', 'node', 'npm', 'npx', 'uv', 'uvx', 'pip', 'go',
    'rustc', 'cargo', 'java', 'javac', 'sqlite3', 'ollama',
    'ffmpeg', 'curl', 'wget', 'pnpm', 'yarn', 'bun'
)

Write-Host "=====================================================" -ForegroundColor Cyan
Write-Host " SYSTEM TOOL & RUNTIME AUDIT " -ForegroundColor Cyan
Write-Host "=====================================================" -ForegroundColor Cyan

foreach ($t in $tools) {
    $cmd = Get-Command $t -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host (" [FOUND]   {0,-12} -> {1}" -f $t, $cmd.Source) -ForegroundColor Green
    } else {
        Write-Host (" [MISSING] {0,-12}" -f $t) -ForegroundColor DarkGray
    }
}
