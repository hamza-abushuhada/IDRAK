# Independent hosted Lab (prepared, not deployed)

Deploy only `tools/idrak-connect-lab` as a separate container service. It has no
dependencies on the IDRAK API, Supabase, Vercel tokens or production environment.
The original `python demo_server.py` two-port localhost runner is preserved.

## Container setup, after approval

1. Build the Dockerfile using this directory as the build context:
   `docker build -t idrak-connect-lab .`
2. Configure a separate service with one replica, port `8765`, an HTTPS reverse
   proxy, and a persistent volume mounted at `/data`, writable by UID `10001`.
   SQLite needs persistent local storage; this runner does not target Vercel
   Functions or ephemeral filesystems. Do not share its volume with IDRAK.
3. Set `IDRAK_LAB_ACCESS_USER` (default `lab`), a random
   `IDRAK_LAB_ACCESS_PASSWORD` of at least 20 characters, and a distinct random
   `IDRAK_LAB_WEBHOOK_SECRET` of at least 32 characters in hosting secret settings.
   Startup refuses missing/default secrets. Do not reuse production credentials.
   `hosted.env.example` lists the names and contains no usable credentials.
4. Start the image. `/health` is public for health checks; all other routes require
   HTTP Basic authentication. Use HTTPS at the proxy before sharing the URL.
5. Open `/pos`, `/shop`, `/admin`, and `/simulator/`. Create a synthetic sale and
   confirm it appears in the simulator, then refund it and check the total.
   Restart the container and confirm the data persists on the mounted volume.

Hosted mode routes the receiver under `/simulator/` on the same origin. Signed
events are delivered directly to the isolated receiver without external HTTP.
It cannot forward events to production IDRAK. Source event feeds remain protected
by the Lab password. Connecting them to a real IDRAK deployment would require a
separate reviewed change for remote URLs, credentials and scheduled sync.

This is a shared, password-protected synthetic demo, not a multi-tenant commerce
service. Everyone with the Lab password sees and changes the same test data.
There are no real payments. Keep real customer data out of it.

## Validation

`python -I -m unittest discover -s tests -p 'test_*.py'`

Tests create temporary SQLite databases and an ephemeral localhost HTTP server;
they do not load any `.env` or contact production. The Docker image builds and
passed a local container smoke check for health, sale delivery and persistence
across restart using a disposable volume and generated test secrets. HTTP smoke
requests ran inside the container because host loopback access was restricted.
Verify external HTTPS routing and volume persistence on the chosen host.

## Pending approval

No remote hosting project, domain, secret or volume has been created. Temporary
local container resources used for verification were removed. Choose
a container host and an independent domain before approval to publish. Publishing
this service does not apply IDRAK migrations or deploy the original application.
