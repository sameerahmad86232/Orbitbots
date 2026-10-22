# Orbit Computer — self-hosted companion

This service is **not provisioned hosting**. It needs a Linux server or computer running Docker, normally at least 2 CPU cores and 2 GB RAM for Chromium. Model hosting/inference may need more resources. It cannot run as a Docker desktop inside this APK on an ordinary phone.

## What works

- A real 1280×800 Xvfb display, Openbox and Chromium; persistent browser profile.
- Real OS mouse clicks, double clicks, dragging, typing, key combinations and scrolling using xdotool.
- Authenticated JPEG screenshot preview in the Android app and a browser dashboard. It refreshes approximately once per 1.2–1.5 seconds while visible. This is **polling**, not noVNC, WebRTC or audio streaming.
- Every input/action, including terminal commands and SMTP sending, enters a persistent approval queue. An owner/reviewer must approve the immutable action before it executes. Replay approval is rejected; uncertain/failed executions are never automatically retried.
- Optional persistent server vision jobs: screenshot → OpenAI-compatible vision model → one validated action → human approval → next screenshot. Jobs run without the phone being open while this server remains up. Requests are bounded to 1–30 per job. The server needs its own configured model credentials; the APK does not forward the phone's key.
- SQLite audit history, full-text knowledge retrieval and interval schedules. Due schedules queue an action for approval, not an unrestricted AI workflow. Missed intervals coalesce. Schedules/queues survive restart.
- SMTP email sending **after explicit approval**, and read-only IMAP listing of the ten newest message headers when configured. Does not provision a mailbox or domain. IMAP message bodies/attachments and OAuth mailbox login are not implemented.
- Optional shared-workspace owner/reviewer/viewer tokens. Owner can configure knowledge, schedules and server jobs. Reviewer can request/review actions. Viewer can inspect screenshots/action history. This is one shared computer, not isolated multi-tenant teams, enterprise SSO or per-bot access control.
- Terminal opt-in using `ORBIT_ALLOW_TERMINAL=1`; off by default. The vision worker cannot request terminal or email actions, but approved manual terminal commands and the APK's separately enabled mail queue are supported.

## Run on your server

```sh
cp .env.example .env
# Set ORBIT_TOKEN to output from: openssl rand -hex 32
# Configure optional model/mail settings in .env as needed.
docker compose -f compose.yml up --build -d
```

The default port is `127.0.0.1:8080` on the server. Put a TLS reverse proxy in front of it; for example Caddy on that server:

```caddyfile
desktop.your-domain.example {
    reverse_proxy 127.0.0.1:8080
}
```

DNS and HTTPS must be configured for your actual domain. In the APK, Settings → Your computer: enter `https://desktop.your-domain.example` and its access token. Save, open Computer, and connect. Tokens are stored encrypted on the phone, bound to the exact endpoint. On a private LAN you can deliberately bind the service to the LAN and use private HTTP; it is unencrypted and should not be exposed publicly.

One container per data volume, one Uvicorn worker. Starting two instances against the same Chromium profile is unsupported. Startup clears only Chromium's prior-instance locks and supervises desktop/browser/API processes. If the browser/display exits, the container exits so the configured Docker restart policy can recover it. Model calls interrupted by server restart enter `interrupted` and are not automatically billed again. Executing actions become `interrupted`; inspect their real effects before retrying.

### Vision worker

Set `MODEL_BASE_URL` to an OpenAI-compatible base URL, `MODEL_ID` to a vision model, and `MODEL_API_KEY` when required. Ollama on the same server can use a reachable local/private endpoint; `127.0.0.1` inside this container refers to this container, not the host. Configure networking accordingly without exposing an unauthenticated model service to the internet. Set `MODEL_TOKEN_FIELD=max_completion_tokens` for models requiring that field. Some models cannot follow the action JSON protocol reliably; malformed/rejected responses stop the job rather than trigger hidden retries.

