@echo off
setlocal
set "DRIVE_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%DRIVE_TEST_ROOT%drive_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%DRIVE_TEST_ROOT%DriveGuardTests.cpp" /Fo"%DRIVE_TEST_ROOT%DriveGuardTests.obj" /Fe"%DRIVE_TEST_ROOT%DriveGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%DRIVE_TEST_ROOT%DriveGuardTests.exe"
exit /b %ERRORLEVEL%
