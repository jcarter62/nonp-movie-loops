import os
import shutil
import zipfile
import tempfile
from datetime import date
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request, Form, File, UploadFile, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from sqlalchemy.orm import Session
from database import engine, Base, get_db, config
import models
from urllib.parse import quote
import aiofiles

# Create tables
Base.metadata.create_all(bind=engine)

# Lifespan for startup data injection
@asynccontextmanager
async def lifespan(app: FastAPI):
    # This runs on startup
    db = next(get_db())
    try:
        settings = get_settings(db)
        
        # Check if we have movies, if not, add some dummy ones for demonstration
        if db.query(models.Movie).count() == 0:
            dummy_movies = [
                models.Movie(
                    title="Sample Movie 1",
                    description="A beautiful sample movie that loops.",
                    creation_date=date(2023, 1, 1),
                    relative_file_path="sample1.mp4",
                    length_minutes=5,
                    loop=1
                ),
                models.Movie(
                    title="Sample Movie 2",
                    description="A non-looping movie clip.",
                    creation_date=date(2023, 5, 15),
                    relative_file_path="sample2.mp4",
                    length_minutes=2,
                    loop=0
                )
            ]
            db.add_all(dummy_movies)
            db.commit()
    finally:
        db.close()
    
    yield
    # This runs on shutdown (if needed)

app = FastAPI(lifespan=lifespan)

