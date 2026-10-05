@echo off
setlocal
set "MISSION_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%MISSION_TEST_ROOT%mission_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%MISSION_TEST_ROOT%MissionGuardTests.cpp" /Fo"%MISSION_TEST_ROOT%MissionGuardTests.obj" /Fe"%MISSION_TEST_ROOT%MissionGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%MISSION_TEST_ROOT%MissionGuardTests.exe"
exit /b %ERRORLEVEL%
