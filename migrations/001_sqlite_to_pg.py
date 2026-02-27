#!/usr/bin/env python3
"""
ARKAINBRAIN — SQLite → PostgreSQL Migration Script (Phase 5A)

Migrates all data from the local SQLite database to Railway PostgreSQL.
Safe to run multiple times (idempotent — skips existing records).

Usage:
    # Set DATABASE_URL first
    export DATABASE_URL=postgresql://user:pass@host:5432/arkainbrain

    # Dry run (shows what would be migrated)
    python migrations/001_sqlite_to_pg.py --dry-run

    # Full migration
    python migrations/001_sqlite_to_pg.py

    # Migrate from specific SQLite file
    python migrations/001_sqlite_to_pg.py --sqlite-path /path/to/arkainbrain.db
"""

import argparse
import json
import os
import sqlite3
import sys

from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_sqlite_conn(path: str):
    conn = sqlite3.connect(path, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def get_pg_conn(url: str):
    import psycopg
    from psycopg.rows import dict_row
    # Railway uses postgres:// but psycopg wants postgresql://
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg.connect(url, row_factory=dict_row)


def migrate(sqlite_path: str, pg_url: str, dry_run: bool = False):
    print(f"{'[DRY RUN] ' if dry_run else ''}Migrating: {sqlite_path} → PostgreSQL")

    sq = get_sqlite_conn(sqlite_path)
    pg = get_pg_conn(pg_url)

    # ── 1. Create schema in PostgreSQL ──
    print("\n1. Creating schema...")
    from config.database import SCHEMA_SQL
    if not dry_run:
        pg.execute(SCHEMA_SQL)
        pg.commit()
    print("   ✓ Schema created")

    # ── 2. Migrate users ──
    users = sq.execute("SELECT * FROM users").fetchall()
    print(f"\n2. Migrating {len(users)} users...")
    migrated_users = 0
    for u in users:
        u = dict(u)
        if dry_run:
            print(f"   → {u.get('email', '?')}")
            continue
        try:
            pg.execute(
                "INSERT INTO users (id, email, name, picture, email_notify, created_at) "
                "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (id) DO NOTHING",
                [u["id"], u["email"], u.get("name"), u.get("picture"),
                 u.get("email_notify", 1), u.get("created_at")]
            )
            migrated_users += 1
        except Exception as e:
            print(f"   ⚠ User {u.get('email')}: {e}")
    if not dry_run:
        pg.commit()
    print(f"   ✓ {migrated_users} users migrated")

    # ── 3. Migrate jobs ──
    jobs = sq.execute("SELECT * FROM jobs ORDER BY created_at").fetchall()
    print(f"\n3. Migrating {len(jobs)} jobs...")
    migrated_jobs = 0
    for j in jobs:
        j = dict(j)
        if dry_run:
            print(f"   → [{j.get('status', '?')}] {j.get('title', '?')}")
            continue
        try:
            pg.execute(
                "INSERT INTO jobs (id, user_id, job_type, title, params, status, "
                "current_stage, output_dir, error, created_at, completed_at, "
                "parent_job_id, version) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (id) DO NOTHING",
                [j["id"], j["user_id"], j.get("job_type", "slot_pipeline"),
                 j["title"], j.get("params"), j.get("status", "queued"),
                 j.get("current_stage"), j.get("output_dir"), j.get("error"),
                 j.get("created_at"), j.get("completed_at"),
                 j.get("parent_job_id"), j.get("version", 1)]
            )
            migrated_jobs += 1
        except Exception as e:
            print(f"   ⚠ Job {j.get('id')}: {e}")
    if not dry_run:
        pg.commit()
    print(f"   ✓ {migrated_jobs} jobs migrated")

    # ── 4. Migrate reviews (if table exists) ──
    try:
        reviews = sq.execute("SELECT * FROM reviews ORDER BY created_at").fetchall()
        print(f"\n4. Migrating {len(reviews)} reviews...")
        migrated_reviews = 0
        for r in reviews:
            r = dict(r)
            if dry_run:
                print(f"   → [{r.get('status', '?')}] {r.get('title', '?')}")
                continue
            try:
                pg.execute(
                    "INSERT INTO reviews (id, job_id, stage, title, summary, files, "
                    "status, approved, feedback, created_at, resolved_at) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                    "ON CONFLICT (id) DO NOTHING",
                    [r["id"], r["job_id"], r["stage"], r["title"],
                     r.get("summary"), r.get("files"), r.get("status", "pending"),
                     r.get("approved"), r.get("feedback"),
                     r.get("created_at"), r.get("resolved_at")]
                )
                migrated_reviews += 1
            except Exception as e:
                print(f"   ⚠ Review {r.get('id')}: {e}")
        if not dry_run:
            pg.commit()
        print(f"   ✓ {migrated_reviews} reviews migrated")
    except sqlite3.OperationalError:
        print("\n4. No reviews table in SQLite — skipping")

    # ── Cleanup ──
    sq.close()
    pg.close()

    print(f"\n{'[DRY RUN] ' if dry_run else ''}Migration complete!")
    if not dry_run:
        print("\n⚠ IMPORTANT: Verify data in PostgreSQL, then set DATABASE_URL in Railway.")
        print("  The app will auto-detect PostgreSQL and stop using SQLite.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate SQLite → PostgreSQL")
    parser.add_argument("--sqlite-path", default=os.getenv("DB_PATH", "arkainbrain.db"),
                        help="Path to SQLite database file")
    parser.add_argument("--pg-url", default=os.getenv("DATABASE_URL", ""),
                        help="PostgreSQL connection URL")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be migrated without writing")
    args = parser.parse_args()

    if not args.pg_url:
        print("ERROR: Set DATABASE_URL env var or pass --pg-url")
        sys.exit(1)

    if not Path(args.sqlite_path).exists():
        print(f"ERROR: SQLite file not found: {args.sqlite_path}")
        sys.exit(1)

    migrate(args.sqlite_path, args.pg_url, args.dry_run)
