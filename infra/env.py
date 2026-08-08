"""Environment variable access and database connection construction.

First extraction slice out of scripts/*.py -- byte-identical across
ingest_parcels.py, ingest_zoning_permits.py, flag_invalid_geometry.py and
compose_property_file.py before this move. No behavior change, no
canonical-copy judgment call: there was only ever one copy to choose
between.
"""
import os

import psycopg2
from dotenv import load_dotenv


def env(name):
    load_dotenv(override=False)
    val = os.environ.get(name)
    if not val:
        raise SystemExit(f"missing required environment variable: {name}")
    return val


def get_db():
    conn = psycopg2.connect(env("DATABASE_URL"))
    conn.autocommit = False
    return conn
