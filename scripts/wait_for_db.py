"""
LogSentinel — Database readiness check for Docker Compose.

Polls PostgreSQL connection until ready, used as a Docker Compose
depends_on health check condition. Retries with exponential backoff.

Usage:
    python scripts/wait_for_db.py

Environment Variables:
    DATABASE_URL  — PostgreSQL connection string
    DB_MAX_RETRIES — Maximum retry attempts (default: 30)
    DB_RETRY_INTERVAL — Initial retry interval in seconds (default: 2)
"""

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
)
logger = logging.getLogger("wait_for_db")


def wait_for_db():
    """Poll PostgreSQL until it accepts connections."""
    # Parse DATABASE_URL for connection params
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://LogSentinel:LogSentinel@localhost:5432/LogSentinel",
    )

    # Extract host, port, user, password, dbname from URL
    # Handle both asyncpg and regular postgresql URLs
    clean_url = db_url.replace("postgresql+asyncpg://", "").replace("postgresql://", "")
    user_pass, host_db = clean_url.split("@", 1)
    user, password = user_pass.split(":", 1)
    host_port, dbname = host_db.split("/", 1)

    if ":" in host_port:
        host, port = host_port.split(":", 1)
        port = int(port)
    else:
        host = host_port
        port = 5432

    max_retries = int(os.getenv("DB_MAX_RETRIES", "30"))
    base_interval = float(os.getenv("DB_RETRY_INTERVAL", "2"))

    logger.info("Waiting for PostgreSQL at %s:%d/%s ...", host, port, dbname)

    for attempt in range(1, max_retries + 1):
        try:
            import psycopg2

            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                dbname=dbname,
                connect_timeout=5,
            )
            conn.close()
            logger.info("✅ PostgreSQL is ready! (attempt %d/%d)", attempt, max_retries)
            return True

        except Exception as e:
            # Exponential backoff with cap at 10 seconds
            wait_time = min(base_interval * (1.5 ** (attempt - 1)), 10)
            logger.info(
                "Attempt %d/%d — %s. Retrying in %.1fs...",
                attempt,
                max_retries,
                str(e)[:100],
                wait_time,
            )
            time.sleep(wait_time)

    logger.error("❌ PostgreSQL not ready after %d attempts — giving up", max_retries)
    return False


if __name__ == "__main__":
    success = wait_for_db()
    sys.exit(0 if success else 1)
