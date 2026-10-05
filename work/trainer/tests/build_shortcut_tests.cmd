@echo off
setlocal
set "SHORTCUT_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%SHORTCUT_TEST_ROOT%shortcut_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%SHORTCUT_TEST_ROOT%ShortcutTests.cpp" /Fo"%SHORTCUT_TEST_ROOT%ShortcutTests.obj" /Fe"%SHORTCUT_TEST_ROOT%ShortcutTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT user32.lib
if errorlevel 1 exit /b 1
"%SHORTCUT_TEST_ROOT%ShortcutTests.exe"
exit /b %ERRORLEVEL%
