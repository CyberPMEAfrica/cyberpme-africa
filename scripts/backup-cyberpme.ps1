[CmdletBinding()]
param(
    [string]$Destination = "V:\CyberPME-Backups",
    [int]$RetentionDays = 14
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$filesDirectory = Join-Path $Destination "Fichiers"
$databaseDirectory = Join-Path $Destination "PostgreSQL"
$filesArchive = Join-Path $filesDirectory "cyberpme-source-$timestamp.zip"
$databaseArchive = Join-Path $databaseDirectory "cyberpme-db-$timestamp.dump"
$containerDump = "/tmp/cyberpme-db-$timestamp.dump"

New-Item -ItemType Directory -Force -Path $filesDirectory, $databaseDirectory | Out-Null

Write-Host "Création de l'archive des fichiers..."
Push-Location $projectRoot
try {
    & git archive --format=zip --output=$filesArchive HEAD
    if ($LASTEXITCODE -ne 0) { throw "La création de l'archive des fichiers a échoué." }

    Write-Host "Création du dump PostgreSQL..."
    & docker compose exec -T database pg_dump -U cyberpme -d cyberpme --format=custom --file=$containerDump
    if ($LASTEXITCODE -ne 0) { throw "pg_dump a échoué." }
    & docker compose cp "database:$containerDump" $databaseArchive
    if ($LASTEXITCODE -ne 0) { throw "La copie du dump PostgreSQL a échoué." }
    & docker compose exec -T database rm -f $containerDump
}
finally {
    Pop-Location
}

$cutoff = (Get-Date).AddDays(-$RetentionDays)
Get-ChildItem -LiteralPath $filesDirectory -File -Filter "cyberpme-source-*.zip" |
    Where-Object LastWriteTime -lt $cutoff | Remove-Item -Force
Get-ChildItem -LiteralPath $databaseDirectory -File -Filter "cyberpme-db-*.dump" |
    Where-Object LastWriteTime -lt $cutoff | Remove-Item -Force

$filesInfo = Get-Item -LiteralPath $filesArchive
$databaseInfo = Get-Item -LiteralPath $databaseArchive
Write-Host "Sauvegarde terminée."
Write-Host ("Fichiers      : {0} ({1:N2} Mo)" -f $filesInfo.FullName, ($filesInfo.Length / 1MB))
Write-Host ("PostgreSQL    : {0} ({1:N2} Mo)" -f $databaseInfo.FullName, ($databaseInfo.Length / 1MB))
Write-Host ("Conservation  : {0} jours" -f $RetentionDays)
