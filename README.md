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

## Cloudflare Tunnel

For Cloudflare Tunnel, use the Waitress-backed origin instead of the Flask development server:

```powershell
.\start_tunnel.bat
```

Then point cloudflared to `http://127.0.0.1:5000`. See `docs/CLOUDFLARE_TUNNEL.md` for health checks and tunnel-specific settings.
