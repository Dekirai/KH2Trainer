@echo off
setlocal
set "KH2_REVIEW_SOURCE=%~dp0"
set "KH2_REVIEW_OUTPUT=%~dp0..\..\..\artifacts\mission-counter-integration-arithmetic-v01215\"
if not exist "%KH2_REVIEW_OUTPUT%" mkdir "%KH2_REVIEW_OUTPUT%"
call "%~dp0..\..\..\scripts\setup-toolchain.cmd"
if errorlevel 1 exit /b 1
cl /nologo /std:c++17 /EHsc /W4 /WX /O2 "%KH2_REVIEW_SOURCE%ArithmeticReview.cpp" /Fe:"%KH2_REVIEW_OUTPUT%ArithmeticReview.exe" /Fo:"%KH2_REVIEW_OUTPUT%ArithmeticReview.obj"
if errorlevel 1 exit /b 1
"%KH2_REVIEW_OUTPUT%ArithmeticReview.exe" > "%KH2_REVIEW_OUTPUT%arithmetic-result.json"
if errorlevel 1 exit /b 1
type "%KH2_REVIEW_OUTPUT%arithmetic-result.json"
