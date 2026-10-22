# Orbit 4 capabilities and setup

The APK contains configurable clients and local tools. **No cloud server, model weights, provider credits, OAuth client registrations, mailbox or merchant account is supplied.** With only a phone and no server, core chat/local tools work with a configured model API; the connected-service features cannot activate until a server is hosted.

| Capability | Implemented path | What remains to activate/verify |
|---|---|---|
| Easier hosting setup | `computer/setup.py` generates a private token/config; Docker Compose + optional Caddy TLS | You must supply a Linux host, domain/DNS and any hosting charges. No host was provisioned. |
| Android testing | Emulator installation/launch plus native Keystore, backup, tamper and XLSX harness in CI | Not a physical-phone test; microphone/camera/live-provider behavior remains unverified. |
| OAuth connections | Registered-app flows for Google, Microsoft, Notion, Figma, Canva, QuickBooks; state, PKCE where supported, encrypted tokens and refresh | Requires client apps, provider approval/scopes and real account consent. Contract tested, not verified with live accounts. |
| Connected operations | Gmail/Outlook message listing + approved sending, Notion search + approved page creation, Figma profile + approved comments, Canva design listing, QuickBooks company information | These are selected operations, not complete replicas of every provider's app. Canva/QuickBooks are read-only here. No Glean connector. |
| Image/video/audio | Image generation, xAI-protocol video requests/status, audio transcription and speech files | Configure appropriate models/credits. Protocol fixtures tested; actual provider inference not verified. No bundled local generation models. |
| Live voice | OpenAI Realtime WebRTC browser portal, server-held project key, microphone consent and stop control | Requires HTTPS, supported browser/device and configured funded Realtime account. Signaling contract tested, not a live speech call. Not every model/provider supports voice. |
| Smooth desktop | Authenticated noVNC/RFB streaming, view-only enforced by x11vnc; queued real input remains approved | Real stream and server-side pointer rejection tested. No WebRTC desktop/audio streaming. |
| Accounts/team | Password-hashed individual accounts; expiring sessions; owner/reviewer/viewer roles; disable/revoke | One shared trusted desktop, not isolated enterprise tenants, SSO, organizations or granular per-bot ACLs. |
| Cross-device data | Explicit encrypted backup/restore of chats, profiles, memories and text workspaces; per-user server storage, revisions and conflicts | Not continuous merge/live collaborative sync. Passphrase required on each device; keys/connections excluded. Restore disables tool flags and routines. |
| Semantic knowledge | Chunked embeddings, model-separated SQLite vectors, cosine retrieval; optional phone agent tool and server RAG | Configure an embedding provider and explicitly index documents. Fixture vectors tested; real embedding quality unverified. Shared server knowledge, not per-tenant isolation. |
| Excel/larger documents | Local bounded XLSX parsing; server PDF/XLSX/text extraction up to 10 MB | Cached values, not formula execution; no PDF OCR. Output, cells/pages and expanded ZIP size are bounded. |
| Payments | Approved Stripe Checkout link creation; idempotency keys; signed/replay-safe webhook status | Requires an eligible Stripe merchant account, keys and webhook registration. No live charge tested, no auto-charging, X Money, wallet or guaranteed earnings. |
| Grok imports | Existing previewed JSON profile/message migration | A verified Grok Bot export schema/sample is still unavailable. Arbitrary Grok proprietary exports/share links are not claimed to work. |

## Deploy your server

On a Linux Docker host with a domain already pointing at it:

```sh
cd computer
python3 setup.py --domain desktop.your-domain.example --start
```

This does not rent a machine, register DNS or charge an account. It creates `.env` with permissions 0600 and a random token, then starts Compose/Caddy when `--start` is used. If `.env` exists, it refuses to overwrite it. Configure optional services there, then use:

```sh
docker compose -f compose.yml -f tls.yml up -d --build
```

The APK connects in Settings → Your computer. Tools contains account sign-in/management, encrypted sync, connected apps, media, semantic knowledge, payments and browser portals. Native provider keys stay separate from computer-service credentials.

## OAuth

Register a client app for each chosen provider, set `<PROVIDER>_CLIENT_ID` and `_CLIENT_SECRET`, and register this exact callback:

