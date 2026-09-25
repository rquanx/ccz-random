@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /O2 /LD /DUNICODE /D_UNICODE ccz_control.c user32.lib /link /OUT:ccz_control.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /O2 /DUNICODE /D_UNICODE ccz_injector.c /link /SUBSYSTEM:CONSOLE /OUT:ccz_injector.exe
