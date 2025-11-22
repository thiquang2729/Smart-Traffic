from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text, UniqueConstraint, ForeignKey, inspect, text
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship


Base = declarative_base()


class Camera(Base):
    __tablename__ = 'cameras'
    camera_id = Column(String, primary_key=True)
    name = Column(String)
    location = Column(String)
    timezone = Column(String)
    videos = relationship('Video', back_populates='camera')


class Video(Base):
    __tablename__ = 'videos'
    video_id = Column(Integer, primary_key=True, autoincrement=True)
    camera_id = Column(String, ForeignKey('cameras.camera_id'))
    path = Column(Text, unique=True, nullable=False)
    start_ts = Column(DateTime)
    end_ts = Column(DateTime)
    fps = Column(Float)
    resolution = Column(String)
    camera = relationship('Camera', back_populates='videos')
    appearances = relationship('Appearance', back_populates='video')


class Appearance(Base):
    __tablename__ = 'appearances'
    appearance_id = Column(Integer, primary_key=True, autoincrement=True)
    plate = Column(String, nullable=False)
    camera_id = Column(String)
    video_id = Column(Integer, ForeignKey('videos.video_id'))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    score_lp = Column(Float)
    score_ocr = Column(Float)
    match_mode = Column(String)
    # Trajectory analysis fields
    speed_px_per_sec = Column(Float)  # Tốc độ (pixel/giây)
    speed_kmh = Column(Float)  # Tốc độ (km/h) nếu có calibration
    direction_deg = Column(Float)  # Hướng di chuyển (độ)
    direction_name = Column(String)  # Tên hướng (Đông, Tây, Bắc, Nam, etc.)
    total_distance_px = Column(Float)  # Tổng quãng đường (pixel)
    video = relationship('Video', back_populates='appearances')


class Job(Base):
    __tablename__ = 'jobs'
    job_id = Column(String, primary_key=True)
    plate = Column(String, nullable=False)
    status = Column(String)
    created_at = Column(DateTime)
    finished_at = Column(DateTime)
    result_video = Column(Text)
    segments_json = Column(Text)


def get_engine(db_path: str) -> any:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return create_engine(f'sqlite:///{db_path}', future=True)


def migrate_appearances_table(engine):
    """Migrate appearances table to add trajectory columns if they don't exist"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('appearances')]
    
    new_columns = {
        'speed_px_per_sec': 'REAL',
        'speed_kmh': 'REAL',
        'direction_deg': 'REAL',
        'direction_name': 'TEXT',
        'total_distance_px': 'REAL'
    }
    
    with engine.connect() as conn:
        for col_name, col_type in new_columns.items():
            if col_name not in columns:
                print(f"📊 Adding column '{col_name}' to appearances table...")
                conn.execute(text(f"ALTER TABLE appearances ADD COLUMN {col_name} {col_type}"))
                conn.commit()
                print(f"✅ Column '{col_name}' added successfully")


def init_db(db_path: str) -> sessionmaker:
    engine = get_engine(db_path)
    
    # Create all tables first
    Base.metadata.create_all(engine)
    
    # Migrate existing tables if needed
    inspector = inspect(engine)
    if 'appearances' in inspector.get_table_names():
        migrate_appearances_table(engine)
    
    return sessionmaker(bind=engine, expire_on_commit=False)


