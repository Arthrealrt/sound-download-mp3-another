$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

function Run-Python {
    param([string[]]$Arguments)
    & $script:PythonExe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Python command failed (exit $LASTEXITCODE)." }
}

function Find-Python {
    param([string]$Command, [string[]]$Arguments)
    try {
        $Result = & $Command @Arguments -c "import sys, struct; assert sys.version_info[:2] in ((3,11),(3,12)); assert struct.calcsize('P') == 8; import tkinter; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $Result }
    } catch { return $null }
    return $null
}

if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    $Candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        foreach ($Version in @('-3.12', '-3.11')) {
            $Found = Find-Python -Command 'py' -Arguments @($Version)
            if ($Found) { $Candidates += $Found }
        }
    }
    if (Get-Command python -ErrorAction SilentlyContinue) {
        $Found = Find-Python -Command 'python' -Arguments @()
        if ($Found) { $Candidates += $Found }
    }
    foreach ($Candidate in $Candidates) {
        $script:PythonExe = $Candidate
        break
    }
    if (-not $script:PythonExe) { throw 'Please install 64-bit Python 3.11 or 3.12 from python.org, including Tcl/Tk and pip.' }
    Run-Python -Arguments @('-m', 'venv', '.venv')
}
$script:PythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Run-Python -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
Run-Python -Arguments @('-m', 'pip', 'install', '-r', 'requirements-torch.txt')
Run-Python -Arguments @('-m', 'pip', 'install', '-r', 'requirements.txt')
Run-Python -Arguments @('-c', "import torch, torchaudio, demucs, imageio_ffmpeg, tkinter, yt_dlp, Crypto, mutagen; print('All dependencies ready.')")
Write-Host 'Setup complete. Double-click start.bat to launch Sound Studio.'
