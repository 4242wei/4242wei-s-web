# Codex Deploy Guide

This file is for a user-side Codex instance that needs to deploy or continue this web project on another machine.

## Deployment Goal

Deploy the web application codebase only.

Do not assume the source machine's local research assets exist.
Do not copy or recreate private local data unless the user explicitly provides it.

## Keep Local-Only Assets Out Of Git

These paths are intentionally local and should stay untracked:

- `data/`
- `uploads/`
- `reports/`
- `logs/`
- `backups/`
- `output/`
- `.env`
- `.env.local`
- `.venv/`

If they do not exist on the target machine, that is acceptable. The app should still boot with an empty workspace.

## What A Fresh Machine Needs

Minimum requirements:

- Windows with PowerShell
- Python 3.11+ available as `python`
- Git

Optional:

- A local reports directory
- Local data directories
- Tingwu / OSS credentials in `.env.local`
- Codex CLI, only if the user wants local AI / mindmap generation features

## First-Time Setup

From a clean clone:

```powershell
git clone https://github.com/4242wei/4242wei-s-web.git
cd 4242wei-s-web
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env.local
```

Then edit `.env.local` only if the user wants local path overrides or API credentials.

## Optional Local Path Overrides

Use `.env.local` for machine-specific paths:

```text
REPORTS_DIR=
STOCKS_DATA_PATH=
STOCKS_UPLOADS_DIR=
TRANSCRIPT_UPLOADS_DIR=
AI_CHAT_DATA_PATH=
AI_CONTEXT_DIR=
```

Recommended rule:

- keep project structure in Git
- keep user data outside Git
- prefer absolute local paths for data if the machine already has a data layout

## Optional API Credentials

Only place these in `.env.local` on the target machine:

```text
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
ALIYUN_TINGWU_APP_KEY=
ALIYUN_TINGWU_ENDPOINT=tingwu.cn-beijing.aliyuncs.com
ALIYUN_TINGWU_REGION_ID=cn-beijing
ALIYUN_TINGWU_API_VERSION=2023-09-30
ALIYUN_OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_REGION_ID=cn-beijing
ALIYUN_OSS_BUCKET=
```

Never commit filled credentials back to Git.

## Run The App

Use either:

```powershell
.\start.bat
```

or:

```powershell
.\.venv\Scripts\python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## If Reports Or Data Are Missing

Do not treat that as a deployment failure.

Expected behavior on a fresh machine:

- the site loads
- the workspace may be empty
- stock notes / uploads / transcript history may be empty
- AI and transcription features may be limited until local config is provided

## Safe Rules For Codex

If you are Codex working on this repo for another user:

1. Preserve the existing web structure and module boundaries in `docs/WEB_STRUCTURE.md`.
2. Do not fabricate or restore private research data.
3. Do not commit `.env.local`, `data/`, `uploads/`, `reports/`, or `output/`.
4. Prefer code changes and docs changes over machine-specific edits.
5. If deployment requires credentials, ask the user to supply them locally instead of hardcoding them.

## Recommended Verification

After setup, verify:

```powershell
.\.venv\Scripts\python -m py_compile app.py
```

Then open:

- `/`
- `/stocks`
- `/mindmaps`

The pages only need to load successfully. They do not need the original machine's local data to be considered deployed.
