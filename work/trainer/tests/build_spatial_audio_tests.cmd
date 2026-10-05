@echo off
setlocal
set "SPATIAL_AUDIO_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%SPATIAL_AUDIO_TEST_ROOT%spatial_audio_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%SPATIAL_AUDIO_TEST_ROOT%SpatialAudioGuardTests.cpp" /Fo"%SPATIAL_AUDIO_TEST_ROOT%SpatialAudioGuardTests.obj" /Fe"%SPATIAL_AUDIO_TEST_ROOT%SpatialAudioGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%SPATIAL_AUDIO_TEST_ROOT%SpatialAudioGuardTests.exe"
exit /b %ERRORLEVEL%
