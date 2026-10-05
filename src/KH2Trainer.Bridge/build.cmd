@echo off
setlocal
rem Builds bin\KH2Trainer.Bridge.dll with the MSVC toolchain.
rem KH2Trainer.csproj runs this automatically when a bridge source changed.
set "BRIDGE_ROOT=%~dp0"
set "BRIDGE_BIN=%BRIDGE_ROOT%bin\"
set "BRIDGE_OBJ=%BRIDGE_ROOT%obj\"
if not exist "%BRIDGE_BIN%" mkdir "%BRIDGE_BIN%"
if not exist "%BRIDGE_OBJ%" mkdir "%BRIDGE_OBJ%"
call "%BRIDGE_ROOT%..\..\scripts\setup-toolchain.cmd" > "%BRIDGE_OBJ%toolchain.log" 2>&1
if errorlevel 1 (
  type "%BRIDGE_OBJ%toolchain.log"
  exit /b 1
)
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /LD "%BRIDGE_ROOT%TrainerBridge.cpp" /Fo"%BRIDGE_OBJ%TrainerBridge.obj" /Fe"%BRIDGE_BIN%KH2Trainer.Bridge.dll" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT /IMPLIB:"%BRIDGE_OBJ%KH2Trainer.Bridge.lib" user32.lib
exit /b %ERRORLEVEL%
