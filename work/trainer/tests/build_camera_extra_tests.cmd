@echo off
setlocal
set "CAMERA_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%CAMERA_TEST_ROOT%camera_extra_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%CAMERA_TEST_ROOT%CameraExtraGuardTests.cpp" /Fo"%CAMERA_TEST_ROOT%CameraExtraGuardTests.obj" /Fe"%CAMERA_TEST_ROOT%CameraExtraGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%CAMERA_TEST_ROOT%CameraExtraGuardTests.exe"
exit /b %ERRORLEVEL%
