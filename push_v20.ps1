# push_v20.ps1 - stage, commit, and push the v20+v21 research round to GitHub.
# Run in YOUR OWN terminal as weni.liu (you own the repo + have GitHub creds).
# Right-click > "Run with PowerShell" also works.
# Stages ONLY the deliberate files (not scratch scripts, not signals_v13.pkl, not the 93MB lianxi_metrics.pkl).

$ErrorActionPreference = "Stop"
$repo = "D:\Codex\Codex\2026-10-14\new-chat-3\outputs"
Set-Location -LiteralPath $repo

# Allow this repo for the current user (harmless if already set).
git config --global --add safe.directory D:/Codex/Codex/2026-10-14/new-chat-3/outputs

$files = @(
  "README.md",
  "gap_fade_auto.py",
  "v13_target.py",
  "STRATEGY_v20_DECISION.md",
  "RESEARCH_v20_1min_exhaustion.md",
  "v13_gmc_run.py",
  "v13_gmc_out.txt",
  "gmc_signals.pkl",
  "v20_amp_turnover.py",
  "v20_confirm_entry.py",
  "v20_corrected_test.py",
  "v20_exhaustion_confirm.py",
  "v20_exhaustion_noLA.py",
  "v20_exhaustion_v2.py",
  "v20_exhaustion_v3.py",
  "v20_integrated.py",
  "v20_open_vol_price.py",
  "v20_realistic_test.py",
  "v20_sensitivity.py",
  "v20_strategy_test.py",
  "v20_trend_strength.py",
  "v20_us_overnight.py",
  "v20_v13target_s3.py",
  "v20_v13target_grid.py",
  "v20_v13target_expo.py",
  "v20_v13target_capped.py",
  "v20_v13target_best.py",
  "v21_base.py",
  "v21_stageA.py",
  "v21_stageB.py",
  "v21_stageC.py",
  "v21_stageD.py",
  "v21_stageE.py",
  "v21_best.py",
  "v21_report.py",
  "v21_audit.py",
  "v20_features_cache.pkl"
)

# Stage only files that actually exist on disk.
$existing = $files | Where-Object { Test-Path -LiteralPath (Join-Path $repo $_) }
Write-Host "Staging $($existing.Count) file(s)..."
git add -- $existing

Write-Host ""
Write-Host "--- staged (git status --short) ---"
git status --short

Write-Host ""
Write-Host "Review the list above. Press ENTER to commit & push  (Ctrl+C to abort)."
Read-Host | Out-Null

git commit -m "v20+v21: gmc gap-fade leg into v13_target; v21 lifts S3 to annual +270% / MDD -4.3% / win 78% (gap_max + zt_min filters)"

Write-Host ""
Write-Host "Pushing to origin/master ..."
git push origin master

if ($LASTEXITCODE -ne 0) {
  Write-Host ""
  Write-Host "PUSH FAILED (exit $LASTEXITCODE). If it is an auth error:"
  Write-Host "  - HTTPS: use a GitHub Personal Access Token as the password, or"
  Write-Host "  - switch to SSH:  git remote set-url origin git@github.com:WENILIU/Daytrading.git"
  Write-Host "Then re-run:  git push origin master"
  exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Done. Latest commit:"
git log --oneline -1
