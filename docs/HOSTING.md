# Hosting TidalTwin on a VPS

The production Compose stack runs the React frontend, FastAPI backend, PostGIS,
and Caddy. Caddy obtains and renews HTTPS certificates automatically. Only
ports 80 and 443 are public; PostgreSQL and the backend stay on the private
Docker network.

## Requirements

- A Linux VPS with Docker Engine and the Docker Compose plugin.
- A domain name and DNS access. Point an `A` record (and `AAAA` if IPv6 works)
  at the VPS address before starting the stack.
- VPS firewall allows inbound TCP 80/443 and SSH on port 22. UDP 443 is optional
  for HTTP/3.
- At least 4 GB RAM is recommended for building the frontend image and starting
  the API; allow extra disk space for Docker images and database data.

## Deploy

1. Copy this repository onto the VPS (or clone its Git repository).
2. In the project root, copy `.env.production.example` to `.env.production`.
3. Set `TIDALTWIN_DOMAIN` to the DNS name pointing to the VPS. Replace
   `POSTGRES_PASSWORD` with a long random hexadecimal secret, such as the output
   of `openssl rand -hex 32`. Optionally set `CESIUM_ION_TOKEN`.
4. Start the stack:

   ```sh
   docker compose --env-file .env.production -f docker-compose.production.yml up -d --build
   ```

5. Check startup and health:

   ```sh
   docker compose --env-file .env.production -f docker-compose.production.yml ps
   docker compose --env-file .env.production -f docker-compose.production.yml logs -f backend caddy
   ```

   Open `https://<TIDALTWIN_DOMAIN>` after Caddy reports a certificate. API
   documentation is at `https://<TIDALTWIN_DOMAIN>/docs`.

## Updates and backups

Pull or copy the new source, then run the same `up -d --build` command. Database
state is in the Docker volume `db-data`; back it up before server changes. For a
logical backup, run `docker compose ... exec -T db pg_dump -U tidaltwin tidaltwin
> tidaltwin-backup.sql` (replace user/database if customized).

Keep `.env.production` private and outside version control. Do not expose ports
5432 or 8000 through the VPS firewall. The default Compose stack remains for
local development; use `docker-compose.production.yml` for the public site.
