"""Database helpers for Outbox integration tests."""

import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg_pool import AsyncConnectionPool

from ascetic_ddd.seedwork.infrastructure.session.pg_session import PgSessionPool

# Load environment variables from config/.env
_config_env = Path(__file__).parents[4] / 'config' / '.env'
load_dotenv(_config_env)


async def make_pg_pool():
    """Create PostgreSQL connection pool for testing."""
    postgresql_url = os.environ.get(
        'TEST_INTERNAL_POSTGRESQL_URL',
        ''
    )
    pool = AsyncConnectionPool(postgresql_url, open=False)
    await pool.open()
    return pool


async def make_pg_session_pool():
    """Create PostgreSQL session pool for testing."""
    pool = await make_pg_pool()
    return PgSessionPool(pool)
