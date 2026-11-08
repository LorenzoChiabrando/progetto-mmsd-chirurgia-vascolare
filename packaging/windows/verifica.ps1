# Avvia ScadenzarioCV.exe con una cartella utente vuota e controlla che la finestra compaia
# e che i dati demo vengano creati. Non tocca i dati veri in %APPDATA%\ScadenzarioCV.
#
#   powershell -ExecutionPolicy Bypass -File packaging\windows\verifica.ps1
$ErrorActionPreference = "Stop"

$radice = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$exe = Join-Path $radice "ScadenzarioCV.exe"
$utente = Join-Path ([IO.Path]::GetTempPath()) ("ScadenzarioCV-verifica-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $utente | Out-Null

$appdataPrima = $env:APPDATA
$env:APPDATA = $utente
try {
    $app = Start-Process -FilePath $exe -PassThru
} finally {
    $env:APPDATA = $appdataPrima
}

$esito = 1
for ($secondi = 0; $secondi -lt 60; $secondi++) {
    $finestra = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.MainWindowTitle -like "MMSD CV*" -and $_.Path -like "*ScadenzarioCV*" }
    if ($finestra) {
        if (Test-Path (Join-Path $utente "ScadenzarioCV\v2\dati\scadenzario")) {
            Write-Output "OK: finestra aperta in ${secondi}s, dati demo creati in %APPDATA%\ScadenzarioCV\v2"
            $esito = 0
        } else {
            Write-Output "KO: finestra aperta ma dati demo non creati"
        }
        break
    }
    if ($app.HasExited) { break }
    Start-Sleep -Seconds 1
}
if ($esito -ne 0 -and -not $finestra) { Write-Output "KO: nessuna finestra" }

# L'eseguibile a file unico avvia un processo figlio: si chiudono entrambi.
Get-Process -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $exe -or $_.Id -eq $app.Id } |
    Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Remove-Item -Recurse -Force $utente -ErrorAction SilentlyContinue
exit $esito
