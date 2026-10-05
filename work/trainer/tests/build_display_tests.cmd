@echo off
setlocal
set "DISPLAY_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%DISPLAY_TEST_ROOT%display_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /c "%DISPLAY_TEST_ROOT%DisplayProductionCompile.cpp" /Fo"%DISPLAY_TEST_ROOT%DisplayProductionCompile.obj"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%DISPLAY_TEST_ROOT%DisplayGuardTests.cpp" /Fo"%DISPLAY_TEST_ROOT%DisplayGuardTests.obj" /Fe"%DISPLAY_TEST_ROOT%DisplayGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%DISPLAY_TEST_ROOT%DisplayGuardTests.exe"
exit /b %ERRORLEVEL%
