# The switches every run uses. Dot-source before launching, or use launch.ps1.
$env:VICTORY_WINDOW            = '854x480'  # client size; 640x360 is the next step down
$env:VICTORY_FILL_WORKERS      = '4'        # upload and transition workers
$env:VICTORY_PARALLEL_PRELUDES = '1'        # parallel transition recording
$env:VICTORY_UNWATCHED_FRAMES  = '2'        # whole-copy interval; 2 is the safe maximum
$env:VICTORY_TEXTURE_STAGE_MB  = '384'      # upload staging; do not raise past 384 on 32 GB

$Runtime = Join-Path $env:LOCALAPPDATA 'DexNom Runtime'
$Game    = 'C:\GTA6\GTA6.Xbox.v1.0.2.1.CYBERLEEK-GameDrive.Org.part1\GTA6.Xbox.v1.0.2.1-CYBERLEEK'
