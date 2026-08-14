# Auditor Analytics Revamp

Shared design note for agents working on the Auditor module analytics.

## Direction

Auditor analytics should follow the PracticeLab analytics pattern for global filters, but should not copy its dense explanatory text.

Global filters:
- Date from
- Date to
- Specialty
- Apply / Clear
- Export current analytics workbook

Batch, auditor, and specialty should be analysis tabs or drilldown controls, not the primary top filter set.

## Terminology

Use training language in the UI:
- Audit Score
- Clean Chart Score
- Opportunity Chart Score
- Add Score
- Revise Score
- Delete Score
- PCS Score for IP
- Query Score where applicable

Avoid user-facing "accuracy" terminology in the analytics UI unless it is required to explain a methodology. Avoid "DRG Accuracy" as a headline for IP; show PCS Score instead. DRG-impacting misses may remain a secondary signal.

## Layout

Recommended tabs:
- Overview
- Auditors
- Batches
- Specialties
- Error Patterns
- Chart Signals
- Reports

Overview should show KPI cards, a score trend, clean vs opportunity comparison, and a small risk-signal area.

Auditors should be search-first. Search by name or Emp ID; once selected, show the auditor profile, trend, score split, specialties/batches, and PDF download actions. Keep only a capped "needs attention" list before search.

Batches should handle batch comparison and batch-level PDF/report downloads.

Specialties should compare specialties and show IP PCS Score instead of DRG Accuracy.

Error Patterns should show add/revise/delete, POA, PCS character, query, overcalls, missed errors, and detected-not-corrected.

Chart Signals should stay chart-level and controlled by search/caps.

Reports should centralize downloads so export actions do not feel scattered.

## UI Rules

- Remove long explanatory paragraphs from the live dashboard.
- Use short labels and optional tooltips.
- Use existing charting tools such as Recharts, with an auditor-specific color identity.
- Use fixed-height chart areas.
- All growing lists need search, caps, pagination, or "show more"; avoid "show all" for large datasets.
- Verify date and specialty filters apply to every tab.

## Color Direction

- Auditor primary: violet / magenta / indigo.
- Good / borderline / poor score: green / amber / red.
- Missed errors: red.
- Overcalls: orange.
- Clean score: blue.
- Opportunity score: violet.
- PCS/query: teal or slate.
