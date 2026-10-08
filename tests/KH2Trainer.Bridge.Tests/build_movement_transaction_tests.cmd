@echo off
setlocal
call "%~dp0..\..\scripts\setup-toolchain.cmd" >nul
if errorlevel 1 exit /b %errorlevel%
if not exist "%~dp0bin" mkdir "%~dp0bin"
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%~dp0MovementTransactionTests.cpp" /Fo"%~dp0bin\MovementTransactionTests.obj" /Fe"%~dp0bin\MovementTransactionTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b %errorlevel%
"%~dp0bin\MovementTransactionTests.exe"
exit /b %errorlevel%
