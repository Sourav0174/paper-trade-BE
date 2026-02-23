# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker, declarative_base
# from dotenv import load_dotenv

# load_dotenv(dotenv_path=".env")

# DATABASE_URL = os.getenv("DATABASE_URL")

# print("DATABASE_URL:", DATABASE_URL)


# if DATABASE_URL is None:
#     raise ValueError("DATABASE_URL is not set. Check your .env file.")

# engine = create_engine(DATABASE_URL)

# SessionLocal = sessionmaker(
#     autocommit=False,
#     autoflush=False,
#     bind=engine
# )

# Base = declarative_base()

# def get_db():
#     db = SessionLocal()
#     try:
#         yield db
#     finally:
#         db.close()


import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set")

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # 🔥 VERY IMPORTANT (fixes SSL closed error)
    pool_recycle=300      # prevents stale connections
)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
