@echo off
setlocal
set "TASK_ROOT=%~dp0"
set "TASK_BUILD=%TASK_ROOT%Native\build\"
if not exist "%TASK_BUILD%" mkdir "%TASK_BUILD%"
call "%TASK_ROOT%setup-toolchain.cmd" > "%TASK_BUILD%toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /LD "%TASK_ROOT%Native\TrainerBridge.cpp" /Fo"%TASK_BUILD%TrainerBridge.obj" /Fe"%TASK_BUILD%KH2Trainer.Bridge.dll" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /IMPLIB:"%TASK_BUILD%KH2Trainer.Bridge.lib" user32.lib
exit /b %ERRORLEVEL%
