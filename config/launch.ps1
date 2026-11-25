# Launch the runtime. The window caption carries the live figures:
# fps | ms/frame | gpu % | cpu % | ram | draws/frame | up
param([string]$Window = '')

. "$PSScriptRoot\env.ps1"
if ($Window) { $env:VICTORY_WINDOW = $Window }

Start-Process -FilePath (Join-Path $Runtime 'victory-play.exe') `
    -WorkingDirectory $Runtime -PassThru | Select-Object Id, ProcessName
