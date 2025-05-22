import json
from pathlib import Path
from sqlmodel import create_engine, SQLModel, Session

# Construct path to config file relative to this (db.py) file's location
CONFIG_FILE_PATH = Path("/app/configs/mock_api_config.json")

def load_db_config():
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found at {CONFIG_FILE_PATH}")
        return {"database_url": "sqlite:///./data/mock_orders.db"} # Default path within /app

config = load_db_config()
DATABASE_URL = config.get("database", {}).get("url", "sqlite:////app/data/mock_orders.db")

# The connect_args is recommended for SQLite to handle multiple threads (e.g., FastAPI requests)
engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

def create_db_and_tables():
    """
    Creates the database file and all tables defined by SQLModel metadata.
    This should be called once on application startup.
    """
    # Ensure the directory for the SQLite DB exists
    if DATABASE_URL.startswith("sqlite:///"):
        db_file_path_str = DATABASE_URL.replace("sqlite:///", "")
        # If it's a relative path like sqlite:///./data/mock_orders.db
        if db_file_path_str.startswith("./"): 
            db_file_path_str = db_file_path_str[2:]
        
        # Resolve path relative to project root if it starts with /app (container path)
        # For docker, /app/data/mock_orders.db is the structure.
        # For local testing, rely on relative paths.
        # The DATABASE_URL from config is already /app/data/...
        db_file_path = Path(db_file_path_str)

        db_dir = db_file_path.parent
        db_dir.mkdir(parents=True, exist_ok=True)
        print(f"Ensuring database directory exists: {db_dir}")
        print(f"Database file will be at: {db_file_path}")

    SQLModel.metadata.create_all(engine)
    print("Database and tables created (if they didn't exist).")


def get_session():
    """
    Dependency for FastAPI to get a database session.
    Ensures the session is closed after the request.
    """
    with Session(engine) as session:
        yield session