@echo off
setlocal
set "MOVEMENT_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%MOVEMENT_TEST_ROOT%actormovement_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%MOVEMENT_TEST_ROOT%ActorMovementGuardTests.cpp" /Fo"%MOVEMENT_TEST_ROOT%ActorMovementGuardTests.obj" /Fe"%MOVEMENT_TEST_ROOT%ActorMovementGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%MOVEMENT_TEST_ROOT%ActorMovementGuardTests.exe"
exit /b %ERRORLEVEL%
