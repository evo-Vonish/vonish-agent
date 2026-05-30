' VonishAgent Silent Launcher
' Usage: double-click this .vbs file or create a shortcut to it.
' Starts backend in background, opens browser. No console window.

Set WshShell = CreateObject("WScript.Shell")

' Resolve paths relative to this script
scriptDir = WshShell.CurrentDirectory & "\"
backEnd = scriptDir & "backend\"
venvPython = backEnd & ".venv\Scripts\python.exe"
mainPy = backEnd & "main.py"
url = "http://127.0.0.1:8000"

' Check if venv exists
Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(venvPython) Then
    MsgBox "虚拟环境未找到: " & venvPython & vbCrLf & "请先安装: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt", 48, "VonishAgent"
    WScript.Quit 1
End If

' Check if already running
checkCmd = "netstat -ano | findstr "":8000.*LISTENING"""
Set exec = WshShell.Exec("cmd /c " & checkCmd)
output = exec.StdOut.ReadAll()
If InStr(output, "8000") > 0 Then
    ' Already running — just open browser
    WshShell.Run "cmd /c start """" """ & url & """", 0, False
    WScript.Quit 0
End If

' Start backend
WshShell.Run "cmd /c cd /d """ & backEnd & """ && """ & venvPython & """ """ & mainPy & """ > backend.log 2>&1", 0, False

' Wait for backend to be ready
WScript.Sleep 3000

' Open browser
WshShell.Run "cmd /c start """" """ & url & """", 0, False
