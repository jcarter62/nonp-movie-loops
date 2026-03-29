from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from pydantic_settings import BaseSettings, SettingsConfigDict
import os

class Settings(BaseSettings):
    database_path: str = "./nonp-movie-loops.db"
    movie_folder: str = "./static/movies"

    model_config = SettingsConfigDict(env_file=".env")

config = Settings()

SQLALCHEMY_DATABASE_URL = f"sqlite:///{config.database_path}"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
