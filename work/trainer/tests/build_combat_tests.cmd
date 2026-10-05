@echo off
setlocal
set "COMBAT_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%COMBAT_TEST_ROOT%combat_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%COMBAT_TEST_ROOT%CombatGuardTests.cpp" /Fo"%COMBAT_TEST_ROOT%CombatGuardTests.obj" /Fe"%COMBAT_TEST_ROOT%CombatGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%COMBAT_TEST_ROOT%CombatGuardTests.exe"
exit /b %ERRORLEVEL%
