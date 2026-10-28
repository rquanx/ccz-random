@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /O2 /LD /DUNICODE /D_UNICODE ccz_control.c user32.lib /link /OUT:ccz_control.dll
if errorlevel 1 exit /b %errorlevel%
cl /nologo /O2 /DUNICODE /D_UNICODE ccz_injector.c /link /SUBSYSTEM:CONSOLE /OUT:ccz_injector.exe
if errorlevel 1 exit /b %errorlevel%
rc /nologo /fo ccz_audio_launcher.res ccz_audio_launcher.rc
if errorlevel 1 exit /b %errorlevel%
cl /nologo /utf-8 /O2 /DUNICODE /D_UNICODE ccz_audio_launcher.c ccz_audio_launcher.res user32.lib shell32.lib /link /SUBSYSTEM:WINDOWS /OUT:ccz_audio_launcher.exe
