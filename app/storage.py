import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import os

from .models import Base, TableSnapshot, TimeFavorite


def get_engine(database_url=None):
    database_url = database_url or os.getenv('SQLALCHEMY_DATABASE_URL') or 'sqlite:///./metadata.db'
    return create_engine(database_url, connect_args={"check_same_thread": False} if database_url.startswith('sqlite') else {})


def init_db(database_url=None):
    engine = get_engine(database_url)
    Base.metadata.create_all(bind=engine)
    # 轻量级迁移：已有 sqlite 库上补充新列
    try:
        db_url = database_url or os.getenv('SQLALCHEMY_DATABASE_URL') or 'sqlite:///./metadata.db'
        if db_url.startswith('sqlite'):
            with engine.connect() as conn:
                rows = conn.exec_driver_sql("PRAGMA table_info('table_snapshots')").fetchall()
                cols = {r[1] for r in rows}
                if 'pk_distinct_count' not in cols:
                    conn.exec_driver_sql("ALTER TABLE table_snapshots ADD COLUMN pk_distinct_count BIGINT")
                if 'primary_keys_json' not in cols:
                    conn.exec_driver_sql("ALTER TABLE table_snapshots ADD COLUMN primary_keys_json TEXT")
                conn.commit()
    except Exception:
        # 最好努力型迁移失败时不阻塞应用
        pass
    return engine


class Storage:
    def __init__(self, database_url=None):
        self.engine = get_engine(database_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    def save_snapshot(self, metadata: dict):
        session = self.SessionLocal()
        try:
            snap = TableSnapshot(
                table_name=metadata.get('table_name'),
                # 统一使用本地时间；若缺失则用当前本地时间
                analysis_time=datetime.strptime(metadata.get('analysis_time'), '%Y-%m-%d %H:%M:%S') if metadata.get('analysis_time') else datetime.now(),
                last_modified_time=metadata.get('last_modified_time'),
                create_time=metadata.get('create_time'),
                row_count=metadata.get('row_count'),
                pk_distinct_count=metadata.get('pk_distinct_count'),
                column_count=metadata.get('column_count'),
                physical_size_bytes=metadata.get('physical_size_bytes') if isinstance(metadata.get('physical_size_bytes'), int) else None,
                date_columns_json=json.dumps(metadata.get('date_columns', []), ensure_ascii=False),
                date_ranges_json=json.dumps(metadata.get('date_ranges', {}), ensure_ascii=False),
                primary_keys_json=json.dumps(metadata.get('primary_keys', []), ensure_ascii=False),
                location=metadata.get('location'),
                table_type=metadata.get('table_type')
            )
            session.add(snap)
            session.commit()
            return snap.id
        finally:
            session.close()

    def latest_snapshot_for_table(self, table_name: str):
        session = self.SessionLocal()
        try:
            snap = session.query(TableSnapshot).filter(TableSnapshot.table_name == table_name).order_by(TableSnapshot.analysis_time.desc(), TableSnapshot.id.desc()).first()
            if not snap:
                return None
            return {
                'table_name': snap.table_name,
                'analysis_time': snap.analysis_time.strftime('%Y-%m-%d %H:%M:%S'),
                'last_modified_time': snap.last_modified_time,
                'create_time': snap.create_time,
                'row_count': snap.row_count,
                'pk_distinct_count': snap.pk_distinct_count,
                'column_count': snap.column_count,
                'physical_size_bytes': snap.physical_size_bytes,
                'date_columns': json.loads(snap.date_columns_json or '[]'),
                'date_ranges': json.loads(snap.date_ranges_json or '{}'),
                'primary_keys': json.loads(snap.primary_keys_json or '[]') if getattr(snap, 'primary_keys_json', None) is not None else [],
                'location': snap.location,
                'table_type': snap.table_type
            }
        finally:
            session.close()

    def cleanup_older_than(self, days=7):
        # 使用本地时间计算清理阈值（与保存时间保持同一基准）
        cutoff = datetime.now(ZoneInfo(os.getenv('METADATA_TIMEZONE', 'Asia/Shanghai'))).replace(tzinfo=None) - timedelta(days=days)
        session = self.SessionLocal()
        try:
            deleted = session.query(TableSnapshot).filter(TableSnapshot.analysis_time < cutoff).delete(synchronize_session=False)
            session.commit()
            return deleted
        finally:
            session.close()

    # ---- Favorites CRUD ----
    def list_favorites(self, table_name: str):
        session = self.SessionLocal()
        try:
            rows = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name).order_by(TimeFavorite.favorited_at.desc()).all()
            return [
                {
                    'table_name': r.table_name,
                    'column_name': r.column_name,
                    'is_default': r.is_default,
                    'favorited_at': r.favorited_at.strftime('%Y-%m-%d %H:%M:%S')
                } for r in rows
            ]
        finally:
            session.close()

    def count_favorites(self, table_name: str):
        session = self.SessionLocal()
        try:
            return session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name).count()
        finally:
            session.close()

    def is_favorited(self, table_name: str, column_name: str):
        session = self.SessionLocal()
        try:
            return session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.column_name == column_name).first() is not None
        finally:
            session.close()

    def add_favorite(self, table_name: str, column_name: str):
        session = self.SessionLocal()
        try:
            existing = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.column_name == column_name).first()
            if existing:
                return False
            fav = TimeFavorite(table_name=table_name, column_name=column_name, is_default=False)
            session.add(fav)
            session.commit()
            return True
        finally:
            session.close()

    def remove_favorite(self, table_name: str, column_name: str):
        session = self.SessionLocal()
        try:
            fav = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.column_name == column_name).first()
            if not fav:
                return False
            was_default = fav.is_default
            session.delete(fav)
            session.commit()
            if was_default:
                # promote latest remaining as default (optional behavior)
                latest = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name).order_by(TimeFavorite.favorited_at.desc()).first()
                if latest:
                    latest.is_default = True
                    session.commit()
            return True
        finally:
            session.close()

    def set_default_favorite(self, table_name: str, column_name: str):
        session = self.SessionLocal()
        try:
            # reset others
            session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.is_default == True).update({'is_default': False})
            target = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.column_name == column_name).first()
            if not target:
                return False
            target.is_default = True
            session.commit()
            return True
        finally:
            session.close()

    def default_favorite(self, table_name: str):
        session = self.SessionLocal()
        try:
            fav = session.query(TimeFavorite).filter(TimeFavorite.table_name == table_name, TimeFavorite.is_default == True).first()
            return fav.column_name if fav else None
        finally:
            session.close()
