"""
Fill in Review Score on audit results scored before it existed.

Everything needed was already stored: the assignment keeps the claim and the
ground truth, the result keeps the findings. So this is a pure recomputation —
it re-runs the scorer over saved inputs rather than inventing anything.

It also re-derives the DETECTION figures and reports any that disagree with
what is on the row. They should never disagree; if they do, the scorer changed
in a way that altered existing results, which is worth knowing before the
numbers are trusted.

    python scripts/backfill_audit_review.py            # report only
    python scripts/backfill_audit_review.py --write    # and save

Idempotent: rows that already have a review score are skipped unless --all.
"""
import argparse
import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))

for key in ("STORAGE_ENDPOINT_URL", "STORAGE_ACCESS_KEY", "STORAGE_SECRET_KEY",
            "STORAGE_BUCKET_NAME", "STORAGE_PUBLIC_URL", "MASTER_ADMIN_PASSPHRASE"):
    os.environ.setdefault(key, "x")

from database import SessionLocal  # noqa: E402
from models import AuditAssignment, AuditResult  # noqa: E402
from routers.auditor_pkg.shared import fields_for, scoring_config  # noqa: E402
from services.audit_scoring import score_chart  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="save the results")
    ap.add_argument("--all", action="store_true",
                    help="recompute rows that already have a review score")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        cfg = scoring_config(db)
        q = db.query(AuditResult)
        if not args.all:
            q = q.filter(AuditResult.review_total.is_(None))
        rows = q.all()
        if not rows:
            print("nothing to backfill")
            return 0

        assignments = {
            a.id: a for a in db.query(AuditAssignment).filter(
                AuditAssignment.id.in_([r.assignment_id for r in rows])).all()
        }

        done = skipped = drifted = 0
        for row in rows:
            assignment = assignments.get(row.assignment_id)
            if assignment is None:
                # The assignment is what holds the claim; without it there is
                # no denominator to compute against.
                skipped += 1
                continue
            poa = "poa" in {f for spec in (fields_for(row.specialty) or {}).values()
                            for f in (spec or [])}
            score = score_chart(
                assignment.ground_truth or [], row.findings or [], cfg,
                query_expected=row.query_expected,
                query_flagged=row.query_flagged,
                claim=assignment.claim or {},
                poa_applies=poa)

            if row.audit_accuracy is not None \
                    and abs(score.audit_accuracy - row.audit_accuracy) > 0.011:
                drifted += 1
                print(f"  DETECTION DRIFT result {row.id}: stored "
                      f"{row.audit_accuracy} recomputed {score.audit_accuracy}")

            row.review_total = score.review_total
            row.review_correct = score.review_correct
            row.review_score = score.review_score
            row.review_sections = score.review_sections
            row.review_attributes = score.review_attributes
            done += 1

        print(f"recomputed {done}, skipped {skipped} (no assignment), "
              f"detection drift on {drifted}")
        if args.write:
            db.commit()
            print("saved")
        else:
            db.rollback()
            print("dry run — nothing saved, pass --write to commit")
        return 1 if drifted else 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
