$ErrorActionPreference = "Stop"
if (-not $env:SERPAPI_KEY) {
    Write-Host 'Set your key first: $env:SERPAPI_KEY="YOUR_KEY"'
    exit 1
}
python .\lsa_rank_checker.py --find-cids
python .\lsa_rank_checker.py
Write-Host "Local setup complete."
