@echo off
setlocal
set "GUMMI_EDITOR_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%GUMMI_EDITOR_TEST_ROOT%gummi_editor_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%GUMMI_EDITOR_TEST_ROOT%GummiEditorGuardTests.cpp" /Fo"%GUMMI_EDITOR_TEST_ROOT%GummiEditorGuardTests.obj" /Fe"%GUMMI_EDITOR_TEST_ROOT%GummiEditorGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%GUMMI_EDITOR_TEST_ROOT%GummiEditorGuardTests.exe"
exit /b %ERRORLEVEL%
