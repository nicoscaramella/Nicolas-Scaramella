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
            CREATE TABLE IF NOT EXISTS ordenes (
                id TEXT PRIMARY KEY,
                estado TEXT NOT NULL,
                payload JSONB NOT NULL,
                correlation_id TEXT,
                actualizado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS cierres (
                id TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                ts TIMESTAMPTZ,
                procesado BOOLEAN NOT NULL DEFAULT FALSE,
                parte JSONB,
                diferencias JSONB,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        # Bases ya creadas por una versión anterior: se agregan las columnas.
        con.execute("ALTER TABLE cierres ADD COLUMN IF NOT EXISTS parte JSONB")
        con.execute("ALTER TABLE cierres ADD COLUMN IF NOT EXISTS diferencias JSONB")
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
            CREATE TABLE IF NOT EXISTS consultas (
                id SERIAL PRIMARY KEY,
                pregunta TEXT NOT NULL,
                recuperados JSONB NOT NULL DEFAULT '[]',
                respuesta TEXT,
                citas_usadas JSONB NOT NULL DEFAULT '[]',
                modelo TEXT,
                tokens_entrada INT NOT NULL DEFAULT 0,
                tokens_salida INT NOT NULL DEFAULT 0,
                suficiente BOOLEAN NOT NULL DEFAULT FALSE,
                fallback TEXT,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS vision_pendientes (
                id SERIAL PRIMARY KEY,
                nota_id TEXT,
                foto TEXT NOT NULL,
                motivo TEXT,
                procesado BOOLEAN NOT NULL DEFAULT FALSE,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS decisiones (
                id SERIAL PRIMARY KEY,
                orden_id TEXT NOT NULL,
                accion TEXT NOT NULL,
                rol TEXT NOT NULL,
                quien TEXT,
                motivo TEXT,
                creado TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        _crear_rag_chunks(con)


def encolar_vision(nota_id: str | None, foto: str, motivo: str) -> None:
    """Deja el análisis de la foto en cola: sin enlace no se pierde."""
    with _pool().connection() as con:
        existe = con.execute(
            "SELECT 1 FROM vision_pendientes WHERE foto = %s AND NOT procesado", (foto,)
        ).fetchone()
        if existe:
            return
        con.execute(
            "INSERT INTO vision_pendientes (nota_id, foto, motivo) VALUES (%s, %s, %s)",
            (nota_id, foto, motivo),
        )


def vision_pendientes(limite: int = 50) -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, nota_id, foto, motivo FROM vision_pendientes "
            "WHERE NOT procesado ORDER BY creado LIMIT %s",
            (limite,),
        ).fetchall()


def marcar_vision_procesada(fila_id: int) -> None:
    with _pool().connection() as con:
        con.execute("UPDATE vision_pendientes SET procesado = true WHERE id = %s", (fila_id,))


def _crear_rag_chunks(con) -> None:
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


# --------------------------------------------------------------------------- órdenes


ORDENES_CERRADAS = ("Rechazada", "Cerrada", "Certificada")


def guardar_orden(payload: dict, correlation_id: str | None = None) -> bool:
    """Checkpoint de una orden (upsert idempotente por id).

    Devuelve ``True`` si la orden es nueva. El mismo id con otro estado
    actualiza la fila: nunca se duplica.
    """
    with _pool().connection() as con:
        cur = con.execute(
            """
            INSERT INTO ordenes (id, estado, payload, correlation_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                estado = EXCLUDED.estado,
                payload = EXCLUDED.payload,
                correlation_id = COALESCE(EXCLUDED.correlation_id, ordenes.correlation_id),
                actualizado = now()
            RETURNING (xmax = 0) AS nueva
            """,
            (payload["id"], payload["estado"], Jsonb(payload), correlation_id),
        )
        return bool(cur.fetchone()["nueva"])


def obtener_orden(orden_id: str) -> dict | None:
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, estado, payload, correlation_id, actualizado FROM ordenes WHERE id = %s",
            (orden_id,),
        ).fetchone()


def ordenes_abiertas(limite: int = 200) -> list[dict]:
    """Órdenes que no terminaron su circuito (para recuperar tras un corte)."""
    with _pool().connection() as con:
        return con.execute(
            """
            SELECT id, estado, payload, correlation_id, actualizado
            FROM ordenes
            WHERE NOT (estado = ANY(%s))
            ORDER BY actualizado
            LIMIT %s
            """,
            (list(ORDENES_CERRADAS), limite),
        ).fetchall()


def existe_orden_abierta(equipo: str, tareas: list[str]) -> dict | None:
    """Busca una orden abierta del mismo equipo con las mismas tareas (E3).

    Si existe, el flujo agrega la evidencia a esa orden en vez de duplicarla.
    """
    with _pool().connection() as con:
        return con.execute(
            """
            SELECT id, estado, payload, correlation_id
            FROM ordenes
            WHERE payload->>'equipo' = %s
              AND payload->'tareas' = %s
              AND NOT (estado = ANY(%s))
            ORDER BY actualizado DESC
            LIMIT 1
            """,
            (equipo, Jsonb(sorted(set(tareas))), list(ORDENES_CERRADAS)),
        ).fetchone()


def ordenes_por_correlacion(correlation_id: str) -> list[dict]:
    """Todas las órdenes de un mismo caso (evento → orden → cierre)."""
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, estado, payload, correlation_id FROM ordenes "
            "WHERE correlation_id = %s ORDER BY actualizado",
            (correlation_id,),
        ).fetchall()


def registrar_decision(
    orden_id: str, accion: str, rol: str, quien: str | None, motivo: str | None
) -> None:
    """Auditoría de la Central: quién decidió y por qué."""
    with _pool().connection() as con:
        con.execute(
            "INSERT INTO decisiones (orden_id, accion, rol, quien, motivo) "
            "VALUES (%s, %s, %s, %s, %s)",
            (orden_id, accion, rol, quien, motivo),
        )


def listar_ordenes(estado_filtro: str | None = None, limite: int = 200) -> list[dict]:
    with _pool().connection() as con:
        if estado_filtro:
            return con.execute(
                "SELECT id, estado, payload, correlation_id, actualizado FROM ordenes "
                "WHERE estado = %s ORDER BY actualizado DESC LIMIT %s",
                (estado_filtro, limite),
            ).fetchall()
        return con.execute(
            "SELECT id, estado, payload, correlation_id, actualizado FROM ordenes "
            "ORDER BY actualizado DESC LIMIT %s",
            (limite,),
        ).fetchall()


# --------------------------------------------------------------------------- cierres


def guardar_cierre_crudo(payload: dict) -> bool:
    """Guarda una ``NotaCierre`` tal como llegó (idempotente por ``id``).

    El procesamiento (transcribir el audio, comparar contra la orden) es de la
    Entrega 2; acá se persiste apenas llega para no perderlo si el contenedor
    se apaga de golpe.
    """
    ts = payload.get("ts")
    if isinstance(ts, str):
        try:
            ts = datetime.fromisoformat(ts)
        except ValueError:
            ts = None
    if ts is None:
        ts = datetime.now().astimezone()
    with _pool().connection() as con:
        cur = con.execute(
            """
            INSERT INTO cierres (id, payload, ts)
            VALUES (%s, %s, %s)
            ON CONFLICT (id) DO NOTHING
            RETURNING id
            """,
            (payload["id"], Jsonb(payload), ts),
        )
        return cur.fetchone() is not None


def obtener_cierre_crudo(cierre_id: str) -> dict | None:
    with _pool().connection() as con:
        return con.execute("SELECT * FROM cierres WHERE id = %s", (cierre_id,)).fetchone()


def cierres_pendientes(limite: int = 100) -> list[dict]:
    """Cierres recibidos que todavía no se procesaron (para M7)."""
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, payload FROM cierres WHERE NOT procesado ORDER BY creado LIMIT %s",
            (limite,),
        ).fetchall()


def marcar_cierre_procesado(cierre_id: str) -> None:
    with _pool().connection() as con:
        con.execute("UPDATE cierres SET procesado = true WHERE id = %s", (cierre_id,))


def actualizar_cierre_procesado(
    cierre_id: str,
    *,
    parte: dict | None = None,
    diferencias: list[str] | None = None,
) -> None:
    """Guarda el parte de cierre y las diferencias contra la orden."""
    with _pool().connection() as con:
        con.execute(
            """
            UPDATE cierres
            SET procesado = true,
                parte = COALESCE(%s, parte),
                diferencias = COALESCE(%s, diferencias)
            WHERE id = %s
            """,
            (
                Jsonb(parte) if parte is not None else None,
                Jsonb(diferencias) if diferencias is not None else None,
                cierre_id,
            ),
        )


def obtener_cierre_por_orden(orden_id: str) -> dict | None:
    with _pool().connection() as con:
        return con.execute(
            "SELECT id, payload, parte, diferencias, procesado FROM cierres "
            "WHERE payload->>'orden_id' = %s ORDER BY creado DESC LIMIT 1",
            (orden_id,),
        ).fetchone()


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


def registrar_consulta(
    pregunta: str, recuperados: list[dict], salida: dict
) -> None:
    from .auditoria import registro_consulta

    r = registro_consulta(pregunta, recuperados, salida)
    with _pool().connection() as con:
        con.execute(
            """
            INSERT INTO consultas
                (pregunta, recuperados, respuesta, citas_usadas, modelo,
                 tokens_entrada, tokens_salida, suficiente, fallback)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                r["pregunta"],
                Jsonb(r["recuperados"]),
                r["respuesta"],
                Jsonb(r["citas_usadas"]),
                r["modelo"],
                r["tokens_entrada"],
                r["tokens_salida"],
                r["suficiente"],
                r["fallback"],
            ),
        )


def consultas_recientes(limite: int = 20) -> list[dict]:
    with _pool().connection() as con:
        return con.execute(
            "SELECT * FROM consultas ORDER BY id DESC LIMIT %s", (limite,)
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


def citas_del_corpus() -> dict[str, bool]:
    """Cita -> vigente para el paso revisor (no se puede citar lo que no existe)."""
    with _pool().connection() as con:
        filas = con.execute(
            "SELECT cita, bool_and(coalesce(vigente, true)) AS vigente "
            "FROM rag_chunks GROUP BY cita"
        ).fetchall()
    return {f["cita"]: bool(f["vigente"]) for f in filas}


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
