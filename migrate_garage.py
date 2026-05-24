#!/usr/bin/env python3
"""Database migration script to add garage columns"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import engine, Base
from sqlalchemy import inspect, text

def migrate_database():
    """Add missing garage columns to vehicles table"""
    
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns('vehicles')]
    
    print("Current columns:", columns)
    
    with engine.connect() as conn:
        # Add is_garage column if not exists
        if 'is_garage' not in columns:
            print("Adding is_garage column...")
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN is_garage BOOLEAN DEFAULT 0"))
            conn.commit()
            print("[OK] Added is_garage column")
        
        # Add garage_number column if not exists
        if 'garage_number' not in columns:
            print("Adding garage_number column...")
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN garage_number VARCHAR(50)"))
            conn.commit()
            print("[OK] Added garage_number column")
        
        # Add garage_valid_until column if not exists
        if 'garage_valid_until' not in columns:
            print("Adding garage_valid_until column...")
            conn.execute(text("ALTER TABLE vehicles ADD COLUMN garage_valid_until DATE"))
            conn.commit()
            print("[OK] Added garage_valid_until column")
    
    print("\n[SUCCESS] Database migration completed!")

if __name__ == "__main__":
    migrate_database()
