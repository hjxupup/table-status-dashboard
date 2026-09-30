import copy
import json
from datetime import datetime

import pytest

from app.flask_app import create_app, monitoring_status
from app.models import TableSnapshot


@pytest.fixture
def dashboard(tmp_path):
    app = create_app({'TESTING': True, 'DASHBOARD_MODE': 'snapshot', 'ENABLE_SCHEDULER': False,
                      'SQLALCHEMY_DATABASE_URL': f'sqlite:///{tmp_path / "test.db"}'})
    yield app, app.test_client()
    ext = app.extensions['status_dashboard']
    ext['storage'].engine.dispose()
    ext['engine'].dispose()


def test_original_cards_and_offline_startup(dashboard):
    app, client = dashboard
    html = client.get('/').get_data(as_text=True)
    assert html.count('class="table-card"') == 39
    assert 'Table Status Dashboard' in html
    status = client.get('/api/ensure_data').get_json()
    assert status['has_data'] and not status['refreshing']
    assert app.extensions['status_dashboard']['scheduler'] is None


def test_snapshot_refresh_keeps_real_timestamp_and_counts(dashboard):
    app, client = dashboard
    table = app.extensions['status_dashboard']['analyzer'].load_target_tables()[0]
    before = client.get(f'/api/table/{table}').get_json()
    response = client.post(f'/api/table/{table}/refresh')
    assert response.status_code == 200
    after = response.get_json()
    for key in ('analysis_time', 'row_count', 'pk_distinct_count', 'date_ranges', 'physical_size_gb'):
        assert after[key] == before[key]
    with app.extensions['status_dashboard']['storage'].SessionLocal() as session:
        assert session.query(TableSnapshot).count() == 39
    assert client.post('/api/table/not-a-target/refresh').status_code == 404


def test_time_selection_and_favorites_validate_input(dashboard):
    app, client = dashboard
    service = app.extensions['status_dashboard']['analyzer']
    source = next(s for s in service.snapshots.values() if len(s['date_columns']) >= 6)
    table = source['table_name']
    for column in source['date_columns'][:5]:
        assert client.post(f'/api/table/{table}/favorite', json={'column': column}).status_code == 200
    assert client.post(f'/api/table/{table}/favorite', json={'column': source['date_columns'][5]}).status_code == 400
    assert client.post(f'/api/table/{table}/favorite', json={'column': 'invented_column'}).status_code == 400
    column = source['date_columns'][0]
    assert client.post(f'/api/table/{table}/select_time_column', json={'time_column': column}).status_code == 200
    assert client.post(f'/api/table/{table}/select_time_column', json={'time_column': 'invented_column'}).status_code == 400
    assert client.delete(f'/api/table/{table}/favorite/{column}').status_code == 200
    assert len(client.get(f'/api/table/{table}/time_spans').get_json()['favorites']) == 4
    assert client.delete(f'/api/table/{table}/favorite/{column}').status_code == 404


def test_live_partial_analysis_keeps_other_time_ranges(tmp_path):
    initial = {'table_name': 'demo.events', 'analysis_time': '2026-09-30 12:00:00',
               'row_count': 10, 'column_count': 2, 'date_columns': ['created_dt', 'updated_dt'],
               'date_ranges': {'created_dt': {'min_date': '2026-01-01', 'max_date': '2026-01-02'}}}

    class FakeHive:
        def load_target_tables(self):
            return ['demo.events']

        def _analyze_sync(self, table_name, specific_date_columns=None):
            result = copy.deepcopy(initial)
            result['analysis_time'] = '2026-09-30 13:00:00'
            result['date_ranges'] = {'updated_dt': {'min_date': '2026-01-03', 'max_date': '2026-01-04'}}
            return result

    app = create_app({'TESTING': True, 'DASHBOARD_MODE': 'live', 'ENABLE_SCHEDULER': False,
                      'ANALYZER': FakeHive(), 'SQLALCHEMY_DATABASE_URL': f'sqlite:///{tmp_path / "live.db"}'})
    app.extensions['status_dashboard']['storage'].save_snapshot(initial)
    response = app.test_client().post('/api/table/demo.events/select_time_column', json={'time_column': 'updated_dt'})
    assert response.status_code == 200
    assert set(response.get_json()['date_ranges']) == {'created_dt', 'updated_dt'}


def test_stale_and_inconsistent_metadata_are_flagged():
    now = datetime(2026, 9, 30, 12)
    fresh = {'analysis_time': '2026-09-30 11:00:00', 'row_count': 10, 'pk_distinct_count': 10}
    assert monitoring_status(fresh, now=now)['status'] == 'ok'
    stale = dict(fresh, analysis_time='2026-09-28 11:00:00', pk_distinct_count=8)
    reasons = monitoring_status(stale, now=now)['reasons']
    assert 'stale_snapshot' in reasons and 'primary_key_count_mismatch' in reasons
    assert 'missing_analysis_time' in monitoring_status({}, now=now)['reasons']
