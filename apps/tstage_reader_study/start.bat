@echo off
REM Start a local static-file server for the tstage_reader_study app.
REM Default port 8765.  Usage:  start.bat [port]
set PORT=%1
if "%PORT%"=="" set PORT=8765
cd /d %~dp0
echo Serving tstage_reader_study on http://127.0.0.1:%PORT%/
echo Pass 1 (no AI):    http://127.0.0.1:%PORT%/?reader=YOUR_ID^&pass=1
echo Pass 2 (with AI):  http://127.0.0.1:%PORT%/?reader=YOUR_ID^&pass=2
python -m http.server %PORT% --bind 127.0.0.1
