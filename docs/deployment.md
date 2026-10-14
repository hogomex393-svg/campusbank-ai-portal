# Deployment and accounts

## Local demonstration

Follow the README setup. Data is stored under `logs/portal.sqlite3`, excluded from Git. On a fresh local database, register the owner account first. That account can choose the staff role and create staff invitations. Use a second account/browser for the customer and a separate browser/computer for staff.

The server keeps its terminal occupied while serving. A terminal that does not return to the prompt after successful startup is expected. Open the URL after startup completes; stop with Ctrl+C.

If needed, the local server administrator can use `python -m bankbot.reset_password`. It prompts for the target and a new password without exposing the password. This is a server-side recovery utility, not an unauthenticated web reset endpoint; it preserves records and revokes the target's existing sessions.

## Same-network demonstration

Start with `python -m bankbot.web --host 0.0.0.0 --port 8501`. Other computers use `http://<server-LAN-IPv4>:8501/`; `127.0.0.1` on a different computer points to that computer itself. Keep the host running and allow the intended private-network connection through its firewall. Treat plain-HTTP LAN mode as a controlled synthetic demonstration.

## Public cloud deployment

The current hosted deployment uses Railway, a Python 3.13 Docker image, one service instance, and a persistent `/data` volume. The Docker image copies only runtime source and synthetic knowledge.

1. Build from the repository Dockerfile. Expose the port supplied by the host (`PORT`, default 8080).
2. Attach persistent storage at `/data` before creating accounts. Keep `BANKBOT_DB_PATH=/data/portal.sqlite3`.
3. Set private variables from `.env.cloud.example` in the hosting dashboard. Use `BANKBOT_DEPLOYMENT=cloud`.
4. Set `BANKBOT_PUBLIC_URL` to the bare HTTPS origin, such as `https://your-service.example`, with no path. Railway's public-domain variable can provide this when available.
5. Generate your own unpredictable `BANKBOT_BOOTSTRAP_CODE` (at least 24 characters) and `BANKBOT_TEST_ACCESS_CODE` (at least 12 characters). Keep them private. The public repository contains no usable invitation or initialization codes.
6. Enter your own API key and supported model name privately. Never put keys into a Docker layer or frontend file.
7. Visit the site as the owner and register with the staff identity and bootstrap code. Ordinary early customers never become administrators in cloud mode.
8. Issue single-use staff invitations from the owner workbench. Share the separate test access code privately with invited customer testers.
9. Check `/api/health`, create synthetic chats and support messages, restart the service, and confirm that records remain.

The existing `railway.json` records the configuration used in the deployed prototype. Railway CLI reported a configuration-as-code transition due on **2026-12-01**; verify the provider's supported format before a later redeployment. No automatic connection to the existing hosted service is configured by this GitHub repository.

## Operating limits

Keep one instance/worker with the current SQLite and process-local rate limits. Three-second polling needs network access to the shared server. Model API costs are separate from hosting costs. Free/trial hosting credits and inactivity behavior are provider-dependent; this repository does not promise perpetual free hosting or continuous availability.

Before public expansion, plan backups, account recovery, monitoring, storage migration, centralized quotas, and a security review. Use synthetic demonstration data throughout this version.
