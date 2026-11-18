@echo off
call "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Auxiliary\Build\vcvarsall.bat" x86
if errorlevel 1 exit /b %errorlevel%
cd /d "%~dp0"
cl /nologo /utf-8 /O2 /W4 /LD ccz_growth_patch.c ccz_growth_storage.c user32.lib bcrypt.lib /link /OUT:CCZFX.DLL
if errorlevel 1 exit /b %errorlevel%
cl /nologo /utf-8 /O2 /W4 test_growth_storage.c ccz_growth_storage.c /link /OUT:test_growth_storage.exe
if errorlevel 1 exit /b %errorlevel%
test_growth_storage.exe
