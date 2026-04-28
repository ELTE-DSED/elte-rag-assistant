param(
    [string]$SourceDir = "recources/architecture/split",
    [string]$OutputDir = "documentation/images/architecture",
    [string]$PlantUmlJar = "",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

function Resolve-PlantUmlJarPath {
    param([string]$ExplicitPath)

    if ($ExplicitPath -and (Test-Path -LiteralPath $ExplicitPath)) {
        return (Resolve-Path -LiteralPath $ExplicitPath).Path
    }

    $candidatePaths = @(
        "$env:LOCALAPPDATA\PlantUML\plantuml.jar",
        "$env:USERPROFILE\.plantuml\plantuml.jar",
        "tools/plantuml/plantuml.jar"
    )

    foreach ($candidate in $candidatePaths) {
        if (Test-Path -LiteralPath $candidate) {
            return (Resolve-Path -LiteralPath $candidate).Path
        }
    }

    throw "PlantUML jar was not found. Download it to one of: $($candidatePaths -join ', ') or pass -PlantUmlJar."
}

function Assert-CommandExists {
    param([string]$CommandName, [string]$InstallHint)

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $command) {
        if ($CommandName -eq "dot") {
            $graphvizBin = "C:\Program Files\Graphviz\bin"
            $graphvizDot = Join-Path $graphvizBin "dot.exe"
            if (Test-Path -LiteralPath $graphvizDot) {
                if ($env:Path -notlike "*$graphvizBin*") {
                    $env:Path = "$graphvizBin;$env:Path"
                }
                $command = Get-Command $CommandName -ErrorAction SilentlyContinue
            }
        }
    }
    if (-not $command) {
        throw "$CommandName was not found on PATH. $InstallHint"
    }
    return $command.Source
}

$resolvedSourceDir = (Resolve-Path -LiteralPath $SourceDir).Path
if (-not (Test-Path -LiteralPath $resolvedSourceDir)) {
    throw "Source directory not found: $SourceDir"
}

$resolvedOutputDir = Join-Path (Get-Location) $OutputDir
New-Item -ItemType Directory -Force -Path $resolvedOutputDir | Out-Null
$resolvedOutputDir = (Resolve-Path -LiteralPath $resolvedOutputDir).Path

$javaPath = Assert-CommandExists -CommandName "java" -InstallHint "Install a JDK/JRE and ensure java.exe is on PATH."
$dotPath = Assert-CommandExists -CommandName "dot" -InstallHint "Install Graphviz (winget install Graphviz.Graphviz) and reopen the shell."
$jarPath = Resolve-PlantUmlJarPath -ExplicitPath $PlantUmlJar

$pumlFiles = Get-ChildItem -LiteralPath $resolvedSourceDir -Filter "*.puml" -File | Sort-Object Name
if (-not $pumlFiles) {
    throw "No .puml files found in $resolvedSourceDir"
}

Write-Host "Java:      $javaPath"
Write-Host "Graphviz:  $dotPath"
Write-Host "PlantUML:  $jarPath"
Write-Host "SourceDir: $resolvedSourceDir"
Write-Host "OutputDir: $resolvedOutputDir"

foreach ($file in $pumlFiles) {
    & java "-Djava.awt.headless=true" -jar $jarPath -checkonly $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "PlantUML check failed for $($file.FullName)"
    }
}

if ($CheckOnly) {
    Write-Host "Check-only mode complete. All diagrams are syntactically valid."
    exit 0
}

foreach ($file in $pumlFiles) {
    & java "-Djava.awt.headless=true" -jar $jarPath -tpng -o $resolvedOutputDir $file.FullName
    if ($LASTEXITCODE -ne 0) {
        throw "PlantUML render failed for $($file.FullName)"
    }
}

$missing = @()
foreach ($file in $pumlFiles) {
    $expectedPng = Join-Path $resolvedOutputDir ("{0}.png" -f [System.IO.Path]::GetFileNameWithoutExtension($file.Name))
    if (-not (Test-Path -LiteralPath $expectedPng)) {
        $missing += $expectedPng
    }
}

if ($missing.Count -gt 0) {
    throw "Rendering completed with missing PNG outputs: $($missing -join ', ')"
}

Write-Host "Rendered $($pumlFiles.Count) architecture diagrams to $resolvedOutputDir"
