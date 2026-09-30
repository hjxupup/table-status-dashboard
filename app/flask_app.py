"""Original dashboard, with an explicit offline snapshot mode for demonstrations."""
import atexit
import copy
import json
import os
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from flask import Flask, abort, jsonify, render_template, request

from .storage import Storage, init_db

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env')


class SnapshotMetadataService:
    """Read archived metadata without contacting Hive or inventing newer timestamps."""

    def __init__(self, source_file):
        payload = json.loads(Path(source_file).read_text(encoding='utf-8'))
        self.snapshots = {s['table_name']: s for s in payload['snapshots']}
        self.captured_at = payload['captured_at']

    def load_target_tables(self):
        return list(self.snapshots)

    def _analyze_sync(self, table_name, specific_date_columns=None):
        meta = copy.deepcopy(self.snapshots[table_name])
        for col in specific_date_columns or []:
            if col not in meta.get('date_ranges', {}):
                raise ValueError('This column has no saved range; live Hive access is required.')
        return meta


def monitoring_status(meta, now=None, max_age_hours=24):
    """Flag old snapshots and inconsistent metrics; consumers can inspect this API."""
    now = now or datetime.now(ZoneInfo(os.getenv('METADATA_TIMEZONE', 'Asia/Shanghai'))).replace(tzinfo=None)
    reasons = []
    try:
        analyzed = datetime.strptime(meta['analysis_time'], '%Y-%m-%d %H:%M:%S')
        age_hours = (now - analyzed).total_seconds() / 3600
        if age_hours > max_age_hours:
            reasons.append('stale_snapshot')
        elif age_hours < -0.1:
            reasons.append('future_analysis_time')
    except (ValueError, TypeError, KeyError):
        age_hours = None
        reasons.append('missing_analysis_time')
    row_count, pk_count = meta.get('row_count'), meta.get('pk_distinct_count')
    if row_count is None:
        reasons.append('missing_row_count')
    elif row_count < 0:
        reasons.append('negative_row_count')
    if pk_count is not None and row_count is not None and pk_count != row_count:
        reasons.append('primary_key_count_mismatch')
    return {'status': 'attention' if reasons else 'ok', 'reasons': reasons,
            'snapshot_age_hours': round(age_hours, 2) if age_hours is not None else None}


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DASHBOARD_MODE=os.getenv('DASHBOARD_MODE', 'snapshot'),
        SQLALCHEMY_DATABASE_URL=os.getenv('SQLALCHEMY_DATABASE_URL',
                                         f'sqlite:///{ROOT / "instance" / "metadata.db"}'),
        SNAPSHOT_SOURCE=str(ROOT / 'data' / 'snapshots.json'),
        ENABLE_SCHEDULER=os.getenv('ENABLE_SCHEDULER', 'true').lower() == 'true',
        RETENTION_DAYS=int(os.getenv('RETENTION_DAYS', '7')),
        MAX_SNAPSHOT_AGE_HOURS=float(os.getenv('MAX_SNAPSHOT_AGE_HOURS', '24')),
    )
    app.config.update(config or {})
    mode = app.config['DASHBOARD_MODE']
    if mode not in ('snapshot', 'live'):
        raise ValueError('DASHBOARD_MODE must be snapshot or live.')
    (ROOT / 'instance').mkdir(exist_ok=True)
    database_url = app.config['SQLALCHEMY_DATABASE_URL']
    engine = init_db(database_url)
    storage = Storage(database_url)
    analyzer = app.config.get('ANALYZER')
    if analyzer is None:
        if mode == 'snapshot':
            analyzer = SnapshotMetadataService(app.config['SNAPSHOT_SOURCE'])
        else:
            # JDBC and Java are only required when live mode is explicitly enabled.
            from .services.analyzer import TableMetadataService
            analyzer = TableMetadataService()
    tables = analyzer.load_target_tables()
    allowed_tables = set(tables)
    table_locks = {table: Lock() for table in tables}
    favorites_lock = Lock()
    refresh_lock = Lock()
    background = {'refreshing': False, 'initial_since': None, 'errors': []}

    if mode == 'snapshot':
        for table in tables:
            if storage.latest_snapshot_for_table(table) is None:
                storage.save_snapshot(analyzer._analyze_sync(table))

    def require_table(table):
        if table not in allowed_tables:
            abort(404, description='Table is not in target_tables.txt.')

    def snapshot(table):
        require_table(table)
        data = storage.latest_snapshot_for_table(table)
        if data is None:
            abort(404, description='No saved metadata for this table.')
        # Expose only fields consumed by the public dashboard.
        data = {key: value for key, value in data.items() if key in {
            'table_name', 'analysis_time', 'create_time', 'row_count',
            'pk_distinct_count', 'column_count', 'physical_size_bytes',
            'date_columns', 'date_ranges',
        }}
        size = data.get('physical_size_bytes')
        data['physical_size_gb'] = round(size / (1024 ** 3), 4) if size is not None else None
        favs = storage.list_favorites(table)
        data['favorites'] = [f['column_name'] for f in favs]
        data['default_favorite'] = next((f['column_name'] for f in favs if f['is_default']), None)
        data['source_mode'] = mode
        return data

    def analyze(table, columns=None):
        require_table(table)
        with table_locks[table]:
            meta = analyzer._analyze_sync(table, specific_date_columns=columns)
            if mode == 'live':
                previous = storage.latest_snapshot_for_table(table)
                if columns and previous:
                    ranges = dict(previous.get('date_ranges') or {})
                    ranges.update(meta.get('date_ranges') or {})
                    meta['date_ranges'] = ranges
                storage.save_snapshot(meta)
            # A snapshot reload must not masquerade as a new production analysis.
            return snapshot(table)

    def refresh_all():
        if not refresh_lock.acquire(blocking=False):
            return
        background.update(refreshing=True, initial_since=datetime.now().isoformat(), errors=[])
        try:
            for table in tables:
                try:
                    analyze(table)
                except Exception:
                    background['errors'].append(table)
                    app.logger.exception('Metadata analysis failed for %s', table)
        finally:
            background.update(refreshing=False, initial_since=None)
            refresh_lock.release()

    scheduler = None
    if mode == 'live' and app.config['ENABLE_SCHEDULER']:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler()
        scheduler.add_job(refresh_all, 'interval', hours=1, id='refresh_job', max_instances=1)
        scheduler.add_job(lambda: storage.cleanup_older_than(app.config['RETENTION_DAYS']),
                          'interval', hours=1, id='cleanup_job', max_instances=1)
        scheduler.start()
        atexit.register(lambda: scheduler.shutdown(wait=False) if scheduler.running else None)
        if not any(storage.latest_snapshot_for_table(t) for t in tables):
            Thread(target=refresh_all, daemon=True).start()

    app.extensions['status_dashboard'] = {
        'storage': storage, 'analyzer': analyzer, 'scheduler': scheduler, 'engine': engine,
    }

    @app.errorhandler(400)
    @app.errorhandler(404)
    @app.errorhandler(422)
    def api_error(error):
        return jsonify(error=error.description), error.code

    @app.get('/')
    def index():
        data = [storage.latest_snapshot_for_table(t) for t in tables]
        last_refresh = max((d['analysis_time'] for d in data if d), default=None)
        return render_template('index.html', tables=tables, last_refresh=last_refresh, mode=mode)

    @app.get('/api/ensure_data')
    def ensure_data():
        has_data = any(storage.latest_snapshot_for_table(t) for t in tables)
        return jsonify(refreshing=background['refreshing'], has_data=has_data,
                       initial_since=background['initial_since'], validating=False,
                       validation_since=None, source_mode=mode, errors=background['errors'])

    @app.get('/api/table/<path:table_name>')
    def api_table(table_name):
        return jsonify(snapshot(table_name))

    @app.post('/api/table/<path:table_name>/refresh')
    def refresh_single(table_name):
        require_table(table_name)
        try:
            return jsonify(analyze(table_name))
        except ValueError as exc:
            abort(422, description=str(exc))
        except Exception:
            app.logger.exception('Metadata analysis failed for %s', table_name)
            return jsonify(error='Hive analysis failed; check server logs and JDBC configuration.'), 502

    @app.get('/api/table/<path:table_name>/time_spans')
    def time_spans(table_name):
        data = snapshot(table_name)
        return jsonify(table_name=table_name, columns=data['date_columns'],
                       spans=data['date_ranges'], favorites=data['favorites'],
                       default_favorite=data['default_favorite'])

    @app.post('/api/table/<path:table_name>/select_time_column')
    def select_time_column(table_name):
        data = snapshot(table_name)
        col = (request.get_json(silent=True) or {}).get('time_column')
        if not col or col not in data.get('date_columns', []):
            abort(400, description='Choose a valid time column.')
        if col in data.get('date_ranges', {}):
            return jsonify(data)
        if mode == 'snapshot':
            abort(422, description='No saved range for this column; live Hive access is required.')
        try:
            return jsonify(analyze(table_name, [col]))
        except Exception:
            app.logger.exception('Time-column analysis failed for %s', table_name)
            return jsonify(error='Could not calculate this column range.'), 502

    @app.post('/api/table/<path:table_name>/favorite')
    def add_favorite(table_name):
        data = snapshot(table_name)
        col = (request.get_json(silent=True) or {}).get('column')
        if not col or col not in data.get('date_columns', []):
            abort(400, description='Choose a valid time column.')
        with favorites_lock:
            if storage.is_favorited(table_name, col):
                abort(400, description='已收藏此时间列')
            if storage.count_favorites(table_name) >= 5:
                abort(400, description='收藏不能超过五个')
            storage.add_favorite(table_name, col)
        if mode == 'live' and col not in data.get('date_ranges', {}):
            try:
                analyze(table_name, [col])
            except Exception:
                app.logger.exception('Favorite range calculation failed for %s', table_name)
        updated = snapshot(table_name)
        return jsonify(ok=True, favorites=updated['favorites'], date_ranges=updated['date_ranges'])

    @app.delete('/api/table/<path:table_name>/favorite/<path:column_name>')
    def remove_favorite(table_name, column_name):
        require_table(table_name)
        with favorites_lock:
            if not storage.remove_favorite(table_name, column_name):
                abort(404, description='不存在此收藏')
        data = snapshot(table_name)
        return jsonify(ok=True, favorites=data['favorites'], date_ranges=data['date_ranges'])

    @app.post('/api/refresh')
    def refresh():
        Thread(target=refresh_all, daemon=True).start()
        return jsonify(status='refresh triggered', source_mode=mode), 202

    @app.get('/api/monitoring')
    def monitoring():
        results = []
        for table in tables:
            meta = storage.latest_snapshot_for_table(table)
            status = monitoring_status(meta or {}, max_age_hours=app.config['MAX_SNAPSHOT_AGE_HOURS'])
            results.append(dict(table_name=table, **status))
        return jsonify(source_mode=mode, table_count=len(results),
                       attention_count=sum(r['status'] != 'ok' for r in results), tables=results)

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=int(os.getenv('PORT', '8000')))
