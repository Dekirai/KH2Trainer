@echo off
setlocal
set "PLAYER_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%PLAYER_TEST_ROOT%player_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%PLAYER_TEST_ROOT%PlayerBridgeTests.cpp" /Fo"%PLAYER_TEST_ROOT%PlayerBridgeTests.obj" /Fe"%PLAYER_TEST_ROOT%PlayerBridgeTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT user32.lib
if errorlevel 1 exit /b 1
"%PLAYER_TEST_ROOT%PlayerBridgeTests.exe"
exit /b %ERRORLEVEL%
