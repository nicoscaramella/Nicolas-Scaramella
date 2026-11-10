"""Persistencia en PostgreSQL 16 + pgvector."""

from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Any

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .config import settings

pool: ConnectionPool | None = None


def init_db() -> None:
    global pool
    if pool is not None:
        return
    ultimo = None
    # Primero la extensión, después el pool con el adaptador de pgvector:
    # register_vector necesita que el tipo `vector` ya exista.
    for _ in range(40):
        try:
            with psycopg.connect(settings.database_url, autocommit=True) as con:
                con.execute("SELECT 1")
                con.execute("CREATE EXTENSION IF NOT EXISTS vector")
            break
        except Exception as exc:  # pragma: no cover - depende del arranque de Postgres
            ultimo = exc
            time.sleep(1.5)
    else:
        raise RuntimeError(f"No se pudo conectar a PostgreSQL: {ultimo}")

    pool = ConnectionPool(
        settings.database_url,
        min_size=1,
        max_size=4,
        configure=register_vector,
        kwargs={"row_factory": dict_row},
        open=True,
    )

    with pool.connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS partes (
                nota_id TEXT PRIMARY KEY,
                ts TIMESTAMPTZ,
                operador TEXT,
                filas JSONB NOT NULL DEFAULT '[]',
                ambiguedades JSONB NOT NULL DEFAULT '[]',
                estado TEXT NOT NULL DEFAULT 'nueva',
                intento INT NOT NULL DEFAULT 0,
                actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS mensajes_tablet (
                id TEXT PRIMARY KEY,
                nota_id TEXT NOT NULL,
                tipo TEXT NOT NULL,
                intento INT NOT NULL DEFAULT 0,
                filas JSONB NOT NULL DEFAULT '[]',
                ambiguedades JSONB NOT NULL DEFAULT '[]',
                payload JSONB NOT NULL,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS eventos (
                id TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                ts TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS outbox (
                id SERIAL PRIMARY KEY,
                topico TEXT NOT NULL,
                payload JSONB NOT NULL,
                publicado BOOLEAN NOT NULL DEFAULT FALSE,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS consumo (
                id SERIAL PRIMARY KEY,
                modelo TEXT NOT NULL,
                tokens_entrada INT NOT NULL DEFAULT 0,
                tokens_salida INT NOT NULL DEFAULT 0,
                tokens_por_segundo DOUBLE PRECISION,
                velocidad_estimada BOOLEAN NOT NULL DEFAULT FALSE,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id TEXT PRIMARY KEY,
                doc TEXT,
                cita TEXT,
                numero TEXT,
                titulo TEXT,
                clave TEXT,
                pagina INT,
                vigente BOOLEAN,
                equipos TEXT[],
                fabricante TEXT,
                tipo TEXT,
                texto TEXT NOT NULL,
                embedding vector(384)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS rag_chunks_fts_idx ON rag_chunks "
            "USING gin (to_tsvector('spanish', texto))"
        )


def _pool() -> ConnectionPool:
    if pool is None:
        init_db()
    assert pool is not None
    return pool


# --------------------------------------------------------------------------- partes


def guardar_parte(nota: dict) -> bool:
    with _pool().connection() as con:
        cur = con.execute(
            """
            INSERT INTO partes (nota_id, ts, operador, estado)
            VALUES (%s, %s, %s, 'nueva')
            ON CONFLICT (nota_id) DO NOTHING
            RETURNING nota_id
            """,
            (nota["id"], datetime.fromisoformat(nota["ts"]), nota.get("operador")),
        )
        return cur.fetchone() is not None


def obtener_parte(nota_id: str) -> dict | None:
    with _pool().connection() as con:
        return con.execute("SELECT * FROM partes WHERE nota_id = %s", (nota_id,)).fetchone()


def actualizar_parte(
    nota_id: str,
    *,
    filas: list[dict] | None = None,
    ambiguedades: list[dict] | None = None,
    estado: str | None = None,
    intento: int | None = None,
) -> None:
    campos, valores = [], []
    for nombre, valor in (
        ("filas", filas),
        ("ambiguedades", ambiguedades),
        ("estado", estado),
        ("intento", intento),
    ):
        if valor is not None:
            campos.append(f"{nombre} = %s")
            valores.append(Jsonb(valor) if nombre in ("filas", "ambiguedades") else valor)
    if not campos:
        return
    valores.append(nota_id)
    with _pool().connection() as con:
        con.execute(
            f"UPDATE partes SET {', '.join(campos)}, actualizado = now() WHERE nota_id = %s",
            valores,
        )


# --------------------------------------------------------------------------- tablet


def guardar_mensaje(
    mensaje_id: str,
    nota_id: str,
    tipo: str,
    payload: dict,
    filas: list[dict],
    ambiguedades: list[dict],
    intento: int,
) -> None:
    with _pool().connection() as con:
        con.execute(
            """
            INSERT INTO mensajes_tablet
                (id, nota_id, tipo, intento, filas, ambiguedades, payload)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (
                mensaje_id,
                nota_id,
                tipo,
                intento,
                Jsonb(filas),
                Jsonb(ambiguedades),
                Jsonb(payload),
            ),
        )


def obtener_mensaje(mensaje_id: str) -> dict | None:
    with _pool().connection() as con:
        return con.execute(
            "SELECT * FROM mensajes_tablet WHERE id = %s", (mensaje_id,)
        ).fetchone()


# --------------------------------------------------------------------------- eventos y outbox


def guardar_evento(evento: dict) -> bool:
    ts = evento.get("ts")
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts)
    if ts is None:
        ts = datetime.now().astimezone()
    payload = dict(evento)
    payload["ts"] = ts.isoformat() if isinstance(ts, datetime) else ts
    with _pool().connection() as con:
        cur = con.execute(
            """
            INSERT INTO eventos (id, payload, ts)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            (evento["id"], Jsonb(payload), ts),
        )
        return cur.fetchone() is not None


def encolar(topico: str, payload: dict) -> int:
    with _pool().connection() as con:
        cur = con.execute(
            "INSERT INTO outbox (topico, payload) VALUES (%s, %s) RETURNING id",
            (topico, Jsonb(payload)),
        )
        fila = cur.fetchone()
        return int(fila["id"])


def pendientes_count() -> int:
    with _pool().connection() as con:
        fila = con.execute(
            "SELECT count(*) AS n FROM outbox WHERE NOT publicado"
        ).fetchone()
        return int(fila["n"])


def pendientes(limite: int = 100) -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, topico, payload FROM outbox WHERE NOT publicado ORDER BY id LIMIT %s",
            (limite,),
        ).fetchall()


def marcar_publicado(fila_id: int) -> None:
    with _pool().connection() as con:
        con.execute("UPDATE outbox SET publicado = true WHERE id = %s", (fila_id,))


# --------------------------------------------------------------------------- consumo


def registrar_consumo(
    modelo: str,
    tokens_entrada: int,
    tokens_salida: int,
    tokens_por_segundo: float | None = None,
    velocidad_estimada: bool = False,
) -> None:
    with _pool().connection() as con:
        con.execute(
            """
            INSERT INTO consumo
                (modelo, tokens_entrada, tokens_salida, tokens_por_segundo,
                 velocidad_estimada)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (modelo, tokens_entrada, tokens_salida, tokens_por_segundo, velocidad_estimada),
        )


def consumo_por_modelo() -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            """
            SELECT modelo,
                   sum(tokens_entrada)::int AS tokens_entrada,
                   sum(tokens_salida)::int AS tokens_salida,
                   avg(tokens_por_segundo) AS tokens_por_segundo,
                   bool_or(velocidad_estimada) AS velocidad_estimada
            FROM consumo
            GROUP BY modelo
            ORDER BY modelo
            """
        ).fetchall()


# --------------------------------------------------------------------------- RAG


def rag_count() -> int:
    with _pool().connection() as con:
        return int(con.execute("SELECT count(*) AS n FROM rag_chunks").fetchone()["n"])


def rag_insertar(chunks: list[dict]) -> None:
    if not chunks:
        return
    with _pool().connection() as con:
        with con.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO rag_chunks
                    (id, doc, cita, numero, titulo, clave, pagina, vigente,
                     equipos, fabricante, tipo, texto, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                [
                    (
                        c["id"],
                        c.get("doc"),
                        c.get("cita") or c["id"],
                        c.get("numero"),
                        c.get("titulo"),
                        c.get("clave"),
                        c.get("pagina"),
                        c.get("vigente"),
                        c.get("equipos"),
                        c.get("fabricante"),
                        c.get("tipo"),
                        c["texto"],
                        Vector(c["embedding"]),
                    )
                    for c in chunks
                ],
            )


def rag_vector(embedding: list[float], k: int = 20) -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            """
            SELECT id, doc, cita, titulo, texto, vigente, equipos,
                   1 - (embedding <=> %s) AS score
            FROM rag_chunks
            WHERE vigente IS NOT FALSE
            ORDER BY embedding <=> %s
            LIMIT %s
            """,
            (Vector(embedding), Vector(embedding), k),
        ).fetchall()


def rag_fts(query: str, k: int = 20) -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            """
            SELECT id, doc, cita, titulo, texto, vigente, equipos,
                   ts_rank_cd(to_tsvector('spanish', texto),
                              plainto_tsquery('spanish', %s)) AS score
            FROM rag_chunks
            WHERE vigente IS NOT FALSE
              AND to_tsvector('spanish', texto) @@ plainto_tsquery('spanish', %s)
            ORDER BY score DESC
            LIMIT %s
            """,
            (query, query, k),
        ).fetchall()
