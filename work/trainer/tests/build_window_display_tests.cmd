@echo off
setlocal
set "WINDOW_DISPLAY_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%WINDOW_DISPLAY_TEST_ROOT%window_display_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /DWINDOW_DISPLAY_PRODUCTION_COMPILE /c "%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayTests.cpp" /Fo"%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayProduction.obj"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayTests.cpp" /Fo"%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayTests.obj" /Fe"%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%WINDOW_DISPLAY_TEST_ROOT%WindowDisplayTests.exe"
exit /b %ERRORLEVEL%
