@echo off
setlocal
set "WORLD_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%WORLD_TEST_ROOT%world_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%WORLD_TEST_ROOT%WorldGuardTests.cpp" /Fo"%WORLD_TEST_ROOT%WorldGuardTests.obj" /Fe"%WORLD_TEST_ROOT%WorldGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT user32.lib
if errorlevel 1 exit /b 1
"%WORLD_TEST_ROOT%WorldGuardTests.exe"
exit /b %ERRORLEVEL%
