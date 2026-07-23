$url = "https://github.com/rudraksha127/PythonAI/archive/refs/heads/main.zip"
$out = "C:\Users\lucky\OneDrive\Desktop\PythonAI_remote.zip"
Write-Output "Downloading from GitHub..."
Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 600
Write-Output "Download complete! File saved to: $out"
