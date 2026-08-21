"""
Auditing E/M and ED Profee end to end.

No E/M answer keys exist in production yet, so every one of these builds its
own. That is the point: the wiring has to be provably right BEFORE the data
arrives, or the first real batch is where the faults are found.

The design decisions being pinned:

  * the key comes from em_answer_keys, not answer_keys — one chart, one truth
  * MDM is audited at the three LEVELS, not the twenty-six element ticks
  * a level error is only revenue-impacting when it moves the E/M code, because
    two of three components decide it
  * which levels the trainer overrode steers the planting and is NOT shown to
    the auditor
"""
import json

import pytest
from sqlalchemy import text

from conftest import make_chart
from models import AnswerKey, AuditKeySet, Specialty
from models.charts import Specialty as Sp
from routers.auditor_pkg.shared import audit_key_for, chart_pool, form_spec
from services.audit_mutation import MUTATION_KINDS, MutationConfig, generate
from services.em_audit_key import load as load_em_key


def _em_key(db, chart_id, copa="Moderate", dr="Moderate", risk="Moderate",
            em_code="99214", overridden=("risk",), procs="[]", dx=None):
    db.execute(text("""
        INSERT INTO em_answer_keys
          (chart_id, em_code, em_modifier, dx_codes, procedure_cpts,
           copa_level, dr_level, risk_level,
           copa_level_overridden, dr_level_overridden, risk_level_overridden,
           entered_by)
        VALUES (:c, :code, '', :dx, :procs, :copa, :dr, :risk,
                :o_copa, :o_dr, :o_risk, 't')"""),
        {"c": chart_id, "code": em_code,
         "dx": json.dumps(dx or ["J18.9", "E11.9"]), "procs": procs,
         "copa": copa, "dr": dr, "risk": risk,
         "o_copa": "copa" in overridden, "o_dr": "dr" in overridden,
         "o_risk": "risk" in overridden})
    db.commit()


def _only(kind):
    zeros = {f: 0 for _k, f in MUTATION_KINDS}
    zeros[dict(MUTATION_KINDS)[kind]] = 100
    return MutationConfig(**zeros)


