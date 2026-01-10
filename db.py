from sqlalchemy import create_engine, Column, Integer, String, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

engine = create_engine("sqlite:///bot.db", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()

class BotEvent(Base):
    __tablename__ = "cBotEvents"

    id = Column(Integer, primary_key=True, index=True)
    event = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

def log_event(message: str):
    session = SessionLocal()
    ev = BotEvent(event=message)
    session.add(ev)
    session.commit()
    session.close()

def init_db():
    Base.metadata.create_all(bind=engine)
