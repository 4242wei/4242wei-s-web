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
