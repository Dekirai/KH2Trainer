@echo off
setlocal
call "%~dp0..\..\scripts\setup-toolchain.cmd" >nul
if errorlevel 1 exit /b %errorlevel%
if not exist "%~dp0bin" mkdir "%~dp0bin"
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%~dp0ActorLifetimeTests.cpp" /Fo"%~dp0bin\ActorLifetimeTests.obj" /Fe"%~dp0bin\ActorLifetimeTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b %errorlevel%
"%~dp0bin\ActorLifetimeTests.exe"
if errorlevel 1 exit /b %errorlevel%
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /DACTOR_LIFETIME_PRODUCTION_COMPILE /c "%~dp0ActorLifetimeTests.cpp" /Fo"%~dp0bin\ActorLifetimeProduction.obj"
exit /b %errorlevel%
