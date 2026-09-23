#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$ApiUrl,
    [Parameter(Mandatory = $true)][string]$EnrollmentToken,
    [string]$Name = $env:COMPUTERNAME
)
$ErrorActionPreference = 'Stop'
$apiUri = [uri]$ApiUrl
if ($apiUri.Scheme -ne 'https' -or $apiUri.UserInfo -or $apiUri.Query -or $apiUri.Fragment) {
    throw 'Utilisez l’adresse HTTPS de votre API CyberPME.'
}
$agentRoot = Join-Path $env:ProgramData 'CyberPME'
New-Item -ItemType Directory -Path $agentRoot -Force | Out-Null
# Credentials and executable files must not be writable by ordinary users.
& icacls.exe $agentRoot /inheritance:r /grant:r '*S-1-5-18:(OI)(CI)F' '*S-1-5-32-544:(OI)(CI)F' | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Impossible de protéger le dossier CyberPME.' }

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Échec de $Executable (code $LASTEXITCODE)." }
}

Write-Host '1/4 - Préparation de Python et Nmap'
$pythonPath = Join-Path $env:ProgramFiles 'Python312\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'Installez Python 3.12 pour tous les utilisateurs depuis python.org, puis relancez cette commande.'
    }
    Invoke-Checked 'winget.exe' @('install', '--id', 'Python.Python.3.12', '--exact', '--scope', 'machine', '--accept-source-agreements', '--accept-package-agreements')
}
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Python 3.12 doit être installé dans Program Files\Python312.' }
$nmapCandidates = @((Join-Path ${env:ProgramFiles(x86)} 'Nmap\nmap.exe'), (Join-Path $env:ProgramFiles 'Nmap\nmap.exe'))
$nmapPath = $nmapCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $nmapPath) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) { throw 'Installez Nmap et Npcap depuis https://nmap.org/download puis relancez.' }
    Write-Host 'Validez les fenêtres de l’installateur Nmap et conservez Npcap sélectionné.'
    Invoke-Checked 'winget.exe' @('install', '--id', 'Insecure.Nmap', '--exact', '--interactive', '--accept-source-agreements', '--accept-package-agreements')
    $nmapPath = $nmapCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $nmapPath) { throw 'Nmap est absent. Terminez son installation puis relancez.' }
Invoke-Checked $nmapPath @('--version')

Write-Host '2/4 - Installation de CyberPME'
$staging = Join-Path $agentRoot ('setup-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $staging | Out-Null
$archive = Join-Path $staging 'source.zip'
Invoke-WebRequest -UseBasicParsing -Uri 'https://github.com/CyberPMEAfrica/cyberpme-africa/archive/refs/heads/main.zip' -OutFile $archive
Expand-Archive -LiteralPath $archive -DestinationPath $staging
$venv = Join-Path $agentRoot 'venv'
$agentPython = Join-Path $venv 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $agentPython)) { Invoke-Checked $pythonPath @('-m', 'venv', $venv) }
$existingTask = Get-ScheduledTask -TaskName 'CyberPME Agent' -ErrorAction SilentlyContinue
if ($existingTask) { Stop-ScheduledTask -TaskName 'CyberPME Agent' }
Invoke-Checked $agentPython @('-m', 'pip', 'install', '--upgrade', (Join-Path $staging 'cyberpme-africa-main\agent'))

Write-Host '3/4 - Association avec votre organisation'
$configPath = Join-Path $agentRoot 'agent-config.json'
$statePath = Join-Path $agentRoot 'agent-state.json'
$config = @{}
if (Test-Path -LiteralPath $configPath) {
    $previous = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
    foreach ($property in $previous.PSObject.Properties) { $config[$property.Name] = $property.Value }
}
$config.api_url = $ApiUrl.TrimEnd('/')
$config.name = $Name
$config.interval = 30
$config.enrollment_token = $EnrollmentToken
$config.state_path = $statePath
$config | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8
Invoke-Checked $agentPython @('-m', 'cyberpme_agent.main', '--config', $configPath, '--register-only')

Write-Host '4/4 - Démarrage automatique'
$runner = Join-Path $agentRoot 'run-agent.ps1'
@'
$agentRoot = Join-Path $env:ProgramData 'CyberPME'
$log = Join-Path $agentRoot 'agent.log'
if ((Test-Path -LiteralPath $log) -and (Get-Item -LiteralPath $log).Length -gt 10MB) {
    Move-Item -LiteralPath $log -Destination (Join-Path $agentRoot 'agent.previous.log') -Force
}
& (Join-Path $agentRoot 'venv\Scripts\python.exe') -u -m cyberpme_agent.main --config (Join-Path $agentRoot 'agent-config.json') *>> $log
exit $LASTEXITCODE
'@ | Set-Content -LiteralPath $runner -Encoding UTF8
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument ('-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + $runner + '"')
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'CyberPME Agent' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName 'CyberPME Agent'
Write-Host 'Installation terminée. Revenez dans Scanner réseau et actualisez dans 30 secondes.'
Write-Host ('Journal : ' + (Join-Path $agentRoot 'agent.log'))
