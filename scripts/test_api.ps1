# PodCraft API smoke test.
# Starts the server, runs /health, /analyze, /upload and /download, then
# reports results. Cleans up the server process it started.
#
# Usage (from project root):
#   powershell -ExecutionPolicy Bypass -File scripts\test_api.ps1
#
# Optional: -DemoPdf path/to/script.pdf   -Genre technology   -Port 8000

param(
    [string]$DemoPdf = "static\demo_script.pdf",
    [string]$Genre = "technology",
    [int]$Port = 8000,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$root = (Get-Location).Path

function Write-Step([string]$msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }

# Locate the venv python (prefer local .venv, else system python)
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# Start the server
$server = Start-Process -FilePath $python -ArgumentList @("-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "$Port") -PassThru -WindowStyle Hidden
try {
    $base = "http://127.0.0.1:$Port"

    Write-Step "Waiting for server on $base"
    $ready = $false
    for ($i = 0; $i -lt 30; $i++) {
        try { Invoke-RestMethod -Uri "$base/" -TimeoutSec 2 | Out-Null; $ready = $true; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "Server did not start within 15s" }
    Write-Host "Server ready."

    Write-Step "GET /health"
    $health = Invoke-RestMethod -Uri "$base/health"
    Write-Host ("status: " + $health.status)
    ($health.configured | Format-Table -AutoSize | Out-String).Trim() | Write-Host

    Write-Step "POST /analyze (pdf: $DemoPdf)"
    $tmp = Join-Path $env:TEMP "podcraft_upload.json"
    curl.exe -s -X POST "$base/analyze" -F "file=@$DemoPdf" -o $tmp
    $analyze = Get-Content $tmp | ConvertFrom-Json
    Write-Host ("status: " + $analyze.status)
    Write-Host ("speakers: " + ($analyze.script_analysis.speakers -join ", "))
    Write-Host ("mood: " + $analyze.script_analysis.mood + " | segments: " + $analyze.script_analysis.dialogue_segments.Count)
    Remove-Item $tmp -ErrorAction SilentlyContinue

    Write-Step "POST /upload (full pipeline, ~1-3 min with real TTS)"
    curl.exe -s -X POST "$base/upload" -F "file=@$DemoPdf" -F "genre=$Genre" -o $tmp
    $upload = Get-Content $tmp | ConvertFrom-Json
    Write-Host ("status: " + $upload.status)
    Write-Host ("message: " + $upload.message)
    $audio = $upload.data.audio_production
    Write-Host ("segments: " + $audio.total_segments)
    foreach ($a in $audio.audio_files) {
        Write-Host ("  [{0}] {1} ({2}) -> {3}" -f $a.index, $a.speaker, $a.voice, $a.audio_path)
    }
    Write-Host ("music: " + $audio.music_path)
    Write-Host ("sentiment: " + $audio.sentiment_analysis.overall_tone + " (engagement " + $audio.sentiment_analysis.audience_engagement + ")")
    Write-Host "recommendations:"
    foreach ($r in $upload.data.recommendations) { Write-Host ("  - " + $r) }

    if ($audio.audio_files.Count -gt 0) {
        Write-Step "GET /download (first segment)"
        $name = [System.IO.Path]::GetFileName($audio.audio_files[0].audio_path)
        $dl = Join-Path $root "outputs\download_test.wav"
        $code = curl.exe -s -o $dl -w "%{http_code} %{content_type}" "$base/download/$name"
        Write-Host ("http: " + $code)
        if (Test-Path $dl) { Write-Host ("saved: " + $dl + " (" + (Get-Item $dl).Length + " bytes)") }
    }

    Write-Host "`n=== ALL TESTS DONE ===" -ForegroundColor Green
} finally {
    if (-not $KeepRunning) { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue; Write-Host "`nServer stopped." }
    else { Write-Host "`nServer left running (pid $($server.Id))." }
}