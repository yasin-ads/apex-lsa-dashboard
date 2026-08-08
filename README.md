# Apex LSA Rank Dashboard

This repository runs the LSA rank checker automatically and publishes a simple web dashboard.

## What it does

- Uses SerpApi Google Local Services engine.
- Does not log in to any Google account.
- Runs 4 times per day with GitHub Actions.
- Saves the latest CSV and JSON.
- Keeps rolling history for the last 180 scans.
- Displays the latest rankings through GitHub Pages.

## First local setup

Set your SerpApi key.

PowerShell:
```powershell
$env:SERPAPI_KEY="YOUR_KEY"
python lsa_rank_checker.py --find-cids
python lsa_rank_checker.py
```

CMD:
```cmd
set SERPAPI_KEY=YOUR_KEY
python lsa_rank_checker.py --find-cids
python lsa_rank_checker.py
```

Commit the generated `city_cids.json` file.

## GitHub secret

Repository → Settings → Secrets and variables → Actions → New repository secret

Name:
`SERPAPI_KEY`

Value:
your SerpApi key.

Never put the key directly in source code.

## Test automation

GitHub → Actions → Update LSA Rankings → Run workflow

## Enable GitHub Pages

Repository → Settings → Pages

Select:
- Deploy from a branch
- Branch: main
- Folder: /(root)

The dashboard will be available at:
`https://YOUR_USERNAME.github.io/YOUR_REPOSITORY/`

## Privacy

GitHub Pages is normally public. Do not use public Pages if you consider ranking data confidential.

## City list

The screenshots supplied for the project contain 54 verified cities.
If the live account has 58, add the four missing names to `EXTRA_CITIES` in `lsa_rank_checker.py`,
run `--find-cids` again, and commit the updated `city_cids.json`.
