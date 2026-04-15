@echo off
set PY=C:\Users\Sergiu\AppData\Local\Programs\Python\Python311\python.exe

echo Installing requirements into Python 3.11...
%PY% -m pip install uvicorn[standard] -r requirements.txt

echo.
echo Starting server with auto-reload...
echo Open browser console and run:
echo   localStorage.setItem("backendUrl", "http://localhost:8080/chat")
echo.
%PY% -m uvicorn app.server:app --host 0.0.0.0 --port 8080 --reload
