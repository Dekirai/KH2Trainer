@echo off
setlocal
set "RENDERER_DIAG_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%RENDERER_DIAG_TEST_ROOT%renderer_diagnostics_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /DRENDERER_PRODUCTION_COMPILE /c "%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsTests.cpp" /Fo"%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsProduction.obj"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsTests.cpp" /Fo"%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsTests.obj" /Fe"%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%RENDERER_DIAG_TEST_ROOT%RendererDiagnosticsTests.exe"
exit /b %ERRORLEVEL%