In Computer choose **Start server agent**, enter a goal and request cap. View jobs via **Server jobs**. Open the approval inbox when it pauses. Cancelling a server job rejects its still-pending action, but cannot undo actions or model requests already accepted. Removing the phone's provider key or closing/uninstalling the APK does not cancel a server job. Cancel it explicitly before shutting down access.

### Mail and knowledge

Set SMTP_HOST/PORT/FROM and credentials for your account. STARTTLS is required except port 465, which uses implicit TLS. A plaintext loopback-only test switch is used exclusively by tests. Set IMAP_HOST/USER/PASSWORD for SSL IMAP. Account providers may require app passwords or may forbid password authentication; unsupported OAuth cannot be substituted automatically. In the APK, Compose server email queues a reviewable message. Agent mailbox access is a separate explicit toggle in Settings.

Files → View → Copy to server knowledge uploads a chosen text file to this service. SQLite FTS retrieval is lexical, **not vector/embedding RAG**. Server data is stored on the Docker data volume; mobile encryption does not encrypt this volume. Use encrypted host storage/backups and a server you trust. Screenshots, browser sessions and action history can contain sensitive information.

### Notifications

The APK provides foreground progress, task-result and approval notifications while tasks run. Optional JobScheduler checks detect pending server approvals approximately every 15 minutes; Android battery/network restrictions may delay or prevent them. These are not instant FCM/Web Push notifications. Enable notification permission and background approval checks in Settings. Server jobs can remain paused until you reopen the app.

### Proxy/CA environments

The Dockerfile supports an optional BuildKit secret `proxy_ca` for pip trust:

```sh
docker build --secret id=proxy_ca,src=/path/to/combined-ca.pem -t orbit-computer .
```

For deployments behind a TLS inspection proxy, provide the proxy's CA as a read-only runtime mount and set `ORBIT_CA_CERT` to its container path. Chromium imports it into the user's NSS database. Set `ORBIT_BROWSER_PROXY` when Chromium requires an explicit proxy. Python clients use standard `SSL_CERT_FILE`/proxy variables. TLS verification is never disabled.

## Security boundary and limits

This is a trusted, single-workspace self-hosted service. Use one isolated server/container per trusted workspace. Docker runs as an unprivileged user with dropped capabilities, resource limits and no Docker socket/host filesystem mounts. Chromium uses `--no-sandbox` inside the outer container because this deployment does not supply its separate sandbox prerequisites. The container is not a hardened browser VM, gVisor or Firecracker sandbox. Do not run hostile workloads or attach production secrets to an untrusted desktop. An enabled, approved terminal command runs as the same container user and can access that user's files/processes; it is not isolated from service credentials. Keep terminal disabled unless you understand that trust model.

No billing/hosting account, cloud machine, email account, automatic mailbox provisioning, Stripe/X Money payment processing, Figma/Notion/Canva/Glean/QuickBooks OAuth, vector database, image/video generation, desktop audio stream or verified Grok proprietary import is supplied. Model performance and account integrations are not guaranteed. Shared role tokens grant access to this shared computer and its history, not separate private user workspaces.

## Tests

```sh
python test_server.py
python test_agent.py
# Against an isolated test container (never a personal work desktop):
ORBIT_TEST_TOKEN_FILE=/path/to/test-token python test_live.py
```

Unit/contract tests cover authentication/roles, approval/replay/failure behavior, validation, real loopback SMTP delivery and a bounded vision loop with an HTTP model stub. Live tests use a real container display/browser, actual X11 clicking, screenshot capture, schedules and FTS. The optional `ORBIT_TEST_AGENT=1` live test expects `test_model_fixture.py` running only in the isolated test container. That fixture is not AI inference. Never start it as your production model.

## Open-source components

FastAPI (MIT), Uvicorn (BSD), HTTPX (BSD), Pillow (HPND), SQLite (public domain), X.Org/Xvfb (MIT-style licenses), xdotool (BSD), Openbox (GPL) and Chromium (BSD and bundled third-party licenses). Upstream packages retain their licenses. Orbit's application code and original Milo SVG/CSS are MIT licensed. No GhostDesk/non-compete dependency is used. The implementation does not rely on the supplied third-party popularity or feature claims.
