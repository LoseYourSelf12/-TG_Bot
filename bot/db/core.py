import os
import psycopg
from psycopg.rows import dict_row

async def get_conn():
    return await psycopg.AsyncConnection.connect(
        os.getenv("PG_DSN_NATIVE", "dbname=app user=app password=app host=postgres port=5432"),
        row_factory=dict_row,
    )
