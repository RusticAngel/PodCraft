# PodCraft Demo Reel generator.
# Renders a short MP4 (plus MP3 + SRT) from an existing production pack using
# ONLY cached audio (zero TTS quota). Use the newest pack for the Devpost video.
#
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts\make_reel.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\make_reel.ps1 -Token <pack_token>

param(
    [string]$Token = ""
)

$ErrorActionPreference = "Stop"
$root = (Get-Location).Path
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if (-not $Token) {
    $latest = Get-ChildItem (Join-Path $root "outputs\podcraft_pack_*.zip") |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) { Write-Error "No pack found in outputs\"; exit 1 }
    $Token = [System.IO.Path]::GetFileNameWithoutExtension($latest.Name).Replace("podcraft_pack_", "")
}

$pack = Join-Path $root "outputs\podcraft_pack_$Token.zip"
if (-not (Test-Path $pack)) { Write-Error "Pack not found: $pack"; exit 1 }

Write-Host "Generating reel from $pack ..."
& $python -c "from src.video_generator import generate_video_from_pack; import sys; print(generate_video_from_pack(sys.argv[1]))" $pack
if ($LASTEXITCODE -ne 0) { Write-Error "Video generation failed"; exit 1 }

Write-Host "`nReel generated. Files are in outputs\ (podcast_video_*.mp4 / .mp3 / .srt)."