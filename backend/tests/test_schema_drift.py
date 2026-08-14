"""
A column added to a model without a migration is invisible until production.

create_all() creates missing tables and never alters an existing one, so the
test database — rebuilt from the models on every run — always looks correct
while the deployed one silently lacks the column. The first request that
SELECTs the table returns 500, with nothing at startup to explain why.

That is exactly how /auditor/batches broke: audit_batches gained
show_results_to_auditor with no migration behind it, and 2074 tests passed.
"""
from sqlalchemy import text

from database import Base, report_schema_drift


class TestSchemaDrift:

    def test_a_clean_database_reports_no_drift(self, engine):
        assert report_schema_drift(engine) == {}

    def test_a_missing_column_is_named(self, engine):
        """
        The check has to say WHICH column, or it is just another way of
        knowing something is wrong.
        """
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE audit_batches DROP COLUMN show_results_to_auditor"))
            conn.commit()
        try:
            drift = report_schema_drift(engine)
            assert "audit_batches" in drift
            assert "show_results_to_auditor" in drift["audit_batches"]
        finally:
            with engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE audit_batches ADD COLUMN "
                    "show_results_to_auditor BOOLEAN DEFAULT TRUE"))
                conn.commit()

    def test_every_column_added_after_launch_has_a_migration(self):
        """
        The rule this module broke, checked statically because it cannot be
        checked dynamically: the test database is built from the models, so a
        column with no migration looks perfectly correct here and is absent
        only where it matters.

        Columns present in the models but not in the auditor tables' original
        CREATE are listed explicitly — adding one to a model means adding it
        here and to _run_migrations() together.
        """
        import pathlib as _p
        migrations = _p.Path(__file__).resolve().parent.parent / "database.py"
        sql = migrations.read_text()
        for table, col in [
            ("audit_batches", "show_results_to_auditor"),
            ("audit_scoring_configs", "observed_share_pct"),
            ("audit_scoring_configs", "mix_substitute_pcs"),
        ]:
            assert f'_add_col("{table}", "{col}"' in sql, (
                f"{table}.{col} exists in the model with no migration behind it — "
                f"it will be missing from every database that predates it")

    def test_every_auditor_table_is_covered(self, engine):
        """
        The whole module at once — the check is only worth having if it looks
        at every table, not the one that happened to break.
        """
        audit_tables = [t for t in Base.metadata.tables if t.startswith("audit_")]
        assert len(audit_tables) >= 9
        drift = report_schema_drift(engine)
        assert not any(t in drift for t in audit_tables), drift
