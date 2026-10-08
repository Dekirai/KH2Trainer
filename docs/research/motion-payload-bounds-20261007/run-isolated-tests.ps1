$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$testRoot = Join-Path $repoRoot 'artifacts\research\motion-payload-bounds-20261007\isolated'
New-Item -ItemType Directory -Path $testRoot -Force | Out-Null
$sourceGlob = [System.Security.SecurityElement]::Escape((Join-Path $repoRoot 'src\KH2Trainer.Core\Motion*.cs'))
$testPath = [System.Security.SecurityElement]::Escape((Join-Path $repoRoot 'tests\KH2Trainer.Core.Tests\MotionPayloadTests.cs'))
$project = @"
<Project Sdk="Microsoft.NET.Sdk">
<PropertyGroup><TargetFramework>net8.0-windows</TargetFramework><OutputType>Exe</OutputType><EnableDefaultCompileItems>false</EnableDefaultCompileItems><TreatWarningsAsErrors>true</TreatWarningsAsErrors></PropertyGroup>
<ItemGroup><Compile Include="$sourceGlob"/><Compile Include="$testPath"/><Compile Include="Program.cs"/></ItemGroup>
</Project>
"@
Set-Content -LiteralPath (Join-Path $testRoot 'MotionTests.csproj') -Value $project -Encoding utf8
Set-Content -LiteralPath (Join-Path $testRoot 'Program.cs') -Value @'
int checks=0, failures=0;
try { MotionPayloadTests.Run((ok,name)=>{checks++;if(!ok){failures++;System.Console.WriteLine("FAIL "+name);}}); }
catch(System.Exception e){failures++;System.Console.WriteLine(e);}
System.Console.WriteLine($"Motion tests: {checks} checks, {failures} failures.");
return failures==0?0:1;
'@ -Encoding utf8
& dotnet run --project (Join-Path $testRoot 'MotionTests.csproj') -c Release 2>&1 | Tee-Object -FilePath (Join-Path $PSScriptRoot 'tests.txt')
if ($LASTEXITCODE -ne 0) { throw 'Isolated Motion tests failed.' }
