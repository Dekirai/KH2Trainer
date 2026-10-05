@echo off
setlocal
set "MOTION_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%MOTION_TEST_ROOT%motion_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%MOTION_TEST_ROOT%MotionGuardTests.cpp" /Fo"%MOTION_TEST_ROOT%MotionGuardTests.obj" /Fe"%MOTION_TEST_ROOT%MotionGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%MOTION_TEST_ROOT%MotionGuardTests.exe"
exit /b %ERRORLEVEL%
