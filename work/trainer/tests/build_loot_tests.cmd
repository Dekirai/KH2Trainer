@echo off
setlocal
set "LOOT_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%LOOT_TEST_ROOT%loot_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%LOOT_TEST_ROOT%LootGuardTests.cpp" /Fo"%LOOT_TEST_ROOT%LootGuardTests.obj" /Fe"%LOOT_TEST_ROOT%LootGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%LOOT_TEST_ROOT%LootGuardTests.exe"
exit /b %ERRORLEVEL%
