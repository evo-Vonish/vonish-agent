' VonishAgent Silent Launcher
' Usage: double-click this .vbs file or create a shortcut to it.
' Starts backend in background, opens browser. No console window.

Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Resolve paths relative to this script
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(scriptDir)
backEnd = root & "\backend\"
frontEnd = root & "\frontend\"
venvPython = backEnd & ".venv\Scripts\python.exe"
mainPy = backEnd & "main.py"
frontPort = "18473"
backPort = "18480"
url = "http://127.0.0.1:" & frontPort

' Check if venv exists
If Not fso.FileExists(venvPython) Then
    MsgBox "虚拟环境未找到: " & venvPython & vbCrLf & "请先安装: cd backend && python -m venv .venv && .venv\Scripts\pip install -r requirements.txt", 48, "VonishAgent"
    WScript.Quit 1
End If

' Check if already running
checkCmd = "netstat -ano | findstr "":" & backPort & ".*LISTENING"""
Set exec = WshShell.Exec("cmd /c " & checkCmd)
output = exec.StdOut.ReadAll()
If InStr(output, backPort) = 0 Then
    ' Start backend
    WshShell.Run "cmd /c cd /d """ & backEnd & """ && """ & venvPython & """ """ & mainPy & """ > server.out.log 2> server.err.log", 0, False
    WScript.Sleep 3000
End If

' Start frontend if needed
frontCheckCmd = "netstat -ano | findstr "":" & frontPort & ".*LISTENING"""
Set frontExec = WshShell.Exec("cmd /c " & frontCheckCmd)
frontOutput = frontExec.StdOut.ReadAll()
If InStr(frontOutput, frontPort) = 0 Then
    WshShell.Run "cmd /c cd /d """ & frontEnd & """ && npm.cmd run dev > vite.out.log 2> vite.err.log", 0, False
    WScript.Sleep 3000
End If

' Open browser
WshShell.Run "cmd /c start """" """ & url & """", 0, False
