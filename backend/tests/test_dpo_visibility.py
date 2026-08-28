"""
DPO figures are recorded whatever the batch flag says; the flag only shows them.

A trainer reported not seeing DPO anywhere. All three of their batches had
use_dpo false — but the figures had been computed and stored the whole time,
because grading computes them for every chart whose SPECIALTY supports it and
never consults the batch. The flag decides what the results endpoint returns.

That was unreachable: it could only be set while creating the batch, there was
no way to change it afterwards, and the Scoring Config screen carries a
similarly named setting that governs specialty defaults instead. So the numbers
existed, could not be seen, and nothing said they were there.
"""
from models import (AnswerKey, Batch, BatchStatus, Chart, ChartStatus,
                    Difficulty, GradingResult, PassFail, Specialty)

PASSPHRASE = "test-passphrase"


def _batch_with_dpo_figures(db, use_dpo=False, specialty=Specialty.IP_DRG):
    c = Chart(chart_number="IP960", specialty=specialty, category="C",
              difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE, uploaded_by="t")
    b = Batch(name="DPO", specialty=specialty, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=False, use_weighted=True,
              use_dpo=use_dpo, force_closed=False)
    db.add_all([c, b]); db.commit()
    db.add(GradingResult(batch_id=b.id, coder_name="Asha", chart_id=c.id,
                         specialty=specialty, pdx_score=20, sdx_score=15, pcs_score=20,
                         total_score=85, pass_fail=PassFail.PASS,
                         dpo_dx_accuracy=100.0, dpo_poa_accuracy=66.7,
                         dpo_proc_accuracy=100.0, dpo_overall_accuracy=85.7))
    db.commit()
    return b.id


def test_the_figures_are_masked_when_the_flag_is_off(client, db):
    bid = _batch_with_dpo_figures(db, use_dpo=False)
    d = client.get("/practicelab/batches/%d/results" % bid).json()
    assert d["use_dpo"] is False
    charts = [ch for c in d["coder_summaries"] for ch in c["charts"]]
    assert all(ch["dpo_overall_accuracy"] is None for ch in charts)


def test_but_the_response_admits_they_exist(client, db):
    """
    Without this the screen cannot tell an absent figure from a hidden one, and
    would have to claim there is nothing to show.
    """
    bid = _batch_with_dpo_figures(db, use_dpo=False)
    assert client.get("/practicelab/batches/%d/results" % bid).json()["dpo_available"] is True


def test_a_batch_with_no_figures_says_so(client, db):
    """The control — otherwise the offer would appear on every batch."""
    c = Chart(chart_number="IP961", specialty=Specialty.IP_DRG, category="C",
              difficulty=Difficulty.INTERMEDIATE, status=ChartStatus.ACTIVE, uploaded_by="t")
    b = Batch(name="None", specialty=Specialty.IP_DRG, status=BatchStatus.OPEN, created_by="t",
              charts_per_coder=1, is_direct_assignment=False, use_weighted=True,
              use_dpo=False, force_closed=False)
    db.add_all([c, b]); db.commit()
    db.add(GradingResult(batch_id=b.id, coder_name="Asha", chart_id=c.id,
                         specialty=Specialty.IP_DRG, pdx_score=20, sdx_score=20,
                         pcs_score=20, total_score=60, pass_fail=PassFail.FAIL))
    db.commit()
    assert client.get("/practicelab/batches/%d/results" % b.id).json()["dpo_available"] is False


def test_turning_it_on_reveals_the_stored_figures(client, db):
    """No re-grade: the numbers were there before the switch was touched."""
    bid = _batch_with_dpo_figures(db, use_dpo=False)
    r = client.patch("/practicelab/batches/%d/scoring" % bid,
                     json={"use_weighted": True, "use_dpo": True})
    assert r.status_code == 200, r.text
    assert r.json()["use_dpo"] is True

    d = client.get("/practicelab/batches/%d/results" % bid).json()
    assert d["use_dpo"] is True
    charts = [ch for c in d["coder_summaries"] for ch in c["charts"]]
    assert charts[0]["dpo_overall_accuracy"] == 85.7


def test_both_methods_cannot_be_switched_off(client, db):
    bid = _batch_with_dpo_figures(db)
    r = client.patch("/practicelab/batches/%d/scoring" % bid,
                     json={"use_weighted": False, "use_dpo": False})
    assert r.status_code == 400


def test_a_specialty_without_dpo_cannot_have_it_forced_on(client, db):
    """Creation applies this rule, so the two must not be able to disagree."""
    bid = _batch_with_dpo_figures(db, specialty=Specialty.EM)
    r = client.patch("/practicelab/batches/%d/scoring" % bid,
                     json={"use_weighted": False, "use_dpo": True})
    assert r.status_code == 200, r.text
    assert r.json()["use_dpo"] is False
    assert r.json()["use_weighted"] is True
    assert r.json()["dpo_supported"] is False
