# Non-Profit Movie Loops

A FastAPI-based web application designed for non-profit organizations to manage and display looping movie clips. This is ideal for informational kiosks, waiting rooms, event displays, or any situation where a continuous video loop is needed.

## 🚀 Features

- **Movie Management**: Easy interface to add, edit, and delete movies.
- **Looping Playback**: Toggle looping on or off for each movie.
- **Organization Customization**: Personalize the app with your organization's name, description, logo, and contact information.
- **Search & Sort**: Quickly find movies by title, date added, creation date, or length.
- **Poster Images**: Upload custom posters for each movie to create an attractive gallery.
- **Backup & Restore**: Simple one-click backup of the entire database and all movie files into a single ZIP file, with an easy restore process.
- **Responsive Design**: Clean and functional web interface that works across devices.

## 🛠 Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/)
- **Database**: [SQLite](https://www.sqlite.org/) with [SQLAlchemy](https://www.sqlalchemy.org/)
- **Templating**: [Jinja2](https://palletsprojects.com/p/jinja/)
- **Configuration**: [Pydantic Settings](https://docs.pydantic.dev/latest/usage/pydantic_settings/)
- **Asynchronous I/O**: [aiofiles](https://github.com/Tinche/aiofiles)
- **Testing**: [pytest](https://docs.pytest.org/)

## 📋 Prerequisites

- Python 3.8+
- pip (Python package installer)

## ⚙️ Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd nonp-movie-loops
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables**:
   Create a `.env` file in the root directory based on the `sample.env` file.
   ```bash
   cp sample.env .env
   ```
   Edit `.env` to set your desired database path and movie storage folder.
   ```env
   DATABASE_PATH=./nonp-movie-loops.db
   MOVIE_FOLDER=./static/movies
   ```

## 🚀 Running the Application

Start the server using Uvicorn:

```bash
python main.py
```
Or directly with Uvicorn:
```bash
uvicorn main:app --reload
```

The application will be available at `http://127.0.0.1:8000`.

## 🧪 Running Tests

To run the automated tests, use `pytest`:

```bash
pytest
```

## 📂 Project Structure

- `main.py`: Core FastAPI application and routes.
- `models.py`: SQLAlchemy database models.
- `database.py`: Database connection and configuration logic.
- `templates/`: Jinja2 HTML templates.
- `static/`: Static assets (CSS, images, and movies by default).
- `requirements.txt`: Python dependencies.
- `test_app.py`: Automated tests.

## 💾 Backup & Restore

- **Backup**: Go to the **Settings** page and click **Download Backup**. This will generate a ZIP file containing the SQLite database and all files in your configured movie folder.
- **Restore**: On the **Settings** page, upload a previously created backup ZIP file. **Warning**: Restoring will overwrite your current database and delete existing files in the movie folder.

## 📄 License

This project is open-source. Please refer to the organization's guidelines for usage and contribution.
