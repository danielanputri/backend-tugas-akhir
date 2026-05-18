import os

def create_tables():
    from app.db.database import engine
    from app.db.base import Base
    from app.models import User, Penjualan, ModelRegistry, PredictionResult, TrainingLog # Import all models to register
    from sqlalchemy import text
    
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    create_tables()
