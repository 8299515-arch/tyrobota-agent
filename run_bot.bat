@echo off
REM Tyrobota agent - autostart wrapper with error log (for Task Scheduler debug)
cd /d "C:\Users\Raketa\tyrobota-agent"
if not exist logs mkdir logs
echo [%DATE% %TIME%] starting bot >> logs\task.log
"C:\Users\Raketa\tyrobota-agent\venv\Scripts\python.exe" -u -m src.main >> logs\task.log 2>&1
echo [%DATE% %TIME%] exit code %ERRORLEVEL% >> logs\task.log