class TestTheKeyComesFromTheEmTable:
    def test_an_em_chart_reads_its_own_key(self, client, db):
        """
        Not the ordinary answer key. One chart carrying two truths would
        disagree the first time either was edited — silently, with the coder
        graded against one and the auditor against the other.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        key = audit_key_for(db, chart)
        assert key is not None
        assert key.pdx_code == "J18.9"
        assert [s["code"] for s in key.sdx] == ["E11.9"]
        assert key.cpt[0]["code"] == "99214"
        assert key.mdm == {"copa": "Moderate", "dr": "Moderate", "risk": "Moderate"}

    def test_a_chart_with_no_em_key_is_not_auditable(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        assert audit_key_for(db, chart) is None

    def test_an_ordinary_specialty_still_reads_answer_keys(self, client, db):
        chart = make_chart(db, specialty="IP-DRG")
        db.add(AnswerKey(chart_id=chart.id, specialty=Specialty.IP_DRG,
                         pdx_code="J18.9", pdx_poa="Y", sdx=[], pcs=[], cpt=[],
                         entered_by="t"))
        db.commit()
        key = audit_key_for(db, chart)
        assert isinstance(key, AnswerKey)

    def test_the_pool_accepts_em_charts_with_an_em_key(self, client, db):
        """
        The eligibility join looks at answer_keys, which no E/M chart has —
        so without the branch every E/M batch would allocate nothing.
        """
        from models import AuditBatch, BatchStatus
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        batch = AuditBatch(name="EM wave", specialty=Specialty.EM,
                           charts_per_auditor=1, created_by="t",
                           status=BatchStatus.OPEN)
        db.add(batch); db.commit()
        assert [c.id for c in chart_pool(db, batch)] == [chart.id]

    def test_audit_key_status_counts_em_keys(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        body = client.get("/auditor/keys/status", params={"specialty": "E/M"}).json()
        assert body["auditable"] == 1
        assert body["uncurated"] == 1
        assert body["no_answer_key"] == 0

    def test_the_uncurated_list_includes_em_charts_with_em_keys(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        body = client.get("/auditor/keys/uncurated", params={"specialty": "E/M"}).json()
        assert body["total"] == 1
        assert body["charts"][0]["chart_id"] == chart.id

    def test_the_picker_includes_em_charts_with_em_keys(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        body = client.get("/auditor/charts", params={"specialty": "E/M"}).json()
        assert [c["id"] for c in body["charts"]] == [chart.id]

    def test_an_em_chart_can_receive_an_authored_audit_version(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)

        r = client.post(f"/auditor/keys/chart/{chart.id}", json={
            "name": "Missed secondary",
            "authored_by": "T",
            "passphrase": "test-passphrase",
            "mutations": [{
                "section": "SDx", "action": "Add", "correct_value": "E11.9",
                "line": 0,
            }],
        })
        assert r.status_code == 200, r.text
        assert r.json()["planting_count"] == 1

    def test_stale_authored_sets_do_not_show_after_the_em_key_is_deleted(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        db.add(AuditKeySet(chart_id=chart.id, name="Curated", mutations=[],
                           authored_by="T"))
        db.commit()

        assert client.get("/auditor/keys", params={"specialty": "E/M"}).json()["count"] == 1
        db.execute(text("DELETE FROM em_answer_keys WHERE chart_id = :c"), {"c": chart.id})
        db.commit()

        body = client.get("/auditor/keys", params={"specialty": "E/M"}).json()
        status = client.get("/auditor/keys/status", params={"specialty": "E/M"}).json()
        assert body["count"] == 0
        assert status["auditable"] == 0
        assert status["no_answer_key"] == 1

    def test_an_em_chart_without_a_key_stays_out_of_the_pool(self, client, db):
        from models import AuditBatch, BatchStatus
        make_chart(db, specialty="E/M")
        batch = AuditBatch(name="EM wave", specialty=Specialty.EM,
                           charts_per_auditor=1, created_by="t",
                           status=BatchStatus.OPEN)
        db.add(batch); db.commit()
        assert chart_pool(db, batch) == []

    def test_ed_profee_critical_care_boundary_is_stored_on_the_em_key(
            self, client, db):
        """
        ED Profee has no ordinary answer_keys row. The 99285/99291 marker must
        live with the E/M key, or the key screen appears to save while the
        generator never sees the flag.
        """
        chart = make_chart(db, specialty="ED Profee")
        db.commit()
        _em_key(db, chart.id, em_code="99285")

        r = client.post(f"/auditor/keys/chart/{chart.id}/cc-boundary",
                        json={"cc_boundary": "borderline",
                              "passphrase": "test-passphrase"})
        assert r.status_code == 200, r.text
        assert r.json()["cc_boundary"] == "borderline"

        key = audit_key_for(db, chart)
        assert key.cc_boundary == "borderline"
        body = client.get(f"/auditor/keys/chart/{chart.id}").json()
        assert body["cc_boundary"] == "borderline"

        _claim, gt = generate(key, Specialty.ED_PROFEE, seed=4,
                              cfg=_only("cc_boundary"), budget=1,
                              cc_boundary=key.cc_boundary)
        assert gt and gt[0]["kind"] == "cc_boundary"

    def test_an_authored_mdm_version_is_playable(self, client, db):
        """
        Auto plantings already emit MDM findings. A trainer-authored version
        must use the same shape or E/M curation is code-only while scoring is
        MDM-aware.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, risk="Moderate")

        r = client.post(f"/auditor/keys/chart/{chart.id}", json={
            "name": "Risk level judgement",
            "authored_by": "T",
            "passphrase": "test-passphrase",
            "mutations": [{
                "section": "MDM", "action": "Revise", "field": "risk",
                "line": 0, "claim_value": "Low",
                "correct_value": "Moderate",
            }],
        })
        assert r.status_code == 200, r.text

        key_set = db.query(AuditKeySet).filter(AuditKeySet.chart_id == chart.id).first()
        from services.audit_allocation import apply_manual_set
        claim, truth = apply_manual_set(audit_key_for(db, chart), key_set)
        assert claim["mdm"]["risk"] == "Low"
        assert truth[0]["section"] == "MDM"
        assert truth[0]["action"] == "Revise"
        assert truth[0]["field"] == "risk"
        assert truth[0]["claim_value"] == "Low"
        assert truth[0]["correct_value"] == "Moderate"


class TestTheForm:
    @pytest.mark.parametrize("specialty", [Sp.EM, Sp.ED_PROFEE])
    def test_mdm_is_three_levels_and_revise_only(self, specialty):
        """
        An encounter has one COPA, one Data Review and one Risk. They can be
        wrong; they cannot be added or removed — exactly like PDx.
        """
        sections = {s["key"]: s for s in form_spec(specialty)["sections"]}
        assert sections["MDM"]["fields"] == ["copa", "dr", "risk"]
        assert sections["MDM"]["actions"] == ["Revise"]

    def test_the_element_ticks_are_not_on_the_form(self):
        """
        Twenty-six attestations is a different job from reviewing a claim, and
        it is where the variable count explodes.
        """
        fields = {f for s in form_spec(Sp.EM)["sections"] for f in s["fields"]}
        assert not any(f.startswith("copa_") or f.startswith("risk_")
                       for f in fields)


