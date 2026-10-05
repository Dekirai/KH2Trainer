@echo off
setlocal
set "GUMMI_EXTRA_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%GUMMI_EXTRA_TEST_ROOT%gummi_extra_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%GUMMI_EXTRA_TEST_ROOT%GummiExtraGuardTests.cpp" /Fo"%GUMMI_EXTRA_TEST_ROOT%GummiExtraGuardTests.obj" /Fe"%GUMMI_EXTRA_TEST_ROOT%GummiExtraGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%GUMMI_EXTRA_TEST_ROOT%GummiExtraGuardTests.exe"
exit /b %ERRORLEVEL%
