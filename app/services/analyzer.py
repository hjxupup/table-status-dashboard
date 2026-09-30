import os
import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from ..services.db import DBConnector
import re
import json

load_dotenv()


class TableMetadataService:
    """Service that wraps table metadata analysis and adapts existing logic for async use."""

    def __init__(self, target_tables_file: str = None):
        # Do not keep a long-lived DBConnector instance; use per-call connections instead
        self.db = None
        # location of target_tables file
        self.base_dir = os.path.dirname(os.path.dirname(__file__))
        self.target_tables_file = target_tables_file or os.path.join(self.base_dir, '..', 'target_tables.txt')
        # optional local mapping file: { "schema.table": ["pk1","pk2"], ... }
        # used when CONFIG_TABLE is not configured or doesn't contain primary_keys
        self.primary_keys_file = os.getenv('PRIMARY_KEYS_FILE') or os.path.join(self.base_dir, '..', 'table_primary_keys.json')
        self._primary_keys_map = None

    # Note: per-call connections are used; explicit connect/close methods are unnecessary

    def load_target_tables(self):
        path = os.path.abspath(self.target_tables_file)
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            lines = [l.strip() for l in f.readlines() if l.strip()]
        # remove code fences if present
        # cleaned = []
        # for l in lines:
        #     cleaned.append(re.sub(r"[`\\s]+", "", l))
        return lines

    def _load_primary_keys_map(self):
        """Best-effort load of local primary keys mapping file."""
        if self._primary_keys_map is not None:
            return self._primary_keys_map
        path = os.path.abspath(self.primary_keys_file) if self.primary_keys_file else None
        if not path or not os.path.exists(path):
            self._primary_keys_map = {}
            return self._primary_keys_map
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f) or {}
            if not isinstance(raw, dict):
                self._primary_keys_map = {}
                return self._primary_keys_map
            # normalize keys to lowercase for case-insensitive lookup
            norm = {}
            for k, v in raw.items():
                if not k:
                    continue
                if isinstance(v, str):
                    cols = [c.strip() for c in v.split(',') if c.strip()]
                elif isinstance(v, (list, tuple)):
                    cols = [str(c).strip() for c in v if str(c).strip()]
                else:
                    cols = []
                norm[str(k).strip().lower()] = cols
            self._primary_keys_map = norm
            return self._primary_keys_map
        except Exception as e:
            print(f"Could not read PRIMARY_KEYS_FILE {path}: {e}")
            self._primary_keys_map = {}
            return self._primary_keys_map

    async def analyze_tables(self, table_list):
        results = []
        for t in table_list:
            try:
                r = await self.analyze_single_table(t)
                results.append(r)
            except Exception as e:
                print(f"Error analyzing {t}: {e}")
        return results

    def analyze_tables_sync(self, table_list):
        """Synchronous wrapper to analyze many tables (used by Flask app)."""
        results = []
        for t in table_list:
            try:
                results.append(self._analyze_sync(t))
            except Exception as e:
                print(f"Error analyzing {t}: {e}")
        return results

    async def analyze_single_table(self, table_name, specific_date_columns=None):
        loop = asyncio.get_event_loop()
        # call blocking analysis in threadpool
        return await loop.run_in_executor(None, self._analyze_sync, table_name, specific_date_columns)

    def _analyze_sync(self, table_name, specific_date_columns=None):
        """Synchronous analysis using SQL queries via DBConnector."""
        # Use a short-lived DBConnector for this table to avoid reusing stale connections
        from .db import DBConnector
        config_table = os.getenv('CONFIG_TABLE')
        resident_time_columns = None
        primary_keys = None

        extended = {}
        columns = []
        row_count = None
        pk_distinct_count = None
        date_ranges = {}

        with DBConnector() as db:
            # optionally load resident time-columns from config table in DB
            if config_table:
                # 先尝试同时取 time_columns 和 primary_keys；失败再退回只取 time_columns
                try:
                    rows = db.execute(
                        f"SELECT time_columns, primary_keys FROM {config_table} WHERE table_name='{table_name}'"
                    )
                    if rows and rows[0]:
                        if len(rows[0]) > 0 and rows[0][0]:
                            resident_time_columns = [c.strip() for c in str(rows[0][0]).split(',') if c.strip()]
                        if len(rows[0]) > 1 and rows[0][1]:
                            primary_keys = [c.strip() for c in str(rows[0][1]).split(',') if c.strip()]
                except Exception:
                    try:
                        rows = db.execute(
                            f"SELECT time_columns FROM {config_table} WHERE table_name='{table_name}'"
                        )
                        if rows and rows[0] and rows[0][0]:
                            resident_time_columns = [c.strip() for c in str(rows[0][0]).split(',') if c.strip()]
                    except Exception as e2:
                        print(f"Could not read CONFIG_TABLE {config_table}: {e2}")

            # fallback: load primary keys from local mapping file
            if not primary_keys:
                pk_map = self._load_primary_keys_map()
                primary_keys = pk_map.get(str(table_name).strip().lower())

            # 1. extended info
            try:
                rows = db.execute(f"DESC EXTENDED {table_name}")
                detailed = False
                for r in rows:
                    c0 = str(r[0]) if r and r[0] else ''
                    c1 = str(r[1]) if r and len(r) > 1 and r[1] else ''
                    if c0.strip() == "# Detailed Table Information":
                        detailed = True
                        continue
                    if detailed and c0:
                        extended[c0.strip()] = c1.strip()
            except Exception as e:
                print(f"DESC EXTENDED failed for {table_name}: {e}")

            # 2. columns
            try:
                rows = db.execute(f"DESC {table_name}")
                for r in rows:
                    if not r or not r[0]:
                        break
                    col = str(r[0]).strip()
                    dtype = str(r[1]).strip() if len(r) > 1 and r[1] else ''
                    if col.startswith('#'):
                        break
                    columns.append((col, dtype))
            except Exception as e:
                print(f"DESC failed for {table_name}: {e}")

            # 3. row count
            try:
                rc = db.execute(f"SELECT COUNT(*) FROM {table_name}")
                if rc and len(rc) > 0:
                    row_count = int(rc[0][0])
            except Exception as e:
                print(f"COUNT failed for {table_name}: {e}")

            # 3.1 distinct primary key count (optional)
            if primary_keys:
                try:
                    # 只用真实存在的列
                    col_names = {c[0] for c in columns}
                    pk_cols = [c for c in primary_keys if c in col_names]
                    if pk_cols:
                        # 单列 PK：直接 distinct
                        if len(pk_cols) == 1:
                            expr = f"`{pk_cols[0]}`"
                        else:
                            # 多列 PK：拼成一个字符串键再 distinct
                            parts = [f"COALESCE(CAST(`{c}` AS STRING), '')" for c in pk_cols]
                            expr = f"concat_ws('||', {', '.join(parts)})"
                        rr = db.execute(f"SELECT COUNT(DISTINCT {expr}) FROM {table_name}")
                        if rr and len(rr) > 0:
                            pk_distinct_count = int(rr[0][0])
                except Exception as e:
                    print(f"PK DISTINCT COUNT failed for {table_name}: {e}")

            # 4. date ranges
            all_date_cols = []
            keywords = ['date', 'time', 'dt', 'timestamp', 'created', 'updated', 'modified']
            types = ['date', 'timestamp', 'datetime']
            for col, dtype in columns:
                if any(t in dtype.lower() for t in types) or any(k in col.lower() for k in keywords):
                    all_date_cols.append(col)

            # If specific_date_columns provided, only compute those; else compute all detected
            if specific_date_columns:
                compute_cols = [c for c in specific_date_columns if c in [x[0] for x in columns]]
            else:
                compute_cols = all_date_cols

            if compute_cols:
                try:
                    select_parts = []
                    for c in compute_cols:
                        select_parts.append(f"MIN({c}) as min_{c}")
                        select_parts.append(f"MAX({c}) as max_{c}")
                    sql = f"SELECT {', '.join(select_parts)} FROM {table_name}"
                    rr = db.execute(sql)
                    if rr and len(rr) > 0:
                        row = rr[0]
                        for i, c in enumerate(compute_cols):
                            min_idx = i * 2
                            max_idx = i * 2 + 1
                            minv = row[min_idx] if row[min_idx] else None
                            maxv = row[max_idx] if row[max_idx] else None
                            date_ranges[c] = {'min_date': str(minv) if minv else 'N/A', 'max_date': str(maxv) if maxv else 'N/A'}
                except Exception as e:
                    print(f"Date range query failed for {table_name}: {e}")

        # physical size extraction
        physical_bytes = None
        try:
            stats = extended.get('Statistics', '') or extended.get('totalSize', '') or extended.get('Total Size', '')
            if stats and 'bytes' in stats:
                num = re.sub(r"[^0-9]", "", stats.split('bytes')[0])
                physical_bytes = int(num) if num else None
            else:
                if str(stats).isdigit():
                    physical_bytes = int(stats)
        except Exception:
            physical_bytes = None

        now = datetime.now(ZoneInfo("Asia/Shanghai")).strftime('%Y-%m-%d %H:%M:%S')

        return {
            'table_name': table_name,
            'analysis_time': now,
            'last_modified_time': extended.get('Last Access', 'N/A'),
            'create_time': extended.get('Created Time', 'N/A'),
            'location': extended.get('Location', 'N/A'),
            'table_type': extended.get('Table Type', 'N/A'),
            'physical_size_bytes': physical_bytes if physical_bytes is not None else 'N/A',
            'physical_size_mb': round(physical_bytes / (1024 * 1024), 2) if physical_bytes else 'N/A',
            'physical_size_gb': round(physical_bytes / (1024 * 1024 * 1024), 4) if physical_bytes else 'N/A',
            'columns': columns,
            'column_count': len(columns),
            'row_count': row_count,
            'primary_keys': primary_keys if primary_keys else [],
            'pk_distinct_count': pk_distinct_count,
            'date_columns': all_date_cols,
            'default_time_columns': resident_time_columns if resident_time_columns else [],
            'date_column_count': len(all_date_cols),
            'date_ranges': date_ranges
        }
