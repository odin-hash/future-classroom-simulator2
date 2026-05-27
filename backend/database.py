import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Path to the database file (load from environment variable for hosting, or fallback to local SQLite)
raw_db_url = os.getenv("DATABASE_URL")
if raw_db_url and raw_db_url.strip():
    # Strip any whitespace, single quotes, or double quotes that can be introduced by copy-pasting env settings
    DATABASE_URL = raw_db_url.strip().strip("'").strip('"')
else:
    DATABASE_URL = "sqlite:///./classroom.db"

# Normalize 'postgres://' to 'postgresql://' for SQLAlchemy compatibility
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Log parsed dialect status
dialect = DATABASE_URL.split(":")[0] if ":" in DATABASE_URL else "unknown"
print(f"[DB] Normalizing database URL. Parsed Dialect: '{dialect}'")

# Detect if running in a production hosting context
is_prod = (
    os.environ.get("RENDER") == "true" or
    bool(os.environ.get("RAILWAY_STATIC_URL")) or
    os.environ.get("NODE_ENV") == "production"
)

# Adjust connection settings based on the database driver
if not (DATABASE_URL.startswith("sqlite") or DATABASE_URL.startswith("postgresql")):
    print(f"[DB] WARNING: Invalid DATABASE_URL format: '{DATABASE_URL}'. Falling back to local SQLite database.")
    DATABASE_URL = "sqlite:///./classroom.db"

if DATABASE_URL.startswith("sqlite"):
    if is_prod:
        print("❌ CRITICAL: Production environment detected but database is missing or configured as SQLite.")
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
        if is_prod:
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
