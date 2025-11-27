Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d C:\Users\crist\OneDrive\Documentos\workspace\I_S25_Web_Scraping && venv_new\Scripts\pythonw.exe telegram_bot.py", 0, False
Set WshShell = Nothing
