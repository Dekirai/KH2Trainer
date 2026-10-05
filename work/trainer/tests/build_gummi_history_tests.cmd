@echo off
setlocal
set "GUMMI_HISTORY_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%GUMMI_HISTORY_TEST_ROOT%gummi_history_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%GUMMI_HISTORY_TEST_ROOT%GummiHistoryGuardTests.cpp" /Fo"%GUMMI_HISTORY_TEST_ROOT%GummiHistoryGuardTests.obj" /Fe"%GUMMI_HISTORY_TEST_ROOT%GummiHistoryGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%GUMMI_HISTORY_TEST_ROOT%GummiHistoryGuardTests.exe"
exit /b %ERRORLEVEL%
