from fastapi.testclient import TestClient
import os
import shutil
import pytest
import zipfile
import io
from main import app, get_db
from database import Base, engine, SessionLocal, config
import models

# Set up test database
@pytest.fixture(scope="session", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield

@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c

def test_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "My Non-Profit" in response.text
    assert "Sample Movie 1" in response.text

def test_play_movie(client):
    # Set a logo in DB for test
    db = SessionLocal()
    settings = db.query(models.OrgSettings).first()
    settings.org_logo = "logo_test.png"
    db.commit()
    
    movie = db.query(models.Movie).first()
    db.close()
    
    response = client.get(f"/play/{movie.id}")
    assert response.status_code == 200
    assert movie.title in response.text
    assert "logo-overlay" in response.text
    assert "timeLeft" in response.text
    assert "video.ontimeupdate" in response.text

def test_search(client):
    response = client.get("/?search=Sample Movie 1")
    assert response.status_code == 200
    assert "Sample Movie 1" in response.text
    assert "Sample Movie 2" not in response.text

def test_update_settings(client):
    # Get current settings
    response = client.get("/settings")
    assert response.status_code == 200
    
    # Update settings
    new_data = {
        "org_name": "Updated Org Name",
        "org_description": "Updated Description",
        "org_logo": "new_logo.png",
        "org_website": "https://updated.org",
        "org_email": "updated@example.org",
        "org_phone": "123-456-7890",
        "org_contact_info": "Updated Contact Info"
    }
    response = client.post("/settings", data=new_data, follow_redirects=True)
    assert response.status_code == 200
    assert "Updated Org Name" in response.text
    assert "Updated Description" in response.text

def test_logo_upload(client):
    data = {
        "org_name": "Logo Test Org"
    }
    files = {
        "org_logo_file": ("test_logo.png", b"fake logo data", "image/png")
    }
    response = client.post("/settings", data=data, files=files, follow_redirects=True)
    assert response.status_code == 200
    
    # Verify logo exists in the specified folder
    assert os.path.exists(os.path.join(config.movie_folder, "logo_test_logo.png"))
    
    # Verify DB
    db = SessionLocal()
    settings = db.query(models.OrgSettings).first()
    assert settings.org_logo == "logo_test_logo.png"
    db.close()
    
    # Cleanup: logo is now in config.movie_folder/logo_test_logo.png
    # But wait, the test originally used ./test_movies_folder
    # Now it uses whatever config.movie_folder is (default ./static/movies)
    # I should probably use monkeypatch to set config.movie_folder if I want to isolate tests.

def test_add_movie(client):
    data = {
        "title": "New Test Movie",
        "description": "Test movie description",
        "creation_date": "2024-01-01",
        "length_minutes": 10,
        "loop": 1
    }
    files = {
        "movie_file": ("test.mp4", b"fake movie data", "video/mp4"),
        "poster_file": ("test_poster.png", b"fake poster data", "image/png")
    }
    # Ensure movie folder is known
    movie_folder = config.movie_folder
    
    response = client.post("/movies/add", data=data, files=files, follow_redirects=True)
    assert response.status_code == 200
    assert "New Test Movie" in response.text

    # Verify in DB
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.title == "New Test Movie").first()
    assert movie is not None
    assert movie.relative_file_path == "movie_test.mp4"
    assert movie.poster_image == "poster_test_poster.png"
    db.close()
    
    # Verify file exists
    assert os.path.exists(os.path.join(movie_folder, "movie_test.mp4"))
    assert os.path.exists(os.path.join(movie_folder, "poster_test_poster.png"))

def test_edit_movie(client):
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.title == "New Test Movie").first()
    movie_id = movie.id
    db.close()
    
    data = {
        "title": "Updated Movie Title",
        "description": "Updated description",
        "creation_date": "2024-02-02",
        "length_minutes": 15,
        "loop": 0
    }
    response = client.post(f"/movies/edit/{movie_id}", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert "Updated Movie Title" in response.text
    assert "Sample Movie 1" in response.text # Still there
    
    # Verify in DB
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    assert movie.title == "Updated Movie Title"
    assert movie.length_minutes == 15
    assert movie.loop == 0
    db.close()

def test_delete_movie(client):
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.title == "Updated Movie Title").first()
    movie_id = movie.id
    movie_path = movie.relative_file_path
    poster_path = movie.poster_image
    db.close()
    
    # Get movie folder
    movie_folder = config.movie_folder

    full_movie_path = os.path.join(movie_folder, movie_path)
    full_poster_path = os.path.join(movie_folder, poster_path)
    
    # Ensure files exist before deletion
    assert os.path.exists(full_movie_path)
    assert os.path.exists(full_poster_path)
    
    response = client.post(f"/movies/delete/{movie_id}", follow_redirects=True)
    assert response.status_code == 200
    assert "Updated Movie Title" not in response.text
    
    # Verify DB
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    assert movie is None
    db.close()
    
    # Verify files are deleted
    assert not os.path.exists(full_movie_path)
    assert not os.path.exists(full_poster_path)

