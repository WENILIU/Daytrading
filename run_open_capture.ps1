# run_open_capture.ps1 - 開盤後(約 09:10) 由排程喚醒：抓當天「實際開空單標的」的真實逐筆成交，
#   用於量「真實成交滑價 vs 實際參與率」。非交易日/無網路會安全略過。
#   與 13:00 的 run_fill_capture.ps1(釘漲停腿) 是不同的腿，勿混。
#   產物寫在 fill_probe\ 下(屬資料, 不入 repo)。看結果: python v21_open_impact.py real
#   註冊(需在本機、有網路): schtasks /Create /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 09:10 /TN "V21-OpenCapture" /TR "powershell -WindowStyle Hidden -File D:\Codex\Codex\2026-10-14\new-chat-3\outputs\run_open_capture.ps1"
$ErrorActionPreference = "SilentlyContinue"
$dir  = "D:\Codex\Codex\2026-10-14\new-chat-3\outputs"
$root = Join-Path $dir "fill_probe"
New-Item -ItemType Directory -Force -Path $root | Out-Null
$log  = Join-Path $root ("open_capture_{0}.log" -f (Get-Date -Format "yyyy-MM-dd"))
Set-Location $dir
$py = $null
foreach ($c in @("python", "py")) { if (Get-Command $c -ErrorAction SilentlyContinue) { $py = $c; break } }
if (-not $py -and (Test-Path "C:\Python314\python.exe")) { $py = "C:\Python314\python.exe" }
"[$(Get-Date -Format s)] start python=$py" | Out-File -Append -Encoding utf8 $log
if (-not $py) { "[$(Get-Date -Format s)] ERROR: no python" | Out-File -Append -Encoding utf8 $log; exit 2 }
$env:PYTHONIOENCODING = "utf-8"
# 1) 抓今天日誌裡實際下單標的全日逐筆(需網路; Fugle trades 只回最近交易日 -> 必須同日抓)
& $py collect_ticks.py 2>&1 | Out-File -Append -Encoding utf8 $log
# 2) 用真實逐筆算實際參與率對應的真實滑價
& $py v21_open_impact.py real 2>&1 | Out-File -Append -Encoding utf8 $log
"[$(Get-Date -Format s)] end exit=$LASTEXITCODE" | Out-File -Append -Encoding utf8 $log
exit $LASTEXITCODE
