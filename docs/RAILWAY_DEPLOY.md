# Deploy TidalTwin to Railway

Railway deploys each part of the Compose stack as its own service. This setup
uses a PostGIS container with a persistent Railway Volume, the existing FastAPI
Dockerfile, and a Railway-specific frontend image. Only the frontend needs a
public domain; `/api` requests go through its proxy to the private backend.

## Before starting

The repository must be pushed to GitHub because Railway deploys the selected
repository branch. Connect the GitHub repository `dharani1324-dk/Tidal-Twin-`
to Railway and select the branch you want to publish. Current local changes
must be committed and pushed before Railway can build them.

## Create services

Create an empty Railway project and add these three services. Generate the
frontend Railway domain from its Settings → Networking page before setting the
backend CORS variable.

1. **PostGIS database** — add a service from Docker image `postgis/postgis:16-3.4`.
   Name it `postgis`, set `POSTGRES_DB=tidaltwin`, `POSTGRES_USER=tidaltwin`, and
   set `POSTGRES_PASSWORD` to a strong random secret in Railway Variables. Add a
   Railway Volume mounted at `/var/lib/postgresql/data`. Keep the service
   private; do not generate a public TCP proxy.
2. **Backend** — add the GitHub repository. Set its Root Directory to
   `/backend`; Railway detects `backend/Dockerfile`. Name the service `backend`.
   Set its healthcheck path to `/api/v1/health` and timeout to 600 seconds.
   Add these variables:

   ```text
   DATABASE_URL=postgresql+psycopg2://tidaltwin:${{postgis.POSTGRES_PASSWORD}}@postgis.railway.internal:5432/tidaltwin
   DB_HOST=postgis.railway.internal
   DB_PORT=5432
   ENVIRONMENT=production
   CORS_ORIGINS=https://<your-frontend-domain>.up.railway.app
   ```

   Leave the backend without a public domain.
3. **Frontend** — add the same GitHub repository. Set Root Directory to
   `/frontend`, Dockerfile Path to `Dockerfile.railway`, and name the service
   `frontend`. Set variables `PORT=8080` and
   `BACKEND_HOST=backend.railway.internal`; Railway supplies the `PORT` value
   used by Nginx. Generate a public Railway domain
   for this service. Set the frontend healthcheck path to `/`.

Deploy the PostGIS service first, then the backend and frontend. Backend startup
waits for PostGIS, initializes the schema, seeds locations, and tries a best-
effort data refresh before serving requests. If initial setup fails, use the
service logs to identify the failing step before redeploying.

## Verify

Open the generated frontend `*.up.railway.app` URL. Check that the home page
loads and that `/api/v1/health` and `/api/v1/moes/registry` respond through that
same domain. Frontend refreshes on routes such as `/tide` should load the SPA
rather than return a 404.

Do not commit database passwords or Railway tokens. Keep the database private
and preserve its attached volume across deployments.
