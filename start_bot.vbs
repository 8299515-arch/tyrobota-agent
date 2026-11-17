Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\Raketa\tyrobota-agent"
WshShell.Run """C:\Users\Raketa\tyrobota-agent\venv\Scripts\pythonw.exe"" -m src.main", 0, False
