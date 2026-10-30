$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$taskPython = Join-Path $taskRoot 'work\build-env\Scripts\python.exe'
$taskReleases = [IO.Path]::GetFullPath((Join-Path $taskRoot 'releases'))
$taskTarget = [IO.Path]::GetFullPath((Join-Path $taskReleases 'ControlGestual-V5.3'))
if (-not $taskTarget.StartsWith($taskRoot + [IO.Path]::DirectorySeparatorChar)) { throw 'Destino de compilación fuera del proyecto.' }
if (-not (Test-Path -LiteralPath $taskPython)) { throw 'Prepará work/build-env con PyInstaller 6.22.3 antes de compilar.' }
$taskExe = Join-Path $taskTarget 'ControlGestual-V5.3.exe'
if (Get-Process -Name 'ControlGestual-V5.3' -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $taskExe }) {
    throw 'La version 5.3 esta abierta. Elegi Salir desde la bandeja antes de recompilar. No se modificaron sus archivos.'
}
$taskBackup = $null
if (Test-Path -LiteralPath $taskTarget) {
    $taskBackup = Join-Path $taskRoot ('work\release-backup-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Copy-Item -LiteralPath $taskTarget -Destination $taskBackup -Recurse
}
$env:PYINSTALLER_CONFIG_DIR = Join-Path $taskRoot 'work\pyinstaller-cache'
$taskArguments = @('-m','PyInstaller','--noconfirm','--onedir','--windowed','--name','ControlGestual-V5.3',
    '--distpath',$taskReleases,'--workpath',(Join-Path $taskRoot 'work\pyinstaller-v2'),'--specpath',(Join-Path $taskRoot 'work'),
    '--collect-all','vosk','--collect-all','sounddevice','--collect-all','_sounddevice_data',
    '--add-data',((Join-Path $taskRoot 'phone-tools') + ';phone-tools'),
    '--add-data',((Join-Path $taskRoot 'voice-model') + ';voice-model'),
    '--add-data',((Join-Path $taskRoot 'desktop') + ';desktop'),
    '--add-data',((Join-Path $taskRoot 'extension\vendor') + ';extension\vendor'),
    '--add-data',((Join-Path $taskRoot 'extension\core.js') + ';extension'),
    '--add-data',((Join-Path $taskRoot 'extension\hand-view.js') + ';extension'),
    (Join-Path $taskRoot 'desktop_app.py'))
& $taskPython @taskArguments
if ($LASTEXITCODE -ne 0) { throw 'Falló la compilación. La copia de la versión anterior permanece en work.' }
$taskSettingsSource = Join-Path $taskRoot 'settings.json'
$taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V5.2\settings.json'
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V5.1\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V5.0\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V4.2\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V4.1\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V4.0\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V3.2\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V3.1\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V3.0\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V2.3\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V2.2\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V2.1\settings.json' }
if (-not (Test-Path -LiteralPath $taskPreviousSettings)) { $taskPreviousSettings = Join-Path $taskReleases 'ControlGestual-V2\settings.json' }
if (Test-Path -LiteralPath $taskPreviousSettings) { $taskSettingsSource = $taskPreviousSettings }
if ($taskBackup -and (Test-Path -LiteralPath (Join-Path $taskBackup 'settings.json'))) { $taskSettingsSource = Join-Path $taskBackup 'settings.json' }
if (Test-Path -LiteralPath $taskSettingsSource) { Copy-Item -LiteralPath $taskSettingsSource -Destination (Join-Path $taskTarget 'settings.json') }
if ($taskBackup -and (Test-Path -LiteralPath (Join-Path $taskBackup 'phone-private'))) { Copy-Item -LiteralPath (Join-Path $taskBackup 'phone-private') -Destination (Join-Path $taskTarget 'phone-private') -Recurse }
$taskPhoneSource = Join-Path $taskReleases 'ControlGestual-V5.2\phone-private'
if (-not (Test-Path -LiteralPath $taskPhoneSource)) { $taskPhoneSource = Join-Path $taskReleases 'ControlGestual-V5.1\phone-private' }
if (-not (Test-Path -LiteralPath $taskPhoneSource)) { $taskPhoneSource = Join-Path $taskReleases 'ControlGestual-V5.0\phone-private' }
if (-not (Test-Path -LiteralPath $taskPhoneSource)) { $taskPhoneSource = Join-Path $taskReleases 'ControlGestual-V4.2\phone-private' }
if (-not (Test-Path -LiteralPath $taskPhoneSource)) { $taskPhoneSource = Join-Path $taskReleases 'ControlGestual-V4.1\phone-private' }
if (-not (Test-Path -LiteralPath (Join-Path $taskTarget 'phone-private')) -and (Test-Path -LiteralPath $taskPhoneSource)) { Copy-Item -LiteralPath $taskPhoneSource -Destination (Join-Path $taskTarget 'phone-private') -Recurse }
Copy-Item -LiteralPath (Join-Path $taskRoot 'README.md') -Destination (Join-Path $taskTarget 'LEEME.md')
$taskShell = New-Object -ComObject WScript.Shell
$taskShortcut = $taskShell.CreateShortcut((Join-Path $taskRoot 'ControlGestual 5.3.lnk'))
$taskShortcut.TargetPath = Join-Path $taskTarget 'ControlGestual-V5.3.exe'
$taskShortcut.WorkingDirectory = $taskTarget
$taskShortcut.IconLocation = $taskShortcut.TargetPath + ',0'
$taskShortcut.Save()
Write-Output ('Ejecutable: ' + (Join-Path $taskTarget 'ControlGestual-V5.3.exe'))
