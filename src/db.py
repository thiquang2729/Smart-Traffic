from __future__ import annotations

import os
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    create_engine, Column, Integer, String, Float, DateTime, Text, UniqueConstraint, ForeignKey
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


def init_db(db_path: str) -> sessionmaker:
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


