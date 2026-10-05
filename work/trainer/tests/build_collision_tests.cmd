@echo off
setlocal
set "COLLISION_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%COLLISION_TEST_ROOT%collision_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%COLLISION_TEST_ROOT%CollisionGuardTests.cpp" /Fo"%COLLISION_TEST_ROOT%CollisionGuardTests.obj" /Fe"%COLLISION_TEST_ROOT%CollisionGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%COLLISION_TEST_ROOT%CollisionGuardTests.exe"
exit /b %ERRORLEVEL%