def test_edit_movie_file_cleanup(client):
    # Add a movie first
    data = {
        "title": "Cleanup Test Movie",
        "description": "Test movie description",
        "creation_date": "2024-01-01",
        "length_minutes": 10,
        "loop": 1
    }
    files = {
        "movie_file": ("original.mp4", b"original movie data", "video/mp4"),
        "poster_file": ("original_poster.png", b"original poster data", "image/png")
    }
    client.post("/movies/add", data=data, files=files, follow_redirects=True)
    
    db = SessionLocal()
    movie = db.query(models.Movie).filter(models.Movie.title == "Cleanup Test Movie").first()
    movie_id = movie.id
    db.close()
    
    movie_folder = config.movie_folder
    
    original_movie_path = os.path.join(movie_folder, "movie_original.mp4")
    original_poster_path = os.path.join(movie_folder, "poster_original_poster.png")
    
    assert os.path.exists(original_movie_path)
    assert os.path.exists(original_poster_path)
    
    # Update movie with new files
    data["title"] = "Cleanup Test Movie Updated"
    files = {
        "movie_file": ("new.mp4", b"new movie data", "video/mp4"),
        "poster_file": ("new_poster.png", b"new poster data", "image/png")
    }
    client.post(f"/movies/edit/{movie_id}", data=data, files=files, follow_redirects=True)
    
    # Check if old files are deleted
    assert not os.path.exists(original_movie_path)
    assert not os.path.exists(original_poster_path)
    
    # Check if new files exist
    assert os.path.exists(os.path.join(movie_folder, "movie_new.mp4"))
    assert os.path.exists(os.path.join(movie_folder, "poster_new_poster.png"))

def test_update_settings_readonly_folder(client, monkeypatch):
    # Mock config.movie_folder and os.makedirs to raise OSError (Read-only file system)
    monkeypatch.setattr(config, "movie_folder", "/read-only-folder")
    
    import os
    def mock_makedirs(path, exist_ok=False):
        if path == "/read-only-folder":
            raise OSError(30, "Read-only file system", "/read-only-folder")
        return os.makedirs(path, exist_ok=exist_ok)
    
    monkeypatch.setattr(os, "makedirs", mock_makedirs)
    
    data = {
        "org_name": "Test Org"
    }
    response = client.post("/settings", data=data, follow_redirects=True)
    assert response.status_code == 200
    assert "Cannot use folder" in response.text
    assert "/read-only-folder" in response.text

def test_backup(client):
    response = client.get("/settings/backup")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "nonp_backup.zip" in response.headers["content-disposition"]
    
    # Verify ZIP content
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        file_list = zf.namelist()
        assert "database.sqlite" in file_list
        # There should be some movies since we have dummy ones
        assert any(f.startswith("movies/") for f in file_list)

def test_restore(client):
    # 1. Create a dummy backup ZIP
    movie_folder = config.movie_folder
    # We need to know the actual db path from config
    db_path = config.database_path
    
    # Create a new dummy DB file for restoration
    restore_db_path = "restore_test.db"
    if os.path.exists(restore_db_path):
        os.remove(restore_db_path)
    
    # Copy current DB but modify it
    shutil.copy2(db_path, restore_db_path)
    # Modify the org name in the restore DB
    import sqlite3
    conn = sqlite3.connect(restore_db_path)
    cursor = conn.cursor()
    cursor.execute("UPDATE settings SET org_name = 'Restored Org Name'")
    conn.commit()
    conn.close()
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(restore_db_path, "database.sqlite")
        zf.writestr("movies/restored_movie.mp4", b"restored movie content")
    
    zip_buffer.seek(0)
    
    # 2. Perform restore
    files = {
        "backup_file": ("backup.zip", zip_buffer, "application/zip")
    }
    response = client.post("/settings/restore", files=files, follow_redirects=True)
    assert response.status_code == 200
    assert "Restored Org Name" in response.text
    assert "Backup restored successfully!" in response.text
    
    # 3. Verify files
    assert os.path.exists(os.path.join(movie_folder, "restored_movie.mp4"))
    
    # Cleanup
    if os.path.exists(restore_db_path):
        os.remove(restore_db_path)

def test_restore_with_different_folder(client, monkeypatch):
    # Test that restoration uses the CURRENTLY CONFIGURED movie_folder, 
    # even if the backup's DB had a different one (since we now use .env)
    backup_db_path = "backup_diff.db"
    new_movie_folder = "./restored_movies_env" # This will be our "current" config
    
    monkeypatch.setattr(config, "movie_folder", new_movie_folder)
    
    # 1. Prepare backup DB with a different movie_folder (legacy)
    import sqlite3
    Base.metadata.create_all(bind=engine)
    shutil.copy2(config.database_path, backup_db_path)
    
    conn = sqlite3.connect(backup_db_path)
    cursor = conn.cursor()
    # Manually recreate the legacy table with the movie_folder column and all other expected columns
    cursor.execute("DROP TABLE IF EXISTS settings")
    cursor.execute("CREATE TABLE settings (id INTEGER PRIMARY KEY, org_name TEXT, org_logo TEXT, org_contact_info TEXT, org_website TEXT, org_email TEXT, org_phone TEXT, org_description TEXT, movie_folder TEXT)")
    cursor.execute("INSERT INTO settings (org_name, movie_folder) VALUES (?, ?)", 
                   ("Diff Folder Org", "./legacy_folder"))
    conn.commit()
    conn.close()
    
    # 2. Create ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.write(backup_db_path, "database.sqlite")
        zf.writestr("movies/restored_diff.mp4", b"content")
    zip_buffer.seek(0)
    
    # 3. Restore
    files = {"backup_file": ("backup.zip", zip_buffer, "application/zip")}
    response = client.post("/settings/restore", files=files, follow_redirects=True)
    assert response.status_code == 200
    assert "Diff Folder Org" in response.text
    
    # 4. Verify file was restored to the folder from CURRENT config (new_movie_folder),
    # NOT the legacy folder from backup DB.
    assert os.path.exists(os.path.join(new_movie_folder, "restored_diff.mp4"))
    assert not os.path.exists(os.path.join("./legacy_folder", "restored_diff.mp4"))
    
    # Cleanup
    if os.path.exists(backup_db_path):
        os.remove(backup_db_path)
    if os.path.exists(new_movie_folder):
        shutil.rmtree(new_movie_folder)
