$ErrorActionPreference = "Stop"

$RootDir = Resolve-Path (Join-Path $PSScriptRoot "..")
$QwenDir = Join-Path $RootDir "models\Qwen"
$WhisperDir = Join-Path $RootDir "models\whisper"

New-Item -ItemType Directory -Force -Path $QwenDir, $WhisperDir | Out-Null

function Download-File {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][string]$Output
    )

    if (Test-Path $Output) {
        Write-Host "Already exists: $Output"
        return
    }

    if ([string]::IsNullOrWhiteSpace($Url) -or $Url -eq "TODO") {
        Write-Warning "Missing URL for $Output. Set the matching environment variable or edit this script."
        return
    }

    Write-Host "Downloading $Url"
    Invoke-WebRequest -Uri $Url -OutFile $Output
}

# Stable Hugging Face "resolve" URL. Hugging Face may redirect this to a
# short-lived cas-bridge.xethub signed URL; do not commit those signed URLs.
$QwenGgufUrl = if ($env:QWEN_GGUF_URL) {
    $env:QWEN_GGUF_URL
} else {
    "https://huggingface.co/Edge-Quant/Qwen3-4B-Instruct-2507-Q4_K_M-GGUF/resolve/main/qwen3-4b-instruct-2507-q4_k_m.gguf"
}

$WhisperBaseUrl = if ($env:WHISPER_BASE_URL) {
    $env:WHISPER_BASE_URL
} else {
    "https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-base.bin"
}

$WhisperSmallUrl = if ($env:WHISPER_SMALL_URL) {
    $env:WHISPER_SMALL_URL
} else {
    "https://huggingface.co/ggml-org/whisper.cpp/resolve/main/ggml-small.bin"
}

Download-File -Url $QwenGgufUrl -Output (Join-Path $QwenDir "Qwen3-4B-Instruct-2507-Q4_K_M.gguf")
Download-File -Url $WhisperBaseUrl -Output (Join-Path $WhisperDir "ggml-base.bin")

if ($env:DOWNLOAD_WHISPER_SMALL -eq "1") {
    Download-File -Url $WhisperSmallUrl -Output (Join-Path $WhisperDir "ggml-small.bin")
}

Write-Host "Model download step finished."
Write-Host "If Qwen download was skipped, set QWEN_GGUF_URL and run again."
