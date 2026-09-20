import os
import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Student SQL Lab API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    sql: str


def get_connection():
    return psycopg.connect(
        host=os.getenv("DATABASE_HOST", "postgres"),
        port=os.getenv("DATABASE_PORT", "5432"),
        dbname=os.getenv("DATABASE_NAME", "sqllab"),
        user=os.getenv("DATABASE_USER", "sqladmin"),
        password=os.getenv("DATABASE_PASSWORD"),
        connect_timeout=5,
    )


@app.get("/")
def root():
    return {
        "name": "Student SQL Lab",
        "status": "running"
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/api/query")
def run_query(request: QueryRequest):

    sql = request.sql.strip()

    if not sql:
        raise HTTPException(
            status_code=400,
            detail="SQL cannot be empty"
        )

    try:
        with get_connection() as conn:

            # Stop queries that run for too long
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = '10s'")
                cur.execute(sql)

                if cur.description:
                    columns = [
                        column.name
                        for column in cur.description
                    ]

                    rows = cur.fetchmany(500)

                    return {
                        "type": "result",
                        "columns": columns,
                        "rows": rows,
                        "row_count": len(rows)
                    }

                conn.commit()

                return {
                    "type": "message",
                    "message": "Query executed successfully.",
                    "affected_rows": cur.rowcount
                }

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        )
