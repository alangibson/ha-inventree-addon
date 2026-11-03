# 1.6.4-8

- Fix duplicated Ingress prefixes in metadata-driven API requests, including
  supplier selection, by returning absolute local URLs in JSON responses.

# 1.6.4-7

- Add Home Assistant Ingress, Open Web UI, and Show in sidebar support.
- Share port 8086 between Ingress and direct web/API access.
- Adapt frontend routes, API links, redirects and cookies to the Ingress prefix
  without modifying upstream or plugin source files.

# 1.6.4-6

- Remove the site URL option; accept access by hostname or IP while retaining
  authentication and same-origin CSRF protection.

# 1.6.4-5

- Store all InvenTree state under /data/ha-inventree-addon in Home Assistant's
  private data mount; remove the public app_config mount.
- Update Compose, Nginx, and plugin log storage to use the same directory.
- Development storage reset only; no migration from the previous layout.

# 1.6.4-4

- Make Home Assistant options optional; standalone startup uses native
  InvenTree environment variables and working SQLite defaults.
- Bootstrap new installations with admin/password unless overridden.
- Remove the Compose options.json mount and support an optional .env file.

# 1.6.4-3

- Link InvenTree's expected Docker data directory to the existing persistent
  `/config` volume, eliminating INVE-W10 path warnings without moving data.

# 1.6.4-2

- Bundle inventree-kicad-plugin 2.4.1 with its verified wheel hash.
- Bundle Smart Parts 1.2.0 and persist its activity log across image updates.
- Document KiCad plugin activation, integration settings, and database migrations.

# 1.6.4-1

- Initial Home Assistant add-on wrapping the official InvenTree 1.6.4 image.
- Bundle Supplier Scout 0.1.2 with its verified wheel hash.
- Support amd64 and aarch64, persistent SQLite or external PostgreSQL.
- Run migrations, static collection, web server, background worker, and Nginx.
- Protect media with InvenTree authentication and use cold backups.
