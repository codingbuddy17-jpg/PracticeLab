"""
The generator and the scorer have to agree on the shape they share.

Each is tested in isolation elsewhere. What neither can catch alone is a
mismatch between them: a field the generator writes and the scorer reads under
another name, a line number recorded against the pre-mutation claim, an Add
matched on something the auditor was never shown. Any of those makes a perfect
audit score less than 100, and the failure looks like a scoring bug rather than
a contract bug.

So this exercises the whole path — generate, audit it perfectly from the ground
truth, score — over many seeds and both chart shapes.
"""
import pytest

from models.charts import Specialty
from services.audit_mutation import generate
from services.audit_scoring import score_chart, score_session
from tests.test_audit_mutation import CORPUS, FakeKey, ip_key, op_key


def perfect_findings(ground_truth):
    """
    What a flawless auditor would record: the same action, in the same place,
    with the right correction. Deliberately built from the ground truth rather
    than hand-written, because the point is that the two shapes line up.
    """
    out = []
    for p in ground_truth:
        f = {"section": p["section"], "action": p["action"]}
        if p["action"] == "Add":
            f["correct_value"] = p["correct_value"]
        elif p["action"] == "Delete":
            f["line"] = p["line"]
            f["claim_value"] = p["claim_value"]
        else:
            f["line"] = p["line"]
            f["field"] = p.get("field", "code")
            f["correct_value"] = p["correct_value"]
        out.append(f)
    return out


CASES = [("IP-DRG", ip_key, Specialty.IP_DRG),
         ("Surgery", op_key, Specialty.SURGERY)]


@pytest.mark.parametrize("label,keyfn,spec", CASES)
@pytest.mark.parametrize("seed", range(60))
def test_a_perfect_audit_scores_100(label, keyfn, spec, seed):
    _claim, gt = generate(keyfn(), spec, seed=seed, corpus=CORPUS)
    s = score_chart(gt, perfect_findings(gt))
    assert s.audit_accuracy == 100.0, f"{label} seed {seed}: {gt}"
    assert s.over_calls == 0
    assert s.detected_not_corrected == 0


@pytest.mark.parametrize("label,keyfn,spec", CASES)
@pytest.mark.parametrize("seed", range(40))
def test_an_auditor_who_does_nothing_scores_zero(label, keyfn, spec, seed):
    _claim, gt = generate(keyfn(), spec, seed=seed, corpus=CORPUS)
    s = score_chart(gt, [])
    assert s.audit_accuracy == 0.0
    assert s.over_calls == 0        # inaction is not invention


@pytest.mark.parametrize("seed", range(40))
def test_every_planting_is_reachable_by_exactly_one_finding(seed):
    """
    If two plantings could be satisfied by the same finding, or one planting
    needed two, the component counts would not add up to what was planted.
    """
    _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
    s = score_chart(gt, perfect_findings(gt))
    assert s.add_found == s.add_planted
    assert s.revise_found == s.revise_planted
    assert s.delete_found == s.delete_planted
    assert s.opportunities == len(gt)


@pytest.mark.parametrize("seed", range(40))
def test_dropping_one_finding_costs_exactly_one_opportunity(seed):
    _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
    if len(gt) < 2:
        pytest.skip("needs at least two plantings")
    full = perfect_findings(gt)
    for drop in range(len(full)):
        partial = [f for i, f in enumerate(full) if i != drop]
        s = score_chart(gt, partial)
        assert s.opportunities == len(gt)
        assert (s.add_found + s.revise_found + s.delete_found) == len(gt) - 1
        assert s.over_calls == 0


@pytest.mark.parametrize("seed", range(30))
def test_flagging_everything_without_correcting_scores_near_zero(seed):
    """
    The claim that made a penalty structure unnecessary: an auditor marking
    every line wrong has no idea what the corrected codes are, so the
    correction requirement alone defeats them.
    """
    claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
    scattershot = []
    for i in range(len(claim["sdx"])):
        scattershot.append({"section": "SDx", "action": "Revise", "field": "code",
                            "line": i, "correct_value": "ZZZZ"})
    for i in range(len(claim["pcs"])):
        scattershot.append({"section": "PCS", "action": "Revise", "field": "code",
                            "line": i, "correct_value": "ZZZZZZZ"})
    s = score_chart(gt, scattershot)
    assert s.audit_accuracy <= 20.0, f"seed {seed}: {s.audit_accuracy}"


def test_a_mixed_session_rolls_up_coherently():
    """
    Half the pool clean, half planted — the shape a real allocation produces.
    Clean charts must carry the session, not break it.
    """
    charts = []
    for seed in range(6):
        _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        charts.append(score_chart(gt, perfect_findings(gt)))
    charts += [score_chart([], []) for _ in range(6)]

    s = score_session(charts)
    assert s.charts == 12
    assert s.clean_charts == 6 and s.opportunity_charts == 6
    assert s.audit_accuracy == 100.0
    assert s.clean_accuracy == 100.0 and s.opportunity_accuracy == 100.0
    assert s.add_found == s.add_planted
    assert s.opportunities > 0


def test_the_clean_half_cannot_hide_a_failing_detection_half():
    """
    Why the session view splits the two. A passive auditor scores full marks on
    restraint and nothing on detection; the headline alone would read as a
    mediocre pass rather than a total failure to find anything.
    """
    planted = []
    for seed in range(10):
        _claim, gt = generate(ip_key(), Specialty.IP_DRG, seed=seed, corpus=CORPUS)
        planted.append(score_chart(gt, []))
    s = score_session(planted + [score_chart([], []) for _ in range(10)])

    # Enough opportunities for the verdict to be given at all — a smaller
    # session withholds it, which is the floor doing its job.
    assert s.opportunities >= 20
    assert s.clean_accuracy == 100.0
    assert s.opportunity_accuracy == 0.0
    assert s.audit_accuracy == 50.0
    assert s.pass_fail == "FAIL"
