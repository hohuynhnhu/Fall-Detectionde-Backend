@echo off
title Fall Detection — Backend API
echo ============================================
echo   FALL DETECTION BACKEND
echo   FastAPI + SQLite
echo ============================================
echo.

if not exist "venv\Scripts\activate.bat" (
    echo [SETUP] Tao virtual environment...
    python -m venv venv
    echo.
)

call venv\Scripts\activate.bat

echo [SETUP] Kiem tra / cai packages...
pip install -r requirements.txt -q
echo.

echo [RUN] Backend dang chay...
echo.
echo   API docs  : http://localhost:8000/docs
echo   Dashboard : http://localhost:8000/dashboard
echo   Health    : http://localhost:8000/health
echo.

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

pause
