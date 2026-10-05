@echo off
setlocal
set "TARGET_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%TARGET_TEST_ROOT%targeting_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%TARGET_TEST_ROOT%TargetingGuardTests.cpp" /Fo"%TARGET_TEST_ROOT%TargetingGuardTests.obj" /Fe"%TARGET_TEST_ROOT%TargetingGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%TARGET_TEST_ROOT%TargetingGuardTests.exe"
exit /b %ERRORLEVEL%
