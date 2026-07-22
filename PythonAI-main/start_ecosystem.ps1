# ===============================================================
# ForgeAI Ecosystem - Unified PowerShell Launcher
# ===============================================================

$ErrorActionPreference = "Stop"

# Colors for output
function Write-Header ($text) {
    Write-Host "`n=== $text ===" -ForegroundColor Cyan
}
function Write-Success ($text) {
    Write-Host "[SUCCESS] $text" -ForegroundColor Green
}
function Write-Warn ($text) {
    Write-Host "[WARNING] $text" -ForegroundColor Yellow
}

# Determine script root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Header "ForgeAI Ecosystem Check and Setup"

# 1. Check PythonAI Server (Port 7337)
$PythonAIVenv = Join-Path $ScriptDir "PythonAI\.venv"
$PythonAIExecutable = Join-Path $PythonAIVenv "Scripts\python.exe"

if (-not (Test-Path $PythonAIExecutable)) {
    throw "PythonAI virtual environment not found. Please run setup first."
}

# 2. Setup Rudra-bots (Odysseus Database)
Write-Header "Setting up Rudra-bots Database"
Set-Location (Join-Path $ScriptDir "Rudra-bots-main")
Write-Host "Initializing databases with PythonAI virtual environment..."
& $PythonAIExecutable setup.py
Write-Success "Rudra-bots database initialized."

# 3. Setup Hermes Studio Node modules if missing
Write-Header "Setting up Hermes Studio Dependencies"
Set-Location (Join-Path $ScriptDir "Hermes-studio--main")
if (-not (Test-Path "node_modules")) {
    Write-Warn "node_modules missing in Hermes Studio. Running install..."
    # Check if pnpm is available, fallback to npm
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        & pnpm install
    } else {
        & npm install
    }
    Write-Success "Hermes Studio dependencies installed."
} else {
    Write-Success "Hermes Studio dependencies already present."
}

# 4. Launch Services
Write-Header "Launching Ecosystem Services in Background"

function Start-ServiceBackground ($Name, $Command, $Arguments, $WorkingDir, $LogFile) {
    $LogPath = Join-Path $ScriptDir $LogFile
    $OutLog = $LogPath.Replace(".log", ".out.log")
    $ErrLog = $LogPath.Replace(".log", ".err.log")
    Write-Host "Starting $Name - logs: $LogFile (stdout/stderr separated)" -ForegroundColor DarkGray
    
    $RealCommand = $Command
    $RealArgs = $Arguments
    if ($Command -eq "npm" -or $Command -eq "pnpm") {
        $RealCommand = "cmd.exe"
        $RealArgs = "/c $Command $Arguments"
    }
    
    # Run the command with redirection using Start-Process
    Start-Process -FilePath $RealCommand -ArgumentList $RealArgs -WorkingDirectory $WorkingDir -NoNewWindow -RedirectStandardOutput $OutLog -RedirectStandardError $ErrLog
}

# 4.1 Launch PythonAI Server (if not running)
$Port7337InUse = Get-NetTCPConnection -LocalPort 7337 -ErrorAction SilentlyContinue
if ($Port7337InUse) {
    Write-Success "PythonAI Server already running on port 7337."
} else {
    Start-ServiceBackground -Name "PythonAI Server" -Command $PythonAIExecutable -Arguments "-m src.api.server" -WorkingDir (Join-Path $ScriptDir "PythonAI") -LogFile "pythonai-server.log"
}

# 4.2 Launch Next.js Dashboard (if not running)
$Port3000InUse = Get-NetTCPConnection -LocalPort 3000 -ErrorAction SilentlyContinue
if ($Port3000InUse) {
    Write-Success "Next.js Dashboard already running on port 3000."
} else {
    Start-ServiceBackground -Name "Next.js Dashboard" -Command "npm" -Arguments "run dev" -WorkingDir (Join-Path $ScriptDir "dashboard") -LogFile "dashboard-server.log"
}

# 4.3 Launch Unified Gateway (Port 8000)
$Port8000InUse = Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue
if ($Port8000InUse) {
    Write-Warn "Port 8000 already in use. Skipping Unified Gateway launch."
} else {
    Start-ServiceBackground -Name "Unified Gateway" -Command $PythonAIExecutable -Arguments "-m src.integration.gateway --port 8000" -WorkingDir (Join-Path $ScriptDir "PythonAI") -LogFile "gateway-server.log"
}

# 4.4 Launch Rudra-bots Server (Port 7000)
$Port7000InUse = Get-NetTCPConnection -LocalPort 7000 -ErrorAction SilentlyContinue
if ($Port7000InUse) {
    Write-Warn "Port 7000 already in use. Skipping Rudra-bots launch."
} else {
    Start-ServiceBackground -Name "Rudra-bots Server" -Command $PythonAIExecutable -Arguments "-m uvicorn app:app --port 7000" -WorkingDir (Join-Path $ScriptDir "Rudra-bots-main") -LogFile "rudra-bots-server.log"
}

# 4.5 Launch Hermes Agent (Port 8642)
$Port8642InUse = Get-NetTCPConnection -LocalPort 8642 -ErrorAction SilentlyContinue
if ($Port8642InUse) {
    Write-Warn "Port 8642 already in use. Skipping Hermes Agent launch."
} else {
    $HermesVenv = Join-Path $ScriptDir "hermes-agent-main\.venv312"
    $HermesPython = Join-Path $HermesVenv "Scripts\python.exe"
    if (-not (Test-Path $HermesPython)) {
        # Fallback to standard venv if venv312 is not there
        $HermesPython = Join-Path $ScriptDir "hermes-agent-main\.venv\Scripts\python.exe"
    }
    Start-ServiceBackground -Name "Hermes Agent" -Command $HermesPython -Arguments "-m gateway.run" -WorkingDir (Join-Path $ScriptDir "hermes-agent-main") -LogFile "hermes-agent.log"
}

# 4.6 Launch Hermes Studio (Port 3002)
$Port3002InUse = Get-NetTCPConnection -LocalPort 3002 -ErrorAction SilentlyContinue
if ($Port3002InUse) {
    Write-Warn "Port 3002 already in use. Skipping Hermes Studio launch."
} else {
    # Determine Node execution command
    $Command = "npm"
    $Args = "run dev -- --port 3002"
    if (Get-Command pnpm -ErrorAction SilentlyContinue) {
        $Command = "pnpm"
        $Args = "dev --port 3002"
    }
    Start-ServiceBackground -Name "Hermes Studio" -Command $Command -Arguments $Args -WorkingDir (Join-Path $ScriptDir "Hermes-studio--main") -LogFile "hermes-studio.log"
}

Write-Header "Ecosystem Launch Completed"
Write-Host "Services started! Please wait a few seconds for health checks to initialize."
Write-Host "You can monitor live status in Next.js dashboard at: http://localhost:3000/ecosystem" -ForegroundColor Cyan
