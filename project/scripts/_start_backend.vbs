' Start backend silently
Set WshShell = CreateObject("WScript.Shell")
backend = "F:\Projects\VonishAgent\project\backend"
python = backend & "\.venv\Scripts\python.exe"
WshShell.Run "cmd /c cd /d """ & backend & """ && """ & python & """ -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload > backend.log 2>&1"", 0, False
