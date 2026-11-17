@echo off
REM Tyrobota agent - autostart (hidden via pythonw)
cd /d "C:\Users\Raketa\tyrobota-agent"
if not exist logs mkdir logs
"C:\Users\Raketa\tyrobota-agent\venv\Scripts\pythonw.exe" -m src.main
