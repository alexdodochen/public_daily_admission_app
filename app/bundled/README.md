# app/bundled/

Read-only resources shipped with the packaged `.exe`. User config stays in
`app/data/config.json` (gitignored).

## Files

| File | Committed? | Purpose |
|------|------------|---------|
| `defaults.json` | ✅ yes | Shared Sheet ID + base URLs, non-sensitive |
| `service_account.json` | ❌ **never** | Google SA private key, `.gitignored` |

## Before running PyInstaller

Copy your real service-account JSON to `app/bundled/service_account.json`:

```bash
cp path/to/sigma-sector-xxxx.json app/bundled/service_account.json
```

The `.gitignore` keeps this file out of git. PyInstaller's `--add-data`
flag in `packaging.spec` bundles it into the `.exe`.

## How the app resolves settings

1. User's `app/data/config.json` (if exists) — always wins
2. Fallback to `app/bundled/defaults.json` — Sheet ID, base URLs
3. Fallback to `app/bundled/service_account.json` — if `google_creds_path` blank

So each new user's fresh install reads the bundled SA + Sheet ID
automatically; they only fill LLM / WEBCVIS / LINE on the settings page.
