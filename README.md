# Table Status Dashboard

**[Live Demo — Open the Dashboard](https://hjxupup.github.io/table-status-dashboard/)**

The demo is hosted on GitHub Pages and can be opened without signing in or installing anything.

A web dashboard for inspecting Hive table metadata, developed from a table-monitoring project during an eBay internship. It brings table size, row counts, primary-key distinct counts, and time-column ranges into one interface so analysts can review the state of their data before using it in downstream analysis.

The public demo displays real historical metadata snapshots for **39 tables**, with their recorded metrics and timestamps. The repository includes the Python backend, an interactive frontend, and a static version for browser access.

## Project Background

When analysis depends on many warehouse tables, checking each table separately can involve repeated SQL queries and manual comparisons. Questions such as “How many records are available?”, “Does the distinct-key count match the row count?”, and “What time period does this column cover?” are easy to overlook when the answers are scattered across different tools.

This project centralizes those checks in a card-based dashboard. It gives analysts a consistent view of table metadata and makes changes in data volume, key counts, and time coverage easier to inspect. The goal is to support informed data-quality checks before further analysis.

## Key Features

- **Table overview:** view row counts, distinct primary-key counts, column counts, physical storage size, and metadata-analysis timestamps across 39 tables.
- **Time-range inspection:** select a time column and inspect its saved minimum and maximum values.
- **Favorite columns:** save frequently used time columns, with a maximum of five favorites per table.
- **Separate refresh actions:** reload saved metadata through cache controls, or request a new analysis when running with a configured live source.
- **Scheduled collection:** in live mode, refresh table metadata hourly and retain snapshots for seven days by default.
- **Monitoring API:** flag missing metadata, old analysis snapshots, and differences between row counts and distinct-key counts.
- **Portable demonstration:** browse the project on GitHub Pages or run the Flask application locally using the supplied snapshots.

## Technology Stack

| Layer | Technologies | Role |
| --- | --- | --- |
| Backend | Python, Flask | Application setup, metadata endpoints, refresh controls, and request validation |
| Metadata storage | SQLAlchemy, SQLite | Store table snapshots, analysis timestamps, and favorite-column settings |
| Warehouse access | Hive / Kyuubi JDBC, JayDeBeApi, JPype | Collect metadata from a configured warehouse in live mode |
| Scheduling | APScheduler | Run periodic metadata collection and snapshot cleanup |
| Frontend | Jinja2, HTML, CSS, vanilla JavaScript | Render table cards and handle time-column selection, favorites, and refresh actions |
| Deployment | Docker, Gunicorn, GitHub Pages | Run the backend or publish the static demonstration |
| Validation | pytest, Node.js test runner | Check API behavior, snapshot handling, browser adaptation, and public-field filtering |

## How It Works

### Backend workflow

1. **Collect:** the analyzer connects to a configured Hive/Kyuubi source through JDBC and retrieves table metadata, counts, and time-column ranges.
2. **Store:** SQLAlchemy writes the results to SQLite as timestamped snapshots. Favorites are stored separately from metadata.
3. **Serve:** Flask exposes the latest snapshots through JSON endpoints and renders the dashboard with Jinja2.
4. **Inspect:** the frontend updates table cards, loads selected time ranges, and manages favorite columns.

In live mode, APScheduler runs collection and cleanup jobs in the background. Manual reanalysis follows the same collection and storage workflow.

### Public demo workflow

The GitHub Pages site loads the archived display snapshots from JSON and uses a browser adapter to provide the dashboard interactions. Favorites are stored in each visitor's browser. The demo preserves the original collection timestamps when metadata is reloaded.

GitHub Pages serves the static frontend. Running live warehouse queries requires the Flask backend and a separately configured JDBC connection.

## Engineering Decisions

- **Store metadata before displaying it.** Dashboard reads use saved snapshots, allowing users to inspect results without repeating expensive warehouse queries on every page load.
- **Separate cached reads from analysis.** Refreshing the view and collecting new warehouse metadata are different operations with different costs.
- **Preserve state during UI updates.** Changing a selected time column or updating favorites keeps the card's existing metrics visible.
- **Validate tables and columns.** API requests are checked against the available configuration or snapshots, and favorite limits are enforced on the backend.
- **Keep deployment modes explicit.** Snapshot mode provides a reproducible local demonstration; live mode uses environment-based connection configuration.
- **Control public output.** Exported data and API responses include dashboard display fields, while internal connections and non-display source metadata are excluded from the public edition.

## Available Modes

| Mode | Data source | Refresh / reanalysis | Favorites |
| --- | --- | --- | --- |
| GitHub Pages demo | Archived JSON display snapshots | Reloads the saved metrics and keeps their historical timestamps | Visitor's browser storage |
| Local Flask snapshot mode | Supplied snapshots imported into local SQLite | Reads the saved metadata again | Local SQLite |
| Flask live mode | Configured Hive/Kyuubi connection | Runs queries and saves a new analysis snapshot | Local SQLite |

**Timestamp semantics:** the UI label `最后刷新` displays the source table's recorded **Created Time** for compatibility with the original interface. The `分析时间` field records when metadata was analyzed. The monitoring API evaluates the age of that analysis snapshot; it does not establish the freshness of every underlying business record or automatically block downstream jobs.

## Run Locally

Python **3.11 or newer** is required. The default mode uses the supplied snapshots and needs no warehouse credentials, JDBC driver, or Java installation.

### Windows

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

### macOS / Linux

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

Open **http://127.0.0.1:8000**. On first startup, the application creates `instance/metadata.db` from the supplied display snapshots.

For a browser-only local preview, open `Table_Status_Dashboard.html`. Browser settings may affect whether favorites persist when opening a local file.

## Configure Live Mode

Live mode requires access to your own warehouse, a compatible Java runtime, JDBC driver jars, and local table/key configuration.

Install the optional dependencies and copy the configuration templates:

```powershell
python -m pip install -r requirements-live.txt
Copy-Item .env.example .env
Copy-Item target_tables.txt.example target_tables.txt
Copy-Item table_primary_keys.json.example table_primary_keys.json
```

On macOS / Linux, use `cp` for the three template copies. Edit the local files for your environment. A generic `.env` configuration is:

```dotenv
DASHBOARD_MODE=live
JDBC_URL=jdbc:hive2://your-hive-host:10000/default
JDBC_DRIVER_CLASS=org.apache.kyuubi.jdbc.KyuubiHiveDriver
JDBC_DRIVER_JAR_PATH=/path/to/kyuubi-hive-jdbc.jar
HIVE_USERNAME=your_username
HIVE_PASSWORD=your_password
```

Start the application with `python run.py`. Use one server worker when the in-process scheduler is enabled so collection jobs are not duplicated. Live connectivity must be verified in the configured warehouse environment. Large-table counts and time-range queries can be expensive.

## Docker

```bash
docker build -t table-status-dashboard .
docker run --rm -p 8000:8000 table-status-dashboard
```

The included image runs snapshot mode with Gunicorn. A live-mode container also needs Java, JDBC driver jars, and private connection configuration.

## Static Export and Hosting

The public site is already deployed at **https://hjxupup.github.io/table-status-dashboard/**. It is published from the `docs/` directory on the `main` branch.

To rebuild both the GitHub Pages files and the standalone preview:

```bash
python tools/build_demo.py --output docs --standalone Table_Status_Dashboard.html
```

Commit the updated `docs/` files to the publishing branch to update the demo. See [GITHUB_UPLOAD.md](GITHUB_UPLOAD.md) for deployment instructions.

## Data and Privacy

The public edition contains one historical display snapshot for each of the 39 tables. Displayed table names, time-column names, metrics, and timestamps are accessible to visitors.

Credentials, original databases, internal connection details, actual live-source table/key configuration, server-specific paths, and non-display source fields are excluded. Private configuration stays in local `.env`, `target_tables.txt`, and `table_primary_keys.json` files, which are ignored by Git. See [PRIVACY.md](PRIVACY.md) for the publication boundary and upload guidance.

## Validation

```bash
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
node --test tests/demo-api.test.mjs
```

The checks cover snapshot-mode startup, all 39 cards, table and column validation, favorite limits, preservation of historical timestamps and existing card metrics, time-range merging, monitoring flags, GitHub Pages subpath loading, browser storage, and exclusion of non-display metadata from public output.

## Project Structure

```text
app/
  flask_app.py           # Flask setup and metadata API routes
  models.py             # Snapshot and favorite-column models
  storage.py            # SQLite persistence and retention
  services/             # JDBC connection and metadata analysis
  templates/            # Jinja2 dashboard template
  static/               # CSS and browser interactions
data/snapshots.json      # Archived dashboard display data
docs/                    # Published GitHub Pages frontend
tools/                   # Static export and browser adapter
tests/                   # Python and JavaScript checks
run.py                   # Local application entry point
Dockerfile               # Container setup
PRIVACY.md               # Public-data scope and configuration handling
GITHUB_UPLOAD.md         # GitHub upload and Pages instructions
```
