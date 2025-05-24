import json
from pathlib import Path
from sqlmodel import create_engine, SQLModel, Session
import os # Import os module

# Assuming crud.models is in the same directory or src.mock_api_service.crud.models
from .crud.models import Order, ExperimentTelemetryEvent 

# Determine the base directory of the project (OrderAgent_DS_Task)
# db.py -> mock_api_service -> src -> OrderAgent_DS_Task (project_root)
PROJECT_ROOT_PATH = Path(__file__).parent.parent.parent 
DEFAULT_CONFIG_PATH = PROJECT_ROOT_PATH / "configs" / "mock_api_config.json"

# Allow overriding config path via environment variable
CONFIG_FILE_ENV_VAR = "MOCK_API_CONFIG_PATH"
CONFIG_FILE_PATH_STR = os.getenv(CONFIG_FILE_ENV_VAR, str(DEFAULT_CONFIG_PATH))
CONFIG_FILE_PATH = Path(CONFIG_FILE_PATH_STR)


def load_db_config():
    try:
        print(f"Attempting to load mock API config from: {CONFIG_FILE_PATH}")
        with open(CONFIG_FILE_PATH, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Config file not found at {CONFIG_FILE_PATH}.")
        # Fallback if not found - this could be an issue if essential configs are missing
        # Consider raising an error or having a more robust default.
        # For now, mimicking the original fallback for database_url.
        return {"database": {"url": "sqlite:///./data/mock_orders.db"}} # Default path
    except Exception as e:
        print(f"ERROR: Could not load or parse config file at {CONFIG_FILE_PATH}: {e}")
        return {"database": {"url": "sqlite:///./data/mock_orders.db"}}


config = load_db_config()
# Ensure DATABASE_URL always has a value, even if config loading failed partially
db_config_content = config.get("database", {})
DATABASE_URL = db_config_content.get("url", "sqlite:///./data/mock_orders.db") # Default relative to CWD if totally missing

# The connect_args is recommended for SQLite to handle multiple threads (e.g., FastAPI requests)
# Check if DATABASE_URL is for SQLite before adding connect_args
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)

def create_db_and_tables():
    """
    Creates the database file and all tables defined by SQLModel metadata.
    This should be called once on application startup.
    """
    # Ensure the directory for the SQLite DB exists
    if DATABASE_URL.startswith("sqlite:///"):
        # Remove the 'sqlite:///' prefix
        db_file_path_str = DATABASE_URL[10:] # Length of "sqlite:///"
        
        # Handle paths like ./data/mock_orders.db or data/mock_orders.db
        # These should be relative to the project root if not absolute.
        db_file_path = Path(db_file_path_str)
        
        if not db_file_path.is_absolute():
            db_file_path = PROJECT_ROOT_PATH / db_file_path

        db_dir = db_file_path.parent
        try:
            db_dir.mkdir(parents=True, exist_ok=True)
            print(f"Ensuring database directory exists: {db_dir}")
            print(f"Database file will be at: {db_file_path}")
        except Exception as e:
            print(f"Error creating database directory {db_dir}: {e}")
            # Potentially raise this error if db creation is critical

    SQLModel.metadata.create_all(engine)
    print("Database and tables created (if they didn't exist).")


def get_session():
    """
    Dependency for FastAPI to get a database session.
    Ensures the session is closed after the request.
    """
    with Session(engine) as session:
        yield session