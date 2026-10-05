@echo off
setlocal
set "RENDER_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%RENDER_TEST_ROOT%render_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%RENDER_TEST_ROOT%RenderGuardTests.cpp" /Fo"%RENDER_TEST_ROOT%RenderGuardTests.obj" /Fe"%RENDER_TEST_ROOT%RenderGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%RENDER_TEST_ROOT%RenderGuardTests.exe"
exit /b %ERRORLEVEL%