class TestTheMdmShiftPlanting:
    def test_it_moves_one_level(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        key = audit_key_for(db, chart)
        claim, gt = generate(key, Specialty.EM, seed=3, cfg=_only("mdm_shift"),
                             budget=1)
        assert gt and gt[0]["section"] == "MDM"
        assert gt[0]["action"] == "Revise"
        assert gt[0]["field"] in ("copa", "dr", "risk")
        assert claim["mdm"][gt[0]["field"]] == gt[0]["claim_value"]

    def test_a_shift_that_does_not_move_the_code_is_not_revenue_impacting(
            self, client, db):
        """
        Two of three components carry the level, so one shifted element very
        often changes nothing. Calling that revenue-impacting would inflate
        every revenue figure the module reports — and an auditor who spots it
        without touching the code is exactly right.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, copa="Moderate", dr="Moderate", risk="Moderate")
        key = audit_key_for(db, chart)
        for seed in range(15):
            _claim, gt = generate(key, Specialty.EM, seed=seed,
                                  cfg=_only("mdm_shift"), budget=1)
            if not gt:
                continue
            # Moderate/Moderate/± leaves the second-lowest at Moderate.
            assert gt[0]["moves_em_level"] is False
            assert gt[0]["revenue_impacting"] is False

    def test_a_shift_that_moves_the_code_is_revenue_impacting(self, client, db):
        """Moderate/Low/Moderate: dropping Risk to Low takes the level down."""
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, copa="Moderate", dr="Low", risk="Moderate",
                overridden=("risk",))
        key = audit_key_for(db, chart)
        moved = [g for seed in range(30)
                 for g in generate(key, Specialty.EM, seed=seed,
                                   cfg=_only("mdm_shift"), budget=1)[1]
                 if g["moves_em_level"]]
        assert moved, "no shift ever moved the level on a chart where one should"
        assert all(g["revenue_impacting"] for g in moved)

    def test_the_direction_is_recorded(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        key = audit_key_for(db, chart)
        seen = {g["level_direction"] for seed in range(40)
                for g in generate(key, Specialty.EM, seed=seed,
                                  cfg=_only("mdm_shift"), budget=1)[1]}
        assert seen == {"up", "down"}

    def test_it_prefers_a_level_the_trainer_overrode(self, client, db):
        """
        A trainer who overrode the derivation read the record and disagreed
        with the table, so the level is a genuine judgement call there. Where
        they accepted it, shifting is closer to arithmetic.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, overridden=("dr",))
        key = audit_key_for(db, chart)
        fields = {g["field"] for seed in range(30)
                  for g in generate(key, Specialty.EM, seed=seed,
                                    cfg=_only("mdm_shift"), budget=1)[1]}
        assert fields == {"dr"}

    def test_the_claim_never_says_which_levels_were_overridden(self, client, db):
        """
        The claim is what the AUDITOR sees. "This one was a judgement call" is
        a hint they have not earned — it would point straight at the planting.
        """
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        key = audit_key_for(db, chart)
        claim, _gt = generate(key, Specialty.EM, seed=1,
                              cfg=_only("mdm_shift"), budget=1)
        assert "mdm_overridden" not in claim
        assert set(claim["mdm"]) == {"copa", "dr", "risk"}

    def test_a_key_with_no_levels_cannot_draw_it(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, copa="", dr="", risk="")
        key = audit_key_for(db, chart)
        _claim, gt = generate(key, Specialty.EM, seed=1,
                              cfg=_only("mdm_shift"), budget=1)
        assert gt == []


class TestNothingChangesUntilTurnedOn:
    def test_mdm_shift_defaults_to_zero(self):
        assert MutationConfig().mix_mdm_shift == 0

    def test_a_default_config_never_shifts_a_level(self, client, db):
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id)
        key = audit_key_for(db, chart)
        kinds = {g["kind"] for seed in range(30)
                 for g in generate(key, Specialty.EM, seed=seed,
                                   cfg=MutationConfig(), budget=2)[1]}
        assert "mdm_shift" not in kinds


class TestTheMdmVocabularyIsServed:
    """
    The four levels are sent with the form, not restated in the frontend.

    A free-text MDM box collects "Mod", "moderate" and "MODERATE" as three
    different answers, none of which the scorer matches; a hardcoded list in
    the UI is the same failure one release later, once only one side is edited.
    """

    def test_every_mdm_field_carries_its_levels(self):
        section = {s["key"]: s for s in form_spec(Sp.EM)["sections"]}["MDM"]
        for field in section["fields"]:
            assert section["field_values"][field] == [
                "Minimal", "Low", "Moderate", "High"]

    def test_the_levels_are_the_ones_the_key_stores(self, client, db):
        """The list an auditor picks from must contain the key's own value."""
        chart = make_chart(db, specialty="E/M")
        db.commit()
        _em_key(db, chart.id, copa="Moderate", dr="Low", risk="High")
        key = audit_key_for(db, chart)
        levels = {s["key"]: s for s in
                  form_spec(Sp.EM)["sections"]}["MDM"]["field_values"]["copa"]
        assert all(v in levels for v in key.mdm.values())

    def test_an_ordinary_section_serves_no_vocabulary(self):
        """Codes are typed, not chosen — the list is seventy thousand long."""
        section = {s["key"]: s for s in form_spec(Sp.IP_DRG)["sections"]}["PDx"]
        assert section["field_values"] == {}
