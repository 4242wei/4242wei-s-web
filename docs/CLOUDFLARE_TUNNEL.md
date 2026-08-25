# Cloudflare Tunnel origin setup

Use `start_tunnel.bat` when exposing this app through Cloudflare Tunnel. It runs the Flask app behind Waitress instead of the Flask development server.

## Start the local origin

```powershell
cd path\to\4242wei-s-web
.\start_tunnel.bat
```

By default it listens only on:

```text
http://127.0.0.1:5000
```

Point Cloudflare Tunnel at that URL.

## Health checks

These endpoints do not require the web password:

```text
http://127.0.0.1:5000/healthz
http://127.0.0.1:5000/readyz
```

`/healthz` confirms the process is alive. `/readyz` also checks the local data directories needed by the app.

## Useful environment variables

```bat
set PORT=5000
set TUNNEL_HOST=127.0.0.1
set WAITRESS_THREADS=12
set WAITRESS_CONNECTION_LIMIT=200
set WAITRESS_CHANNEL_TIMEOUT=120
set MAX_CONTENT_LENGTH=1073741824
```

For Tunnel use, keep `TUNNEL_HOST=127.0.0.1` unless you intentionally want LAN devices to connect directly.

## Cloudflared target

For a named tunnel, the service target should be:

```yaml
service: http://127.0.0.1:5000
```

For a quick local test:

```powershell
cloudflared tunnel --url http://127.0.0.1:5000
```

## macOS local deployment

On this Mac, port `5000` is reserved by Control Center. The local
`start.command`, `start_tunnel.command`, and Cloudflare ingress configuration
therefore use `http://127.0.0.1:8000` by default.

The public site is managed by the per-user LaunchAgent
`com.4242wei.web-tunnel`. It starts at login and restarts the origin and Tunnel
if they exit unexpectedly. While the Tunnel is running, `caffeinate -i`
prevents idle system sleep but still allows the display to sleep normally.
The real application directory is `~/.local/share/4242wei-web`; the original
`~/Desktop/网页` location is retained as a symlink for normal editing.

## Stable transcript uploads

Large transcript media can bypass the Cloudflare request timeout by uploading
directly from the browser to OSS. The origin then records the task immediately,
downloads an atomic local copy in the background, and submits Tingwu without
holding the browser request open.

Enable the isolated transcript feature flags in `.env.local`:

```text
TRANSCRIPT_DIRECT_OSS_UPLOAD_ENABLED=1
TRANSCRIPT_BACKGROUND_PIPELINE_ENABLED=1
TRANSCRIPT_PDF_ARCHIVE_DIR=/absolute/path/to/transcript-pdfs
```

Rollback does not require reverting code or data. Set the first two values to
`0` and restart the LaunchAgent; the original local multipart upload path stays
available. Disabling the flags does not remove local media, archived PDFs, or
OSS objects.
