# Stock Daily Analysis Web

This project turns a folder of Markdown files into a simple website.

By default, `start.bat` points the site at:

```text
D:\工作\FTAI\reports
```

So you do not need to copy files into this project manually.

## What it does

- Reads Markdown files from `D:\工作\FTAI\reports`
- Shows a report list on the left
- Renders the selected report on the right
- Sorts newest reports first using the date in the filename when possible
- Lets other devices on the same network open the page while the app is running
- Includes a `Stock` workspace for custom groups, favorites, notes, and research file uploads
- Supports linked stock research notes plus file uploads with optional text extraction from text, PDF, and DOCX
- Includes a stock activity calendar so you can see which day received notes or files

## First run

```powershell
cd "D:\工作\网页"
.\start.bat
```

Then open `http://127.0.0.1:5000`.

## Add new reports

1. Put your generated `.md` files into `D:\工作\FTAI\reports`
2. Refresh the browser
3. The newest file will appear near the top automatically

Both `.md` and `.markdown` files are supported.

Recommended filename format:

```text
YYYYMMDD_HHMMSS_anything.md
```

Example:

```text
20260313_132110_manual_run.md
```

If the filename does not include a date, the app falls back to the file's modified time.

## Stock workspace

Open the `Stock` page from the top navigation to:

- Create custom groups
- Add one or more stock symbols into each group
- Mark stocks as favorites
- Open a stock detail page for historical notes
- Upload your own research files for each stock
- Optionally extract readable text from `txt/md/json/pdf/docx` style files into a linked note
- Keep your own comment above the extracted text when both are saved together
- Preview text-based files online and download any uploaded file
- Open the `Calendar` page to review daily note/file activity and jump back into a stock page
- Use the masthead `Calendar` button to open a popup month view of total stock activity counts
- View a small per-stock calendar on each stock detail page to see that symbol's own note/file activity

## Tingwu transcription

Open the `语音转录` page from the top navigation to:

- Upload a meeting audio/video file and let the app save it locally, auto-upload it to OSS, and submit it to Tingwu
- Preselect speaker diarization, auto chapters, meeting assistance, summarization, text polish, and custom prompt options
- Link a transcript to a stock so it also appears in that stock's detail page under `会议转录`
- Keep the advanced `FileUrl` field only as an override when you want to provide your own cloud URL
- Poll active Tingwu tasks from the backend and write the fetched results back into the page

Credentials are loaded from local environment variables. For local file-based loading, copy `.env.example` to `.env.local` and fill:

```text
ALIBABA_CLOUD_ACCESS_KEY_ID=
ALIBABA_CLOUD_ACCESS_KEY_SECRET=
ALIYUN_TINGWU_APP_KEY=
ALIYUN_OSS_ENDPOINT=https://oss-cn-beijing.aliyuncs.com
ALIYUN_OSS_REGION_ID=cn-beijing
ALIYUN_OSS_BUCKET=
```

`.env.local` is ignored by git and should stay local only.

## Run manually

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python app.py
```

## Let another computer visit it

When the app starts, it listens on `0.0.0.0:5000`, which means other devices on the same LAN can use:

```text
http://YOUR-COMPUTER-IP:5000
```

Example:

```text
http://192.168.1.8:5000
```

Keep this program window open while the site is being used.
