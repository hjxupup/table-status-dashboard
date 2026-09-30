# Table Status Dashboard

**[Live Demo — Open the Dashboard](https://table-status-dashboard-jiaxin.hjxupup.chatgpt.site/)**

The hosted demo is public and requires no sign-in, installation, or deployment.

A reproduction of the original Python / Flask / SQLAlchemy table-metadata dashboard. It retains the original card grid, Chinese field labels, green cache buttons, blue analysis buttons, time-column dropdowns, and star favorites.

This GitHub-ready bundle preserves the dashboard's visible historical metrics, table headings, time-column labels and timestamps. It includes the Flask backend, a prebuilt `docs/` website, and a self-contained `Table_Status_Dashboard.html` preview.

**[GitHub upload and Pages instructions](GITHUB_UPLOAD.md)**: extract this bundle and upload its contents to your repository. The website is already built.

## What the project solves

Downstream analysis depends on understanding whether source tables have usable and consistent metadata. This dashboard centralizes table-analysis timestamps, row counts, distinct primary-key counts, column counts, physical sizes, and minimum/maximum values of time columns. Operators can inspect many tables in one page instead of repeatedly running separate Hive queries.

This distribution includes one historical display snapshot for each of the 39 dashboard cards. Only fields used by the webpage are included. The table headings, time-column labels, metrics and timestamps shown on the webpage remain accessible to visitors; this package protects internal connections and non-display source metadata. See [PRIVACY.md](PRIVACY.md) for the exact boundary.

## Original application and reproduction changes

The original application collected Hive/Kyuubi metadata over JDBC, stored snapshots through SQLAlchemy, refreshed hourly with APScheduler, and provided a Flask/Jinja interface with vanilla JavaScript. Its original monitoring workflow relied on the displayed metrics; the supplied source did not contain a downstream enforcement mechanism.

This reproduction adds an explicit `snapshot` mode, optional `/api/monitoring` flags, and a portable static export. It fixes the frontend bug where updating favorites or loading time spans erased existing card metrics. It also preserves the selected time column across cache refreshes, validates table/column requests, and fixes JDBC jar configuration so explicit driver paths work without a server-specific Kyuubi installation directory.

The original `最后刷新` field continues to display Hive's recorded **Created Time** to preserve the interface. Created Time is not a reliable substitute for a source table's actual data-refresh timestamp. The new monitoring API evaluates the age of the metadata analysis, not the age of every business record.

## Supported modes

| Mode | Data source | Reanalyze button | Favorites | Hive / Java needed |
| --- | --- | --- | --- | --- |
| Flask snapshot mode | Supplied historical snapshots | Reads the saved metadata again; does not change its analysis timestamp | Local SQLite | No |
| Flask live mode | Configured Hive/Kyuubi JDBC connection | Runs metadata queries and saves a new snapshot | Local SQLite | Yes |
| Hosted/static demo | Same archived snapshot export | Reads archived metadata in the browser | Each visitor's browser storage | No |

The hosted static demo is a faithful frontend reproduction. It does not run a Flask server, SQLAlchemy, or JDBC in the browser. The full Python backend is included separately in this repository.

## Run locally on Windows

Requires Python 3.11 or newer. Open a terminal in this folder:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:8000**. No credentials are needed for the default snapshot mode. On the first run, the application creates `instance/metadata.db` and imports the 39 bundled snapshots. The original source database and its full history are excluded.

With an existing Python environment:

```powershell
python -m pip install -r requirements.txt
python run.py
```

## Run on macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

## Restore live Hive analysis

Install the optional JDBC dependencies, install a supported Java runtime and obtain the appropriate Hive/Kyuubi JDBC driver jars:

```powershell
python -m pip install -r requirements-live.txt
Copy-Item .env.example .env
```

Edit `.env` with your own environment:

```dotenv
DASHBOARD_MODE=live
JDBC_URL=jdbc:hive2://your-hive-host:10000/default
JDBC_DRIVER_CLASS=org.apache.kyuubi.jdbc.KyuubiHiveDriver
JDBC_DRIVER_JAR_PATH=D:\drivers\kyuubi-hive-jdbc.jar
HIVE_USERNAME=your_username
HIVE_PASSWORD=your_password
```

Multiple jar paths on Windows can be separated by `;`. If explicit jar paths are absent, the connector also checks `$KYUUBI_HOME/jars`. Actual live-source table and primary-key configuration is excluded. To enable live mode, copy `target_tables.txt.example` to `target_tables.txt` and `table_primary_keys.json.example` to `table_primary_keys.json`, and edit those private files in your own environment. Both filenames and `.env` are ignored by Git. Snapshot mode uses the display dataset and needs neither file.

Then run `python run.py`. Live mode refreshes metadata once an hour and retains seven days of snapshots by default. Use one server worker when the in-process scheduler is enabled, so hourly jobs are not duplicated. Large tables require expensive `COUNT` and `MIN/MAX` queries; refreshing browser cache does not repeat those queries, while live reanalysis does.

Live connectivity could not be validated outside the original company network. Snapshot-mode startup and routes are tested without opening JDBC connections.

## Docker

```bash
docker build -t table-status-dashboard .
docker run --rm -p 8000:8000 table-status-dashboard
```

This Dockerfile runs snapshot mode with Gunicorn. The standalone Python command above uses Flask's local development server. A live-mode container additionally requires Java and JDBC dependencies and driver files.

## Optional: export for GitHub Pages or static hosting

The live demo above is already deployed. These steps are only needed to host your own copy.

```bash
python tools/build_demo.py
python -m http.server 8001 --directory web-demo
```

Open **http://127.0.0.1:8001**. The `web-demo` directory is self-contained. It uses relative asset paths and works under a GitHub Pages repository subpath as well as at a site's root.

To create a single HTML file that can be opened by double-clicking:

```bash
python tools/build_demo.py --standalone Table_Status_Dashboard.html
```

This embeds the historical dataset, styles and browser interactions in one file. Browser privacy settings may restrict persistence of favorites for local files; the dashboard still works with in-memory favorites.

For GitHub Pages, the included `docs/` folder is already built:

1. Upload `docs` together with the source files; keep `README.md` at the repository root.
2. Open **Settings → Pages** and choose **Deploy from a branch**.
3. Select your default branch (usually `main`) and the `/docs` folder, then save.
4. Copy the published URL into the README and the repository's **About → Website** field.

To rebuild both included previews after making changes:

```bash
python tools/build_demo.py --output docs --standalone Table_Status_Dashboard.html
```

GitHub Pages serves the archived-data frontend. The Flask backend and live Hive connection can be run separately using the instructions above.

The bundle retains the visible display metrics. Original databases, actual live-source table/key configuration, credentials, internal environment identifiers, server-specific driver paths and non-display source fields are excluded. The public API exposes only webpage fields. Local snapshot mode recreates its SQLite database from the display snapshots. Publicly displayed values, including table headings and time-column labels, can still be inspected in browser tools.

## API reference (Flask)

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/api/ensure_data` | GET | Initial refresh / available-data state |
| `/api/table/<table>` | GET | Latest saved snapshot and favorites |
| `/api/table/<table>/refresh` | POST | Analyze live or read an archived snapshot |
| `/api/table/<table>/time_spans` | GET | Time columns, ranges and favorites |
| `/api/table/<table>/select_time_column` | POST | Select a column; calculate a missing range in live mode |
| `/api/table/<table>/favorite` | POST | Add a valid time column; maximum five per table |
| `/api/table/<table>/favorite/<column>` | DELETE | Remove a favorite |
| `/api/refresh` | POST | Trigger a background batch refresh |
| `/api/monitoring` | GET | Flag old/missing analysis metadata and primary-key count mismatches |

`MAX_SNAPSHOT_AGE_HOURS` controls the new stale-snapshot threshold; its default is 24 hours. `METADATA_TIMEZONE` defaults to `Asia/Shanghai`, matching the original analyzer's timestamp convention. This API supplies flags for consumers. It does not automatically stop external downstream jobs or guarantee that nobody uses outdated information.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

The tests exercise offline startup, all 39 rendered cards, preservation of real analysis timestamps during snapshot refresh, column/favorite validation and limits, merging of selectively computed live time ranges, and stale/inconsistent metadata detection.

Privacy regression checks verify that exported snapshots contain only display fields and that the public API excludes source locations and primary-key definitions even if those fields exist in local storage.

The browser adapter can also be checked with Node.js 20+:

```bash
node --test tests/demo-api.test.mjs
```

These checks cover all 39 archived tables, refresh without fabricated timestamps, GitHub Pages subpath loading, self-contained file mode, favorite limits, persistence, and isolation between visitors. These are code checks; the original approved page layout, styles and interactions are preserved. Follow the included guide to publish the website in your own GitHub repository.

## Project layout

```text
app/
  flask_app.py        # App factory, original API paths, explicit snapshot/live modes
  models.py          # SQLAlchemy snapshot and favorite models
  storage.py         # SQLite persistence and retention
  services/
    analyzer.py      # Original Hive metadata query service
    db.py            # Configurable JDBC connector
  templates/
    index.html       # Original page structure
  static/
    styles.css       # Original styles, with small notice/mobile fixes
    app.js           # Original interactions, with metric-preservation fixes
data/snapshots.json   # Latest historical snapshot for each of the 39 tables
tools/build_demo.py   # Export original template for static hosting
tools/demo-api.js     # Browser snapshot/favorites adapter
PRIVACY.md            # Included/excluded data and publication boundary
target_tables.txt.example  # Generic local configuration template
table_primary_keys.json.example  # Generic local configuration template
tests/                # API and monitoring checks
docs/                 # Prebuilt GitHub Pages website
Table_Status_Dashboard.html  # Self-contained local preview
GITHUB_UPLOAD.md       # Upload instructions in Chinese
run.py                # Simple local startup
```