```
https://your-server.example/oauth/google/callback
https://your-server.example/oauth/microsoft/callback
https://your-server.example/oauth/notion/callback
https://your-server.example/oauth/figma/callback
https://your-server.example/oauth/canva/callback
https://your-server.example/oauth/quickbooks/callback
```

Set `PUBLIC_BASE_URL` to your HTTPS origin. Provider verification, tenant restrictions, plan requirements and scopes still apply. Google requests Gmail read/send; Microsoft requests Mail.Read/Mail.Send and offline access; other connectors use their documented scoped endpoints. Connections belong to the signed-in Orbit account. Writes bind the connection identity and always queue for review. Disconnecting removes local credentials; revoke access in the upstream account to revoke it there. Never enter client secrets into chat or commit `.env`.

## Sync

Use Tools → Encrypted sync with a passphrase of at least 12 characters. Encryption uses PBKDF2-HMAC-SHA256 (600,000 iterations), a random salt and AES-256-GCM, with gzip before encryption. The server stores only the envelope and cannot recover the passphrase. Snapshot limits are 100 bots, 30 text files per bot and 12 million total characters; encrypted payload is capped at 20 MB. Local restoration stages files before swapping workspaces. API keys, saved computer access tokens and OAuth credentials are excluded. Restore is explicit, disables schedules/tool permissions, and does not undo/cancel already-running server jobs.

## Media and voice

Set IMAGE/SPEECH/TRANSCRIBE `BASE_URL`, `MODEL`, `API_KEY` for OpenAI-compatible APIs. Images must return base64 output; video uses xAI's asynchronous JSON protocol, not arbitrary video API formats. Video check polls an existing request and never creates another generation. File media is capped at 20 MB; audio uploads at 8 MB. Jobs interrupted by restart are not automatically rebilled. Provider subscriptions and API credit are separate.

Set `REALTIME_API_KEY` and `REALTIME_MODEL` for the OpenAI Realtime browser portal. It uses the unified `/v1/realtime/calls` WebRTC setup; project credentials remain on the server. The page requests microphone permission and ends its peer connection after five minutes or when closed. That client timer is not a guaranteed provider spending cap. No external-action tools are attached to the voice session. Use a server/account access token in the browser portal; it stays in memory rather than localStorage.

## Knowledge and documents

Import a file into local workspace, View → Copy to server knowledge, then explicitly Index for semantic search. Set EMBEDDING_BASE_URL/MODEL/API_KEY. The API batches up to 40 chunks of roughly 2,000 characters per document; split longer source documents before semantic indexing. Each search embeds one query and compares vectors with the same endpoint/model fingerprint. Set AGENT_SEMANTIC_RAG=1 only if you want server vision jobs to issue additional embedding calls. Phone agents have a separate opt-in semantic retrieval toggle.

Local XLSX supports up to 10 MB compressed, 20 MB expanded, 256 columns, 20,000 cells and 300,000 output characters. Server document extraction supports 10 MB source, up to 200 PDF pages/100,000 workbook cells and one million output characters. Truncation is reported. Neither path runs macros/formulas or performs OCR.

## Stripe

Set STRIPE_SECRET_KEY and an HTTPS STRIPE_RETURN_URL. Register `/payments/webhook` and set STRIPE_WEBHOOK_SECRET. Amounts are integer smallest currency units (e.g. INR paise), not a displayed rupee float. Owner queues a checkout, reviewer approves it, Stripe creates a payment link, and a customer completes checkout themselves. Only a valid signed webhook with `payment_status=paid` marks it paid. Creating/visiting a link is not proof of payment. Stripe availability and merchant eligibility depend on your account/country; the app does not create an account or bypass eligibility.

## Verification limits

CI checks build/signature packaging, provider contracts, server contracts with mocked vendors, real desktop/RFB I/O and Android emulator crypto/Excel behavior. Contract fixtures prove request handling and approval boundaries, not upstream account activation, model quality, production scale or availability. Physical phone, live OAuth, real generation/voice and a live Stripe transaction remain unverified. The service remains a trusted shared-container deployment; see the security boundary in computer/README.md. It is not a hardened multi-tenant VM service.
