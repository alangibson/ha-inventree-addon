# InvenTree Home Assistant add-on

<img src="ha-inventree-addon/icon.png" alt="InvenTree icon" width="128">

Runs the official [inventree/inventree](https://hub.docker.com/r/inventree/inventree)
image, pinned to **1.6.4**, on amd64 and aarch64. Includes
[Supplier Scout](https://github.com/getpwnam/inventree-supplier-scout) **0.1.2**,
[InvenTree KiCad](https://github.com/afkiwers/inventree_kicad) **2.4.1**, and
[Smart Parts](https://github.com/0neShot/inventree-smart-parts) **1.2.0**.

Based on the repository layout and official-image wrapper approach of
[argaar/ha-part-db-app](https://github.com/argaar/ha-part-db-app).
InvenTree itself is not built from source. The wrapper adds Nginx, configuration,
database initialization, and supervision of the web server and background worker.

The add-on icon is from [InvenTree 1.6.4](https://github.com/inventree/InvenTree/blob/1.6.4/assets/images/logo/inventree.png), used under the MIT license; see [LICENSE](LICENSE).

## Install locally

1. Copy the `ha-inventree-addon` directory into `/addons/ha-inventree-addon` on your Home Assistant
   OS or Supervised host (for example using the Samba or SSH add-on).
2. Open **Settings → Apps / Add-ons → Store**, then check for updates from the
   three-dot menu. Install **InvenTree** from **Local apps / Local add-ons**.
3. Set `site_url` to the exact address you will use, such as
   `http://homeassistant.local:8086`. Administrator options are optional.
4. Start the add-on. Initial database setup can take several minutes.
5. Open the Web UI and sign in with `admin` / `password` (or your configured credentials).
6. Activate Supplier Scout under **Settings → Plugins** and configure your
   supplier company and API credentials; see [the documentation](ha-inventree-addon/DOCS.md).

To distribute this as a repository, publish this directory to a Git repository
and add that repository URL in the Home Assistant store's Repositories dialog.
No prebuilt add-on image or publishing account is required: Home Assistant builds
the wrapper locally. `repository.yaml` intentionally has no unpublished URL.

## Run with Docker Compose

To run the same image with all bundled plugins outside Home Assistant:

```sh
docker compose up -d --build
docker compose logs -f inventree
```

Open `http://localhost:8086` and sign in with **admin / password** on a new
installation. Change that password after signing in. No `options.json` or `.env`
file is required. Existing accounts and passwords are not reset.

To customize standalone settings, optionally copy `.env.example` to `.env` and
set native `INVENTREE_*` environment variables. For remote access, set
`INVENTREE_SITE_URL` to the server's actual hostname/IP and port. Activate and
configure the bundled plugins as described in [DOCS.md](ha-inventree-addon/DOCS.md).

Home Assistant's `/data/options.json` is read automatically when available.
Compose no longer mounts a local `options.json`; migrate any custom values from
that file to `.env` before recreating an existing standalone installation,
especially external database settings. The old file is left untouched.

The `inventree-data` named volume holds the SQLite database, media, and application
keys. `docker compose down` retains this data; adding `--volumes` deletes it.
Stop the service before backing up the volume. Compose does not provide Home
Assistant's automatic backup integration.

After changing `.env`, run `docker compose up -d --force-recreate` to apply it.
Changing administrator options does not reset an existing
password. If you change the published port in `docker-compose.yml`, also update
`INVENTREE_SITE_URL` in `.env`.

## Behavior

- Web interface on port **8086** by default; no ingress support.
- SQLite database, media, configuration, and secrets persist under `/data/ha-inventree-addon`.
- Optional external PostgreSQL database.
- Background tasks run in the same container, with a single worker.
- Attachments require InvenTree authentication; static frontend assets are public.
- Cold Home Assistant backups stop the add-on for a consistent SQLite backup.

See [DOCS.md](ha-inventree-addon/DOCS.md) for configuration, backups, and troubleshooting.

## Development

```sh
python3 -m unittest discover -s tests -v
docker build -t ha-inventree:test ha-inventree-addon
python3 tests/smoke.py ha-inventree:test
python3 tests/smoke.py ha-inventree:test --standalone
```

The smoke test requires Docker and PyYAML. It creates an isolated container and
temporary data, then removes them. It tests fresh initialization, login, static
assets, media authentication, bundled plugin discovery, restart persistence,
and graceful shutdown. The standalone mode also checks startup without an
options file and login with admin/password. It does not contact supplier APIs.

For an upstream update, change the image tag in `ha-inventree-addon/Dockerfile` and
`ha-inventree-addon/build.yaml`, bump `ha-inventree-addon/config.yaml`, update the changelog,
and repeat the smoke test. Update the pinned plugin version and wheel hash in
`ha-inventree-addon/requirements-plugins.txt` when upgrading bundled plugins.

## License

The wrapper is MIT licensed; see [LICENSE](LICENSE). InvenTree and its plugins
retain their own licenses. Template attribution is retained in LICENSE.