# Templates and Static files
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Helper to get settings
def get_settings(db: Session):
    settings = db.query(models.OrgSettings).first()
    if not settings:
        # Create default settings if not exists
        settings = models.OrgSettings(
            org_name="My Non-Profit",
            org_description="Helping the world one movie at a time."
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return settings

def ensure_folder_writable(folder_path: str):
    """Ensure folder exists and is writable. Returns (success, error_message)"""
    try:
        os.makedirs(folder_path, exist_ok=True)
        # Verify it's writable
        test_file = os.path.join(folder_path, ".write_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return True, None
    except OSError as e:
        return False, str(e)

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request, 
    search: str = None, 
    sort: str = "title", 
    db: Session = Depends(get_db)
):
    settings = get_settings(db)
    query = db.query(models.Movie)
    
    if search:
        query = query.filter(models.Movie.title.contains(search))
    
    if sort == "date_added":
        query = query.order_by(models.Movie.date_added.desc())
    elif sort == "creation_date":
        query = query.order_by(models.Movie.creation_date.desc())
    elif sort == "length_minutes":
        query = query.order_by(models.Movie.length_minutes)
    else:
        query = query.order_by(models.Movie.title)
    
    movies = query.all()
    
    return templates.TemplateResponse(
        request=request, 
        name="index.html", 
        context={
            "settings": settings,
            "movie_folder": config.movie_folder,
            "movies": movies,
            "search": search,
            "sort": sort
        }
    )

@app.get("/play/{movie_id}", response_class=HTMLResponse)
async def play_movie(request: Request, movie_id: int, db: Session = Depends(get_db)):
    settings = get_settings(db)
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        return RedirectResponse(url="/")
    
    return templates.TemplateResponse(
        request=request, 
        name="player.html", 
        context={
            "settings": settings,
            "movie_folder": config.movie_folder,
            "movie": movie
        }
    )

@app.get("/settings", response_class=HTMLResponse)
async def settings_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    return templates.TemplateResponse(
        request=request, 
        name="settings.html", 
        context={
            "settings": settings,
            "movie_folder": config.movie_folder
        }
    )

@app.post("/settings")
async def update_settings(
    request: Request,
    org_name: str = Form(...),
    org_description: str = Form(""),
    org_logo: str = Form(None),
    org_contact_info: str = Form(""),
    org_website: str = Form(""),
    org_email: str = Form(""),
    org_phone: str = Form(""),
    org_logo_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    settings = get_settings(db)
    
    # Ensure movie folder exists and is writable
    success, error_msg = ensure_folder_writable(config.movie_folder)
    if not success:
        return RedirectResponse(url=f"/settings?error={quote(f'Cannot use folder: {error_msg}')}", status_code=303)
    
    if org_logo_file and org_logo_file.filename:
        # Save logo to movie folder
        logo_filename = f"logo_{org_logo_file.filename}"
        logo_path = os.path.join(config.movie_folder, logo_filename)
        
        try:
            # Delete old logo if it exists and is different
            if settings.org_logo and settings.org_logo != logo_filename:
                old_logo_path = os.path.join(config.movie_folder, settings.org_logo)
                if os.path.exists(old_logo_path):
                    os.remove(old_logo_path)
            
            content = await org_logo_file.read()
            async with aiofiles.open(logo_path, "wb") as f:
                await f.write(content)
            settings.org_logo = logo_filename
        except OSError as e:
            return RedirectResponse(url=f"/settings?error={quote(f'Error saving logo: {e}')}", status_code=303)
    elif org_logo:
        settings.org_logo = org_logo

    settings.org_name = org_name
    settings.org_description = org_description
    settings.org_contact_info = org_contact_info
    settings.org_website = org_website
    settings.org_email = org_email
    settings.org_phone = org_phone
    
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/settings/backup")
async def backup_settings(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    settings = get_settings(db)
    movie_folder = config.movie_folder
    db_path = config.database_path
    
    # Create a temporary file for the zip
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    def create_zip():
        with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add database
            if os.path.exists(db_path):
                zf.write(db_path, "database.sqlite")
            
            # Add movie folder
            if os.path.exists(movie_folder):
                for root, dirs, files in os.walk(movie_folder):
                    for file in files:
                        file_path = os.path.join(root, file)
                        # We want to store it under a 'movies' directory in the zip
                        arcname = os.path.join("movies", os.path.relpath(file_path, movie_folder))
                        zf.write(file_path, arcname)

    create_zip()
    
    background_tasks.add_task(os.remove, temp_zip_path)
    
    return FileResponse(
        temp_zip_path,
        media_type="application/zip",
        filename="nonp_backup.zip"
    )

@app.post("/settings/restore")
async def restore_settings(
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    # 1. Save uploaded zip to temp
    fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
    os.close(fd)
    
    try:
        async with aiofiles.open(temp_zip_path, "wb") as f:
            content = await backup_file.read()
            await f.write(content)
        
        # 2. Extract to temp dir
        temp_dir = tempfile.mkdtemp()
        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as zf:
                zf.extractall(temp_dir)
            
            # 3. Verify and Restore
            extracted_db = os.path.join(temp_dir, "database.sqlite")
            extracted_movies = os.path.join(temp_dir, "movies")
            
            if not os.path.exists(extracted_db):
                 return HTMLResponse("Invalid backup file: database.sqlite missing", status_code=400)
            
            # Use the currently configured movie folder for restoration
            target_movie_folder = config.movie_folder
            
            # Restore movies
            if os.path.exists(extracted_movies):
                success, error_msg = ensure_folder_writable(target_movie_folder)
                if not success:
                    return HTMLResponse(f"Error restoring movies: Cannot use folder {target_movie_folder}. {error_msg}", status_code=400)
                
                # Cleanup target folder
                try:
                    for item in os.listdir(target_movie_folder):
                        item_path = os.path.join(target_movie_folder, item)
                        if os.path.isfile(item_path) or os.path.islink(item_path):
                            os.unlink(item_path)
                        elif os.path.isdir(item_path):
                            shutil.rmtree(item_path)
                    
                    # Copy files
                    for item in os.listdir(extracted_movies):
                        s = os.path.join(extracted_movies, item)
                        d = os.path.join(target_movie_folder, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d, dirs_exist_ok=True)
                        else:
                            shutil.copy2(s, d)
                except OSError as e:
                    return HTMLResponse(f"File operation failed during restore: {e}", status_code=400)

            # Restore database
            try:
                engine.dispose()
                shutil.copy2(extracted_db, config.database_path)
            except OSError as e:
                 return HTMLResponse(f"Database restoration failed: {e}", status_code=400)
            
            return RedirectResponse(url="/settings?restored=true", status_code=303)
            
        finally:
            shutil.rmtree(temp_dir)
    finally:
        if os.path.exists(temp_zip_path):
            os.remove(temp_zip_path)

@app.get("/movies/add", response_class=HTMLResponse)
async def add_movie_form(request: Request, db: Session = Depends(get_db)):
    settings = get_settings(db)
    return templates.TemplateResponse(
        request=request, 
        name="movie_form.html", 
        context={"settings": settings, "movie_folder": config.movie_folder, "movie": None}
    )

@app.post("/movies/add")
async def add_movie(
    request: Request,
    title: str = Form(...),
    description: str = Form(""),
    creation_date: str = Form(None),
    length_minutes: int = Form(0),
    loop: int = Form(0),
    movie_file: UploadFile = File(None),
    poster_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    settings = get_settings(db)
    movie = models.Movie(
        title=title,
        description=description,
        length_minutes=length_minutes,
        loop=loop
    )
    
    if creation_date:
        movie.creation_date = date.fromisoformat(creation_date)
    
    success, error_msg = ensure_folder_writable(config.movie_folder)
    if not success:
        return RedirectResponse(url=f"/movies/add?error={quote(f'Cannot use movie folder: {error_msg}')}", status_code=303)

    try:
        if movie_file and movie_file.filename:
            file_path = f"movie_{movie_file.filename}"
            full_path = os.path.join(config.movie_folder, file_path)
            
            # Cleanup old movie if replacing (though it's a new movie record, 
            # let's be safe if a file with the same name exists)
            if os.path.exists(full_path):
                os.remove(full_path)
                
            content = await movie_file.read()
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(content)
            movie.relative_file_path = file_path

        if poster_file and poster_file.filename:
            poster_filename = f"poster_{poster_file.filename}"
            full_poster_path = os.path.join(config.movie_folder, poster_filename)
            
            # Cleanup old poster if replacing
            if os.path.exists(full_poster_path):
                os.remove(full_poster_path)
                
            content = await poster_file.read()
            async with aiofiles.open(full_poster_path, "wb") as f:
                await f.write(content)
            movie.poster_image = poster_filename
    except OSError as e:
        return RedirectResponse(url=f"/movies/add?error={quote(f'Error saving files: {e}')}", status_code=303)

    db.add(movie)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/movies/edit/{movie_id}", response_class=HTMLResponse)
async def edit_movie_form(request: Request, movie_id: int, db: Session = Depends(get_db)):
    settings = get_settings(db)
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        return RedirectResponse(url="/")
    return templates.TemplateResponse(
        request=request, 
        name="movie_form.html", 
        context={"settings": settings, "movie_folder": config.movie_folder, "movie": movie}
    )

@app.post("/movies/edit/{movie_id}")
async def update_movie(
    request: Request,
    movie_id: int,
    title: str = Form(...),
    description: str = Form(""),
    creation_date: str = Form(None),
    length_minutes: int = Form(0),
    loop: int = Form(0),
    movie_file: UploadFile = File(None),
    poster_file: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    settings = get_settings(db)
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        return RedirectResponse(url="/")
    
    movie.title = title
    movie.description = description
    movie.length_minutes = length_minutes
    movie.loop = loop
    
    if creation_date:
        movie.creation_date = date.fromisoformat(creation_date)
    else:
        movie.creation_date = None
    
    success, error_msg = ensure_folder_writable(config.movie_folder)
    if not success:
        return RedirectResponse(url=f"/movies/edit/{movie_id}?error={quote(f'Cannot use movie folder: {error_msg}')}", status_code=303)

    try:
        if movie_file and movie_file.filename:
            file_path = f"movie_{movie_file.filename}"
            full_path = os.path.join(config.movie_folder, file_path)
            
            # Delete old file if it exists and is different
            if movie.relative_file_path and movie.relative_file_path != file_path:
                old_movie_path = os.path.join(config.movie_folder, movie.relative_file_path)
                if os.path.exists(old_movie_path):
                    os.remove(old_movie_path)
            
            content = await movie_file.read()
            async with aiofiles.open(full_path, "wb") as f:
                await f.write(content)
            movie.relative_file_path = file_path

        if poster_file and poster_file.filename:
            poster_filename = f"poster_{poster_file.filename}"
            full_poster_path = os.path.join(config.movie_folder, poster_filename)
            
            # Delete old poster if it exists and is different
            if movie.poster_image and movie.poster_image != poster_filename:
                old_poster_path = os.path.join(config.movie_folder, movie.poster_image)
                if os.path.exists(old_poster_path):
                    os.remove(old_poster_path)
            
            content = await poster_file.read()
            async with aiofiles.open(full_poster_path, "wb") as f:
                await f.write(content)
            movie.poster_image = poster_filename
    except OSError as e:
        return RedirectResponse(url=f"/movies/edit/{movie_id}?error={quote(f'Error saving files: {e}')}", status_code=303)

    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.post("/movies/delete/{movie_id}")
async def delete_movie(
    request: Request,
    movie_id: int,
    db: Session = Depends(get_db)
):
    settings = get_settings(db)
    movie = db.query(models.Movie).filter(models.Movie.id == movie_id).first()
    if not movie:
        return RedirectResponse(url="/")
    
    try:
        # Delete movie file
        if movie.relative_file_path:
            movie_file_path = os.path.join(config.movie_folder, movie.relative_file_path)
            if os.path.exists(movie_file_path):
                os.remove(movie_file_path)
        
        # Delete poster image
        if movie.poster_image:
            poster_path = os.path.join(config.movie_folder, movie.poster_image)
            if os.path.exists(poster_path):
                os.remove(poster_path)
    except OSError as e:
        return RedirectResponse(url=f"/?error={quote(f'Error deleting files: {e}')}", status_code=303)
            
    db.delete(movie)
    db.commit()
    return RedirectResponse(url="/", status_code=303)

@app.get("/movies/{path:path}")
async def serve_movie(path: str, db: Session = Depends(get_db)):
    movie_path = os.path.join(config.movie_folder, path)
    if os.path.exists(movie_path):
        return FileResponse(movie_path)
    return HTMLResponse(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
