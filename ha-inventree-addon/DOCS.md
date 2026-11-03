# Configuration

Requires a Home Assistant installation supporting apps/add-ons, with an amd64 or
aarch64 CPU. The initial build downloads a large upstream image; allow several
minutes and sufficient free disk space.

| Option | Purpose |
| --- | --- |
| `admin_user` | Initial administrator username, default `admin`. |
| `admin_email` | Initial administrator email, default `admin@example.com`. |
| `admin_password` | Initial administrator password, default `password`. |
| `timezone` | IANA timezone, default `Europe/Vienna`. |
| `database_engine` | `sqlite3` (default) or `postgresql`. |
| `database_host` | PostgreSQL host reachable from the add-on. |
| `database_port` | PostgreSQL port, default `5432`. |
| `database_name` | PostgreSQL database, default `inventree`. |
| `database_user` | PostgreSQL user, default `inventree`. |
| `database_password` | PostgreSQL password. |

The administrator options create a user only if that username does not exist.
Changing the password option does **not** reset an existing account's password;
change it in InvenTree. Change the default password after first login.

`options.json` is never required. Non-empty Home Assistant options take priority
over native `INVENTREE_*` environment variables. Without either, the wrapper
uses persistent SQLite, UTC, and `admin` / `password`.
Compose accepts an optional `.env` file; see `.env.example`. Custom environment
settings such as `INVENTREE_DB_HOST`, `INVENTREE_DB_NAME`, `INVENTREE_DB_USER`, and
`INVENTREE_DB_PASSWORD` can configure an external PostgreSQL database when
`INVENTREE_DB_ENGINE=postgresql`.

Database migrations and static collection run before the server starts. A failed
initialization prevents the server from starting; inspect the add-on logs.

SQLite is suitable for a small personal installation. PostgreSQL is preferable
for heavier use. Create an empty database and user before selecting PostgreSQL.
Changing database options does not migrate existing inventory: use InvenTree's
documented export/import process. No PostgreSQL server or Redis is bundled.
The background worker uses the database-backed queue.

## Web access

Open `http://<HA-hostname-or-IP>:8086`, or the port selected in the Network
section. No hostname option is required. The container listens on HTTP port 8080.
The wrapper accepts any valid hostname and uses the current request for web links.
Legacy `site_url` options and `INVENTREE_SITE_URL` values are ignored.
Authentication and Django's same-origin CSRF checks remain enabled.

Ingress is not enabled yet. InvenTree still requires its own login.
The add-on does not terminate TLS or trust incoming forwarded-protocol headers.
Background jobs without a browser request may need InvenTree's Base URL setting
for absolute links in emails or generated documents. Upstream may log
`No SITE_URL specified`; this is expected for this request-based configuration.

## Supplier Scout

Supplier Scout 0.1.2 is installed at image build time, including its frontend.
Plugin support is enabled. After initial setup:

1. Open **Settings → Plugins** and activate **Supplier Scout**.
2. Enable plugin URL, user interface, and schedule integration in InvenTree's
   plugin settings if disabled.
3. Create your supplier company record in InvenTree.
4. In Supplier Scout's settings, set `DIGIKEY_PK` or `MOUSER_PK` to that company's ID.
5. Set DigiKey client ID/secret or the Mouser search API key.

The Supplier Match action requires a configured supplier company as well as
credentials. Store supplier credentials in InvenTree, not in this repository.
Activation and plugin settings persist in the database. No runtime pip install
is needed. Installing other plugins through the UI is not managed by this
wrapper and package installations may be lost when the image is replaced.

See the [Supplier Scout guide](https://github.com/getpwnam/inventree-supplier-scout)
for supplier setup details. Live supplier requests require your own API access.

## KiCad HTTP Library plugin

`inventree-kicad-plugin` 2.4.1 is bundled in the image. To use it:

1. Enable **URL Integration**, **App Integration**, and **Check plugins on startup**
   in InvenTree's plugin settings.
2. Activate **KiCadLibraryPlugin** under **Settings → Plugins**.
3. Restart the add-on (or run `docker compose restart inventree`). Startup runs
   migrations to create the activated plugin's database tables.
4. Configure KiCad categories in `/admin/inventree_kicad/` and create an API token
   for your KiCad user.
5. Configure a KiCad HTTP library with your InvenTree origin followed by
   `/plugin/kicad-library-plugin` as its root URL.

KiCad still needs matching symbol and footprint libraries installed locally.
See the [upstream setup guide](https://github.com/afkiwers/inventree_kicad) for
category mapping and the `.kicad_httplib` format.

For an existing Compose installation, install the updated image with
`docker compose up -d --build`. The data volume is retained.

## Smart Parts

Smart Parts 1.2.0 is bundled in the image. Activate **SmartParts** in the Plugin
Admin Center and enable the upstream-required App, URL, navigation, interface,
and event integrations. Restart the add-on after activation.

Open `/plugin/smartparts/` at your InvenTree origin to access the dashboard.
Configure distributor API credentials in Smart Parts' settings; these are
separate from Supplier Scout's settings. The activity log is stored at
`/data/ha-inventree-addon/smart_parts_activity.jsonl` so it survives container replacement.

See the [Smart Parts guide](https://github.com/0neShot/inventree-smart-parts)
for scanner, PureScan, and distributor configuration. This add-on bundles the
published PyPI release rather than tracking unreleased GitHub changes.

## Storage and backups

All InvenTree data lives in `/data/ha-inventree-addon` inside the container.
Home Assistant provides the private persistent `/data` mount automatically.
Its `/data/options.json` remains separate and is only read by the wrapper.
Compose mounts its named volume directly at `/data/ha-inventree-addon`.
The application directory contains:

| Path | Data |
| --- | --- |
| `inventree.sqlite3` | Local inventory database (SQLite mode only) |
| `media/` | Uploaded images and attachments |
| `static/` | Generated frontend and plugin assets |
| `secret_key.txt`, `oidc.pem` | Persistent application keys |
| `config.yaml` | Additional upstream settings; add-on options take precedence |
| `plugins/`, `plugins.txt` | Upstream plugin paths |
| `backup/` | Upstream backup destination |
| `smart_parts_activity.jsonl` | Smart Parts activity log |

Include the add-on in Home Assistant backups. Cold backups stop it while data
is copied. Back up before an upgrade: migrations may not be reversible, and
downgrading the image alone does not restore the database. Restore the matching
backup instead. External PostgreSQL data must be backed up separately, together
with media and application keys. Uninstalling the add-on removes its private
data; retain a backup before uninstalling.

## Troubleshooting

- **INVE-W3 (Could not detect git information):** the official production image
  contains release files rather than a Git checkout. InvenTree 1.6.4 can emit
  this during early startup even though its commit metadata is present. It does
  not indicate a database or configuration problem.
- **INVE-W10 (configuration directory):** `/home/inventree/data` resolves to
  `/data/ha-inventree-addon`, matching the application's persistent directory.
- **Startup exits immediately:** validate any configured URL/timezone and
  check database connectivity for PostgreSQL.
- **CSRF errors:** access the UI and API through the same origin and check any reverse proxy configuration.
- **Blank frontend:** inspect migration/static collection logs and restart.
- **Supplier Scout is not visible:** activate it, enable UI/URL integration, and
  configure a supplier company ID as well as credentials.
- **A service exits:** the wrapper stops all services so Home Assistant can
  report the failure. Enable the Home Assistant Watchdog if desired.
