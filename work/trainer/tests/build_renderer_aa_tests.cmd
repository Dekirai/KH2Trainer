@echo off
setlocal
set "AA_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%AA_TEST_ROOT%renderer_aa_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE /DAA_PRODUCTION_COMPILE /c "%AA_TEST_ROOT%RendererAaTests.cpp" /Fo"%AA_TEST_ROOT%RendererAaProduction.obj"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%AA_TEST_ROOT%RendererAaTests.cpp" /Fo"%AA_TEST_ROOT%RendererAaTests.obj" /Fe"%AA_TEST_ROOT%RendererAaTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%AA_TEST_ROOT%RendererAaTests.exe"
exit /b %ERRORLEVEL%
