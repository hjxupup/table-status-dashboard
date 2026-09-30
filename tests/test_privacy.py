import json
from pathlib import Path

from app.flask_app import create_app

ROOT = Path(__file__).resolve().parents[1]
DISPLAY_FIELDS = {
    'table_name', 'analysis_time', 'create_time', 'row_count',
    'pk_distinct_count', 'column_count', 'physical_size_bytes',
    'date_columns', 'date_ranges',
}


def test_published_dataset_contains_only_display_fields():
    payload = json.loads((ROOT / 'data/snapshots.json').read_text())
    for snapshot in payload['snapshots']:
        assert set(snapshot) <= DISPLAY_FIELDS
    assert json.loads((ROOT / 'docs/data/snapshots.json').read_text()) == payload


def test_public_api_omits_private_metadata_even_when_stored(tmp_path):
    app = create_app({'TESTING': True, 'DASHBOARD_MODE': 'snapshot',
                      'ENABLE_SCHEDULER': False,
                      'SQLALCHEMY_DATABASE_URL': f'sqlite:///{tmp_path / "privacy.db"}'})
    extensions = app.extensions['status_dashboard']
    try:
        source = next(iter(extensions['analyzer'].snapshots.values()))
        private = dict(source, location='hdfs://private.invalid/warehouse',
                       primary_keys=['private_record_key'], table_type='PRIVATE_TYPE',
                       last_modified_time='private_access_time')
        extensions['storage'].save_snapshot(private)
        response = app.test_client().get(f'/api/table/{source["table_name"]}')
        assert response.status_code == 200
        result = response.get_json()
        for key in ('location', 'primary_keys', 'table_type', 'last_modified_time'):
            assert key not in result
        assert 'private.invalid' not in response.get_data(as_text=True)
        assert result['row_count'] == source['row_count']
        assert result['date_ranges'] == source['date_ranges']
    finally:
        extensions['storage'].engine.dispose()
        extensions['engine'].dispose()
