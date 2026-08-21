from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend" / "src"


def read(path: str) -> str:
    return (FRONTEND / path).read_text()


def test_code_suggest_enter_contract_is_still_active():
    src = read("components/CodeSuggest.tsx")

    assert "onEnter?: (value: string) => void" in src
    assert "if (e.key === 'Enter' && onEnter)" in src
    assert "e.preventDefault(); onEnter(value)" in src


def test_coder_practice_repeated_code_rows_support_enter_to_continue():
    src = read("pages/PracticeSession.tsx")

    for helper in [
        "addSdxOnEnter",
        "addPcsOnEnter",
        "addCptOnEnter",
        "addEmDxOnEnter",
        "addEmCptOnEnter",
    ]:
        assert f"function {helper}" in src

    for call in [
        "onEnter={v => addSdxOnEnter(i, v)}",
        "onEnter={v => addPcsOnEnter(i, v)}",
        "onEnter={v => addCptOnEnter(i, v)}",
        "onEnter={v => addEmDxOnEnter(i, v)}",
        "onEnter={v => addEmCptOnEnter(i, v)}",
    ]:
        assert call in src

    assert "v.trim() && entry.sdx.length === 0" in src


def test_coder_answer_key_editors_keep_enter_row_entry():
    standard = read("pages/practicelab/AnswerKeyEditor.tsx")
    em = read("pages/practicelab/EMAnswerKeysView.tsx")

    for src in [standard, em]:
        assert "onEnter={v => addDxOnEnter(i, v)}" in src or "onEnter={v => addSdxOnEnter(i, v)}" in src
        assert "onEnter={v => addCptOnEnter(i, v)}" in src

    assert "onEnter={v => addPcsOnEnter(i, v)}" in standard
    assert "v.trim() && sdx.length === 0" in standard


def test_auditor_add_finding_fields_keep_enter_confirmation_and_poa_requirement():
    src = read("pages/AuditSession.tsx")

    assert "function confirmAddField" in src
    assert "data-add-field" in src
    assert "onEnter={() => confirmAddField(i, field)}" in src
    assert "if (spec.fields.includes('poa') && !String((f as any).poa || '').trim())" in src
    assert "if (spec.fields.includes('poa') && mine.some(f => f.action === 'Add' && !(f.poa || '').trim()))" in src


def test_drg_review_decision_buttons_are_wired_to_save_endpoint():
    review = read("pages/practicelab/DRGReviewView.tsx")
    batch_detail = read("pages/practicelab/BatchDetailView.tsx")

    assert "submitDRGDecision" in review
    assert "onClick={() => decide(r.result_id, false)}" in review
    assert "onClick={() => decide(r.result_id, true)}" in review

    assert "async function submitDrgReview" in batch_detail
    assert "onClick={() => submitDrgReview(reviewData.session_id, c.chart_id, true)}" in batch_detail
    assert "onClick={() => submitDrgReview(reviewData.session_id, c.chart_id, false)}" in batch_detail


def test_major_output_buttons_remain_connected_to_real_download_actions():
    practice = read("pages/practicelab/PLAnalyticsView.tsx")
    auditor = read("pages/auditor/AuditAnalytics.tsx")
    assessment_batch = read("pages/assessment/analytics/BatchAnalysisTab.tsx")
    assessment_coder = read("pages/assessment/analytics/CoderHistoryTab.tsx")

    for fn in [
        "downloadCoderReportPdf",
        "downloadCoderPerformanceXlsx",
        "downloadBatchReportPdf",
        "downloadBatchAnalyticsXlsx",
        "downloadCoderMatrixXlsx",
        "downloadTopicHeatmapXlsx",
        "downloadChartSignalsXlsx",
        "downloadErrorAnalysisXlsx",
    ]:
        assert fn in practice

    for fn in [
        "downloadAuditAnalytics",
        "downloadAuditAuditorReportPdf",
        "downloadAuditBatchReportPdf",
        "downloadAuditBatchResults",
    ]:
        assert fn in auditor

    assert "downloadAssessmentBatchReport" in assessment_batch
    assert "downloadAssessmentBatchCoderReportsZip" in assessment_batch
    assert "downloadAssessmentCoderReport" in assessment_coder
