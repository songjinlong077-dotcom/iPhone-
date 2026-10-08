@echo off
set PYTHONUTF8=1
set PIP_PROGRESS_BAR=off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" "03_工作过程\verify_mp4_integration.py"
if errorlevel 1 goto :failed
".venv\Scripts\python.exe" "03_工作过程\verify_v2_acceptance.py"
if errorlevel 1 goto :failed
echo.
echo All tests passed.
pause
exit /b 0

:failed
echo.
echo Tests failed. See the output above.
pause
exit /b 1
