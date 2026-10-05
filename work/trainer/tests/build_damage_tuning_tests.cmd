@echo off
setlocal
set "DAMAGE_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%DAMAGE_TEST_ROOT%damage_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%DAMAGE_TEST_ROOT%DamageTuningTests.cpp" /Fo"%DAMAGE_TEST_ROOT%DamageTuningTests.obj" /Fe"%DAMAGE_TEST_ROOT%DamageTuningTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%DAMAGE_TEST_ROOT%DamageTuningTests.exe"
exit /b %ERRORLEVEL%
