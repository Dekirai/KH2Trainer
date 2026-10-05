@echo off
setlocal
set "MISSIONEVENT_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%MISSIONEVENT_TEST_ROOT%missionevents_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%MISSIONEVENT_TEST_ROOT%MissionEventGuardTests.cpp" /Fo"%MISSIONEVENT_TEST_ROOT%MissionEventGuardTests.obj" /Fe"%MISSIONEVENT_TEST_ROOT%MissionEventGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%MISSIONEVENT_TEST_ROOT%MissionEventGuardTests.exe"
exit /b %ERRORLEVEL%
