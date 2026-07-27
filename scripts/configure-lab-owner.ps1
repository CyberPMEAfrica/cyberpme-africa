$ErrorActionPreference = "Stop"
$envPath = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
if (-not (Test-Path -LiteralPath $envPath)) {
    throw "Le fichier .env est introuvable."
}

$securePassword = Read-Host "Choisissez le mot de passe du propriétaire (12 caractères minimum)" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePassword)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
}
if ($password.Length -lt 12) {
    throw "Le mot de passe doit contenir au moins 12 caractères."
}
if ($password -notmatch '^[A-Za-z0-9!@%_+=.\-]+$') {
    throw "Utilisez uniquement lettres, chiffres et les symboles ! @ % _ + = . -"
}

$values = [ordered]@{
    BOOTSTRAP_ORGANIZATION_NAME = "CyberPME Lab"
    BOOTSTRAP_ORGANIZATION_SLUG = "cyberpme-lab"
    BOOTSTRAP_ADMIN_EMAIL = "bocorodrigue43@mail.com"
    BOOTSTRAP_ADMIN_PASSWORD = $password
}
$content = [Collections.Generic.List[string]](Get-Content -LiteralPath $envPath)
foreach ($entry in $values.GetEnumerator()) {
    $prefix = "$($entry.Key)="
    $index = -1
    for ($position = 0; $position -lt $content.Count; $position++) {
        if ($content[$position].StartsWith($prefix)) { $index = $position; break }
    }
    $line = "$prefix$($entry.Value)"
    if ($index -ge 0) { $content[$index] = $line } else { $content.Add($line) }
}
$content | Set-Content -LiteralPath $envPath -Encoding utf8
$password = $null
Write-Host "Compte propriétaire configuré dans .env. Le mot de passe n'a pas été affiché."
