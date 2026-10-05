@echo off
setlocal
set "AUDIO_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%AUDIO_TEST_ROOT%audio_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%AUDIO_TEST_ROOT%AudioGuardTests.cpp" /Fo"%AUDIO_TEST_ROOT%AudioGuardTests.obj" /Fe"%AUDIO_TEST_ROOT%AudioGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%AUDIO_TEST_ROOT%AudioGuardTests.exe"
exit /b %ERRORLEVEL%
