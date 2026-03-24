# GitHub Share Guide

This repository is now organized as a code-only web project.

It is meant to share the website structure and source code without sharing the original machine's private local research assets.

## What Should Go To Git

Safe to keep in Git:

- Flask backend code
- `templates/`
- `static/`
- `docs/`
- `requirements.txt`
- `start.bat`
- `.env.example`

## What Must Stay Local

These paths are intentionally local-only and should not be committed:

- `.env`
- `.env.local`
- `data/`
- `uploads/`
- `reports/`
- `backups/`
- `logs/`
- `output/`
- `.venv/`

That means Git will not carry:

- private research reports
- meeting / call transcript source files
- AI chat history
- mindmap history
- stock workspace local data
- API credentials
- local screenshots, logs, and temporary outputs

## Recommended Update Flow

If you want to sync the latest website structure to Git:

```powershell
git status
git add .
git commit -m "Prepare code-only web release"
git push origin main
```

Because the ignore rules already exclude local data paths, a normal `git add .` should only pick up the shareable project structure.

## What Another User Gets

After cloning, another user should receive:

- the full web application structure
- templates, styles, scripts, and backend routes
- an empty workspace if local data is missing

They should not receive:

- your reports
- your uploaded files
- your local AI history
- your API keys

## Local Machine Overrides

Another user can create their own `.env.local` and point the app at their own local paths:

```text
REPORTS_DIR=D:\their\reports\folder
STOCKS_DATA_PATH=D:\their\web-data\stocks.json
STOCKS_UPLOADS_DIR=D:\their\web-data\uploads\stocks
TRANSCRIPT_UPLOADS_DIR=D:\their\web-data\uploads\transcripts
AI_CHAT_DATA_PATH=D:\their\web-data\ai_chats.json
AI_CONTEXT_DIR=D:\their\web-data\ai_context
```

These should stay local and should not be committed.

## Local API Credentials

If another user wants Tingwu / OSS features, they should place credentials only in their own `.env.local`:

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

Never push filled credentials to Git.

## Read This First

If another user or another Codex instance takes over this repo, read in this order:

1. `README.md`
2. `docs/WEB_STRUCTURE.md`
3. `docs/CODEX_DEPLOY.md`

That keeps the project aligned with the rule:

code structure goes to Git, private local data stays local.
