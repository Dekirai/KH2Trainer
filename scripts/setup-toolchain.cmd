@echo off
rem Called inside each build script's setlocal scope.
set "KH2_VSROOT="
if defined VSINSTALLDIR if exist "%VSINSTALLDIR%VC\Auxiliary\Build\vcvarsall.bat" set "KH2_VSROOT=%VSINSTALLDIR%"
set "KH2_VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not defined KH2_VSROOT if exist "%KH2_VSWHERE%" for /f "usebackq delims=" %%I in (`"%KH2_VSWHERE%" -latest -prerelease -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "KH2_VSROOT=%%I\"
if not defined KH2_VSROOT (
  echo Install Visual Studio Build Tools with Desktop development with C++ and the Windows SDK.
  exit /b 1
)
call "%KH2_VSROOT%VC\Auxiliary\Build\vcvarsall.bat" x64
exit /b %ERRORLEVEL%
