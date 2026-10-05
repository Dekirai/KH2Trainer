@echo off
setlocal
set "PROGRESSION_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%PROGRESSION_TEST_ROOT%progression_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%PROGRESSION_TEST_ROOT%ProgressionTests.cpp" /Fo"%PROGRESSION_TEST_ROOT%ProgressionTests.obj" /Fe"%PROGRESSION_TEST_ROOT%ProgressionTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%PROGRESSION_TEST_ROOT%ProgressionTests.exe"
exit /b %ERRORLEVEL%
