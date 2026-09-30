from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, BigInteger, Text, Index, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class TableSnapshot(Base):
    __tablename__ = 'table_snapshots'

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(255), index=True, nullable=False)
    analysis_time = Column(DateTime, default=datetime.utcnow, index=True, nullable=False)

    # metadata fields
    last_modified_time = Column(String(255))
    create_time = Column(String(255))
    row_count = Column(BigInteger)
    pk_distinct_count = Column(BigInteger)
    column_count = Column(Integer)
    physical_size_bytes = Column(BigInteger)

    # store json-serialized strings for complex fields
    date_columns_json = Column(Text)
    date_ranges_json = Column(Text)
    primary_keys_json = Column(Text)

    # optional free-form location and table type
    location = Column(Text)
    table_type = Column(String(128))


Index('ix_table_snapshots_table_time', TableSnapshot.table_name, TableSnapshot.analysis_time)


class TimeFavorite(Base):
    __tablename__ = 'time_favorites'

    id = Column(Integer, primary_key=True, autoincrement=True)
    table_name = Column(String(255), index=True, nullable=False)
    column_name = Column(String(255), nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    favorited_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    Index('ix_time_fav_table_column', table_name, column_name, unique=True)
