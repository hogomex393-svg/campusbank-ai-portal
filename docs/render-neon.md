# Deploy CampusBank on Render and Neon

The web service runs the existing Python application on a Render Free instance.
Neon stores accounts, conversations, submitted requests and support tickets in PostgreSQL.

## Database setup

Create a Neon Free project near the Render service region. The included Blueprint
uses Frankfurt, so AWS eu-central-1 is a suitable database region. Use the pooled
PostgreSQL connection URL for the application, with `sslmode=require`. Store it
privately as `DATABASE_URL`. The application uses a small connection pool and
disables prepared statement caching for transaction-pooler compatibility.

The portal retains its existing account and staff permissions. `BANKBOT_BOOTSTRAP_CODE`
enables the first owner account. Customer registration uses `BANKBOT_TEST_ACCESS_CODE`.
`BANKBOT_STAFF_ACCESS_CODE` enables separate staff accounts through the shared team code.
Keep those values and the model API key in the hosting platform's secret settings.

## Existing records

Obtain a consistent copy of the previous Railway `/data/portal.sqlite3` before
importing. Keep that backup private. Use the migration module against an empty
destination database before directing customers to the new service:

```powershell
python -m bankbot.migrate_database --source C:\private\portal.sqlite3
```

For this command, set `DATABASE_URL` to the direct Neon connection URL privately.
It takes a read-only SQLite backup, upgrades legacy columns in that copy and
imports all portal tables in one PostgreSQL transaction. IDs and password hashes
are preserved. Retrying the same import returns its recorded completion result.
A different import into an occupied database is rejected. The importer updates
identity sequences so subsequent messages and review events receive new IDs.

For the final cutover, run the old service with `BANKBOT_MAINTENANCE_MODE=true`,
wait for its previous deployment to finish draining, then export the final
snapshot. Maintenance blocks every API route except health checks, including
guest-session creation. Keep the new service in maintenance until import and
verification finish, then deploy it with the flag set to `false`.

## Render setup

Push the migration source to GitHub and deploy the repository Dockerfile as one
Free web service. `render.yaml` records the configuration. Set the private values
listed in `.env.render.example`. Render supplies `PORT` and `RENDER_EXTERNAL_URL`,
which the application uses for listening and HTTPS origin checks.

The application refuses to start on Render without a PostgreSQL URL. This avoids
accidentally creating customer accounts on the instance's temporary filesystem.
Keep one worker and one instance because the classroom quotas use process-local state.

Verify `/api/health`, then exercise customer login, a saved conversation and a
staff reply. After a controlled restart, verify the same records again. Check
both Chinese and English messages and a streamed model response before sharing
the new URL.

## Verification

Run the existing suite with `python -m unittest discover -v`. To run the real
PostgreSQL regressions, set `PG_TEST_DATABASE_URL` to a dedicated Neon test branch's
direct connection URL, then run `python -m unittest tests.test_postgres_storage -v`.
Each PostgreSQL test creates and removes its own isolated schema.

Render Free instances sleep after inactivity and can take time to wake. The
database retains the saved records across those service restarts. Neon Free
usage quotas still apply, and model API usage has its separate provider cost.
