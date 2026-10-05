@echo off
setlocal
set "GUMMI_PROJECTILE_TEST_ROOT=%~dp0"
call "%~dp0..\..\..\trainer\setup-toolchain.cmd" > "%GUMMI_PROJECTILE_TEST_ROOT%gummi_projectile_toolchain.log" 2>&1
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /O2 /W4 /MT /EHsc /DUNICODE /D_UNICODE "%GUMMI_PROJECTILE_TEST_ROOT%GummiProjectileGuardTests.cpp" /Fo"%GUMMI_PROJECTILE_TEST_ROOT%GummiProjectileGuardTests.obj" /Fe"%GUMMI_PROJECTILE_TEST_ROOT%GummiProjectileGuardTests.exe" /link /INCREMENTAL:NO /DYNAMICBASE /NXCOMPAT
if errorlevel 1 exit /b 1
"%GUMMI_PROJECTILE_TEST_ROOT%GummiProjectileGuardTests.exe"
exit /b %ERRORLEVEL%
