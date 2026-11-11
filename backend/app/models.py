"""SQLAlchemy models. See ARCHITECTURE.md for the schema diagram."""
import enum
from datetime import datetime
from sqlalchemy import (Column, DateTime, Enum, Float, ForeignKey, Integer,
                        String, Text, create_engine)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from .config import DATABASE_URL

Base = declarative_base()

class JobStatus(str, enum.Enum):
    QUEUED = "queued"; PROCESSING = "processing"; DONE = "done"
    NEEDS_REVIEW = "needs_review"; FAILED = "failed"

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    filename = Column(String, nullable=False)
    original_filename = Column(String, nullable=False)
    file_type = Column(String)          # pdf / image / spreadsheet / csv
    mime_type = Column(String)
    file_size = Column(Integer)
    sha256 = Column(String, index=True)
    page_count = Column(Integer)
    sheet_names = Column(Text)          # JSON list
    status = Column(String, default=JobStatus.QUEUED.value, index=True)
    error_message = Column(Text)
    extracted_text = Column(Text)
    ocr_used = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    extraction = relationship("Extraction", back_populates="document", uselist=False,
                              cascade="all, delete-orphan")
    validations = relationship("ValidationError", back_populates="document",
                               cascade="all, delete-orphan")
    history = relationship("ProcessingHistory", back_populates="document",
                           cascade="all, delete-orphan")

class Extraction(Base):
    __tablename__ = "extractions"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), unique=True, index=True)
    invoice_number = Column(String, index=True)
    invoice_date = Column(String)
    supplier_name = Column(String, index=True)
    customer_name = Column(String, index=True)
    subtotal = Column(Float)
    tax = Column(Float)
    total = Column(Float)
    currency = Column(String)
    line_items_json = Column(Text)      # JSON list of {description, qty, unit_price, amount}
    confidence_json = Column(Text)      # JSON {field: 0..1}
    raw_json = Column(Text)             # full structured JSON
    document = relationship("Document", back_populates="extraction")

class ValidationError(Base):
    __tablename__ = "validation_errors"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    code = Column(String, index=True)   # MISSING_FIELD, TOTAL_MISMATCH, ...
    field = Column(String)
    severity = Column(String)           # error / warning
    message = Column(Text)
    document = relationship("Document", back_populates="validations")

class ProcessingHistory(Base):
    __tablename__ = "processing_history"
    id = Column(Integer, primary_key=True)
    document_id = Column(Integer, ForeignKey("documents.id"), index=True)
    step = Column(String)               # upload / text_extract / ocr / extract / validate / done
    status = Column(String)
    detail = Column(Text)
    duration_ms = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    document = relationship("Document", back_populates="history")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

def init_db():
    Base.metadata.create_all(engine)
