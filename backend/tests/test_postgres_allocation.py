"""Opt-in: concurrent Get Tasks on real PostgreSQL never assigns a task twice (FOR UPDATE SKIP LOCKED).

Needs a disposable, migrated database (never the shared one):
    TEST_DATABASE_URL=postgresql://... pytest tests/test_postgres_allocation.py
The test creates its own users/dataset/tasks and deletes them afterwards.
"""
import os
import threading
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import sessionmaker

from app.models.customer import CustomerDataset, CustomerPoi
from app.models.platform import ComparisonResult, ComparisonRun, Task, TaskEvent, User
from app.services.workflow import claim

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="Set TEST_DATABASE_URL to a disposable migrated PostgreSQL database")


def test_concurrent_claims_are_disjoint():
    engine = create_engine(URL.replace("postgresql://", "postgresql+psycopg://", 1), pool_size=10)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    dataset_id, run_id = uuid4(), uuid4()
    with Session() as db:
        users = [User(username=f"alloc-{uuid4().hex[:8]}", display_name="Alloc", password_hash="x", roles=["reviewer"], aois=[]) for _ in range(6)]
        db.add_all(users)
        db.add(CustomerDataset(id=dataset_id, filename="alloc.csv", customer="HERE", aoi="Divisoria", country="PHL",
                               sha256=uuid4().hex * 2, row_count=0, columns=[]))
        db.flush()
        db.add(ComparisonRun(id=run_id, dataset_id=dataset_id, aoi="Divisoria", rules_version="t", fingerprint="t", batch_ids=[]))
        db.flush()
        for i in range(60):
            r = ComparisonResult(run_id=run_id, result_key=f"k{i}", content_hash="h", outcome="potential_new", priority=3, explanation={})
            db.add(r)
            db.flush()
            db.add(Task(task_key=uuid4().hex, kind="review", queue="review_new", status="open", priority=3, dataset_id=dataset_id,
                        aoi="Divisoria", run_id=run_id, result_id=r.id, result_key=r.result_key))
        db.commit()
        user_ids = [u.id for u in users]
    claimed, errors = {}, []

    def worker(uid):
        try:
            with Session() as db:
                tasks, _ = claim(db, db.get(User, uid), limit=15)
                claimed[uid] = [t.id for t in tasks]
                db.commit()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(uid,)) for uid in user_ids]
    [t.start() for t in threads]
    [t.join() for t in threads]
    try:
        assert not errors
        all_ids = [tid for ids in claimed.values() for tid in ids]
        assert len(all_ids) == len(set(all_ids)) == 60  # every task claimed exactly once
    finally:
        with Session() as db:
            task_ids = db.scalars(select(Task.id).where(Task.run_id == run_id)).all()
            db.execute(delete(TaskEvent).where(TaskEvent.task_id.in_(task_ids)))
            db.execute(delete(Task).where(Task.run_id == run_id))
            db.execute(delete(ComparisonRun).where(ComparisonRun.id == run_id))
            db.execute(delete(CustomerDataset).where(CustomerDataset.id == dataset_id))
            db.execute(delete(User).where(User.id.in_(user_ids)))
            db.commit()
        engine.dispose()
