import os
from dotenv import load_dotenv

load_dotenv()


class DBConnector:
    """Simple JDBC connector wrapper using jaydebeapi."""

    def __init__(self):
        self.user = os.getenv('HIVE_USERNAME')
        self.password = os.getenv('HIVE_PASSWORD')
        self.jdbc_url = os.getenv('JDBC_URL') or os.getenv('KYUUBI_JDBC_URL')
        self.driver_class = os.getenv('JDBC_DRIVER_CLASS', 'org.apache.kyuubi.jdbc.KyuubiHiveDriver')
        kyuubi_home = os.getenv('KYUUBI_HOME')
        kyuubi_jars_dir = os.path.join(kyuubi_home, 'jars') if kyuubi_home else None
        jdbc_driver_path = [
            os.path.join(kyuubi_jars_dir, jar)
            for jar in os.listdir(kyuubi_jars_dir)
            if jar.endswith('.jar')
        ] if kyuubi_jars_dir and os.path.isdir(kyuubi_jars_dir) else []

        configured = os.getenv('JDBC_DRIVER_JAR_PATH') or os.getenv('KYUUBI_DRIVER_JARS')
        if configured:
            # Respect explicit paths, including the original Windows semicolon format.
            separator = ';' if ';' in configured else os.pathsep
            self.jar_list = [p.strip() for p in configured.split(separator) if p.strip()]
        else:
            self.jar_list = jdbc_driver_path

        self.conn = None
        self.cursor = None

    def connect(self):
        # If an existing connection seems usable, keep it. Otherwise reconnect.
        if self.conn and self.cursor:
            try:
                # quick sanity check: try to call cursor.getDescription (may raise if closed)
                _ = getattr(self.cursor, 'description', None)
                return
            except Exception:
                try:
                    self.close()
                except Exception:
                    pass

        if not self.jar_list:
            raise RuntimeError('No JDBC driver jars configured (JDBC_DRIVER_JAR_PATH)')

        if not self.jdbc_url:
            raise RuntimeError('JDBC_URL is required in live mode')

        import jaydebeapi

        self.conn = jaydebeapi.connect(self.driver_class, self.jdbc_url, {'user': self.user, 'password': self.password}, self.jar_list)
        self.cursor = self.conn.cursor()

    def close(self):
        # Close cursor and connection safely and clear references to avoid reuse of closed objects
        if self.cursor:
            try:
                self.cursor.close()
            except Exception:
                pass
            finally:
                self.cursor = None
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
            finally:
                self.conn = None

    def __enter__(self):
        # Support with-statement usage
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        # Ensure resources are closed on exit
        try:
            self.close()
        except Exception:
            pass
        # Do not suppress exceptions
        return False

    def execute(self, sql):
        # Ensure connection is available before executing
        if not self.conn or not self.cursor:
            self.connect()

        try:
            self.cursor.execute(sql)
            try:
                return self.cursor.fetchall()
            except Exception:
                # If no result set (e.g., DDL), return empty list
                return []
        except Exception:
            # On execution error, close connection to avoid stale state and re-raise
            try:
                self.close()
            except Exception:
                pass
            raise
