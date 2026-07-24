@echo off
REM ============================================
REM ForgeAI Researcher - Continuous Background Mode
REM ============================================
REM Runs the researcher's built-in continuous mode
REM (harvests & analyzes knowledge every 60 min).
REM Logs saved to researcher_continuous.log
REM Close window or press Ctrl+C to stop.
REM ============================================

cd /d "%~dp0"

echo [%date% %time%] Starting ForgeAI Researcher (continuous mode)...
echo [%date% %time%] Harvesting every 60 minutes...
echo [%date% %time%] Log: researcher_continuous.log
echo [%date% %time%] Press Ctrl+C or close window to stop.
echo.

python researcher.py continuous >> researcher_continuous.log 2>&1

echo [%date% %time%] Researcher stopped.
pause
