# Warm the shader cache before a run. victory-warm.exe needs the launcher's state
# lock, so call victory.exe warm instead - it does not, and it works while a run is live.
param([int]$Jobs = 16, [switch]$NoPipelines)

. "$PSScriptRoot\env.ps1"

$env:VICTORY_GAME_DIR  = $Game
$env:VICTORY_CACHE_DIR = Join-Path $Runtime 'cache'
$env:VICTORY_DATA_DIR  = Join-Path $Runtime 'state'

$warmArgs = @('warm', '--jobs', $Jobs)
if ($NoPipelines) { $warmArgs += '--no-pipelines' }

& (Join-Path $Runtime 'victory.exe') @warmArgs
