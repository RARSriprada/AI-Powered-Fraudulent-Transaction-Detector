import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

DATABASE_URL = "sqlite:///./transactions.db"

engine = sqlalchemy.create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class Transaction(Base):
    __tablename__ = "transactions"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True)
    card_number_encrypted = sqlalchemy.Column(sqlalchemy.String, index=True)
    amount = sqlalchemy.Column(sqlalchemy.Float)
    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.utcnow)
    is_fraud = sqlalchemy.Column(sqlalchemy.Integer, default=-1)  # -1: unprocessed, 0: not fraud, 1: fraud
    explanation = sqlalchemy.Column(sqlalchemy.String, nullable=True)


class User(Base):
    __tablename__ = "users"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True)
    username = sqlalchemy.Column(sqlalchemy.String, unique=True, index=True)
    hashed_password = sqlalchemy.Column(sqlalchemy.String)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True)
    username = sqlalchemy.Column(sqlalchemy.String, index=True)
    timestamp = sqlalchemy.Column(sqlalchemy.DateTime, default=datetime.datetime.utcnow)
    action = sqlalchemy.Column(sqlalchemy.String)


def create_db():
    """Create tables if not exist"""
    Base.metadata.create_all(bind=engine)
