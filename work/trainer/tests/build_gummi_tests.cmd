@echo off
setlocal
set "GUMMI_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%GUMMI_TEST_ROOT%gummi_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%GUMMI_TEST_ROOT%GummiGuardTests.cpp" /Fo"%GUMMI_TEST_ROOT%GummiGuardTests.obj" /Fe"%GUMMI_TEST_ROOT%GummiGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%GUMMI_TEST_ROOT%GummiGuardTests.exe"
exit /b %ERRORLEVEL%
