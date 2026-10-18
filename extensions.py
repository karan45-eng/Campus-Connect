"""Shared Flask extensions."""
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

# Initialized by create_app / app.py to keep imports simple.
db = SQLAlchemy()
csrf = CSRFProtect()
