@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo.
echo  === ISLAND SIMULATION ===
echo.
python run_simulation_live.py --rounds 5
echo.
pause
