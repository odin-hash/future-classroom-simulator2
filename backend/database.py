import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Try to resolve a valid PostgreSQL database URL from the environment
raw_db_url = os.getenv("DATABASE_URL")

# Check if DATABASE_URL is an HTTP/HTTPS address (which is incorrect)
is_http = raw_db_url and (raw_db_url.strip().startswith("http://") or raw_db_url.strip().startswith("https://"))

if not raw_db_url or not raw_db_url.strip() or is_http:
    if is_http:
        print(f"[DB] WARNING: DATABASE_URL is set to an HTTP address ('{raw_db_url}'). Searching for alternative connection strings...")
    
    # Try Render auto-injected database credentials
    alt_db_url = os.getenv("INTERNAL_DATABASE_URL") or os.getenv("EXTERNAL_DATABASE_URL")
    if alt_db_url and alt_db_url.strip():
        print(f"[DB] Found and using alternative database URL: {'INTERNAL_DATABASE_URL' if os.getenv('INTERNAL_DATABASE_URL') else 'EXTERNAL_DATABASE_URL'}")
        raw_db_url = alt_db_url
    else:
        # Try individual DB credentials
        db_user = os.getenv("DB_USER")
        db_pass = os.getenv("DB_PASSWORD")
        db_host = os.getenv("DB_HOST")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME")
        if db_user and db_pass and db_host and db_name:
            print("[DB] Constructing database URL from DB_* environment variables.")
            raw_db_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

if raw_db_url and raw_db_url.strip():
    DATABASE_URL = raw_db_url.strip().strip("'").strip('"')
else:
    DATABASE_URL = "sqlite:///./classroom.db"

# Detect if running in a production hosting context
is_prod = (
    os.environ.get("RENDER") == "true" or
    bool(os.environ.get("RAILWAY_STATIC_URL")) or
    os.environ.get("NODE_ENV") == "production"
)
allow_sqlite_in_prod = os.environ.get("ALLOW_SQLITE_IN_PROD", "false").lower() == "true"

# Recheck if the resolved DATABASE_URL is still HTTP/HTTPS
if DATABASE_URL.startswith("http://") or DATABASE_URL.startswith("https://"):
    print(f"❌ CRITICAL: DATABASE_URL is configured as an HTTP web address ('{DATABASE_URL}').")
    print("A valid database connection string starting with 'postgresql://' or 'postgres://' is required.")
    if is_prod and not allow_sqlite_in_prod:
        raise RuntimeError(
            f"Invalid DATABASE_URL configuration: configured as web address '{DATABASE_URL}' instead of a database connection string. "
            "Please check your Render/Railway environment variables or set ALLOW_SQLITE_IN_PROD=true to bypass."
        )
    DATABASE_URL = "sqlite:///./classroom.db"

# Normalize 'postgres://' to 'postgresql://' for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Log parsed dialect status
dialect = DATABASE_URL.split(":")[0] if ":" in DATABASE_URL else "unknown"
print(f"[DB] Normalizing database URL. Parsed Dialect: '{dialect}'")

# Adjust connection settings based on the database driver
if not (DATABASE_URL.startswith("sqlite") or DATABASE_URL.startswith("postgresql")):
    print(f"[DB] WARNING: Invalid DATABASE_URL format: '{DATABASE_URL}'. Falling back to local SQLite database.")
    DATABASE_URL = "sqlite:///./classroom.db"

if DATABASE_URL.startswith("sqlite"):
    if is_prod and not allow_sqlite_in_prod:
        print("❌ CRITICAL: Production environment detected but database is missing or configured as SQLite.")
        print("To override and force SQLite fallback, set ALLOW_SQLITE_IN_PROD=true.")
        raise RuntimeError("PostgreSQL database is required in production deployment contexts.")
    engine = create_engine(
        DATABASE_URL, connect_args={"check_same_thread": False}
    )
    print(f"[DB] Initialized SQLite local engine: {DATABASE_URL}")
else:
    try:
        # Create Postgres engine and test connection immediately
        engine = create_engine(DATABASE_URL)
        with engine.connect() as conn:
            pass
        print(f"[DB] Successfully connected to PostgreSQL database (Engine: {dialect}).")
    except Exception as pg_err:
        print(f"[DB] ERROR: Could not connect to PostgreSQL: {pg_err}")
        if is_prod and not allow_sqlite_in_prod:
            print("❌ CRITICAL: Database connection failed in production context. Aborting startup to fail-fast.")
            raise RuntimeError(f"PostgreSQL database connection failed: {pg_err}")
        print("[DB] Falling back to local SQLite database.")
        DATABASE_URL = "sqlite:///./classroom.db"
        engine = create_engine(
            DATABASE_URL, connect_args={"check_same_thread": False}
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency to get db session in API endpoints
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
