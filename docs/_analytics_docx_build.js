// Dated when it is built, not when someone remembered to change the string.
// A regenerated document carrying an old date is worse than an undated one:
// the reader has no way to tell it was refreshed.
const BUILT = new Date().toLocaleDateString('en-GB',
  { day: 'numeric', month: 'long', year: 'numeric' });

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat, Footer, PageNumber, ImageRun,
} = require('docx');

const NAVY = '1F3864', ACCENT = '2E75B6', GREY = '595959', RED = 'B23A33';
const HDR_BG = 'DCE6F1', CODE_BG = 'F2F2F2', WARN_BG = 'FFF4E5';
const W = 9360;

const p = (t, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 130, line: 285 }, alignment: o.align, indent: o.indent,
  children: [new TextRun({ text: t, size: o.size ?? 21, color: o.color, bold: o.bold, italics: o.italics })],
});

const rich = (runs, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 130, line: 285 }, indent: o.indent,
  children: runs.map(r => new TextRun({
    text: r.t, bold: r.b, italics: r.i,
    font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : (o.size ?? 21),
    color: r.color ?? (r.code ? '7B1FA2' : undefined),
  })),
});

const h1 = t => new Paragraph({
  heading: HeadingLevel.HEADING_1, spacing: { before: 400, after: 170 },
  children: [new TextRun({ text: t, bold: true, size: 30, color: NAVY })],
});
const h2 = t => new Paragraph({
  heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 130 },
  children: [new TextRun({ text: t, bold: true, size: 24, color: NAVY })],
});
const h3 = t => new Paragraph({
  heading: HeadingLevel.HEADING_3, spacing: { before: 220, after: 110 },
  children: [new TextRun({ text: t, bold: true, size: 22, color: ACCENT })],
});

const bullet = (t, lvl = 0) => new Paragraph({
  numbering: { reference: 'b', level: lvl }, spacing: { after: 85, line: 285 },
  children: [new TextRun({ text: t, size: 21 })],
});
const rbullet = (runs, lvl = 0) => new Paragraph({
  numbering: { reference: 'b', level: lvl }, spacing: { after: 85, line: 285 },
  children: runs.map(r => new TextRun({
    text: r.t, bold: r.b, italics: r.i, font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : 21, color: r.color ?? (r.code ? '7B1FA2' : undefined),
  })),
});
const step = t => new Paragraph({
  numbering: { reference: 's', level: 0 }, spacing: { after: 85, line: 285 },
  children: [new TextRun({ text: t, size: 21 })],
});

const code = lines => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill: CODE_BG },
  spacing: { before: 110, after: 150, line: 265 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 6 } },
  indent: { left: 130 },
  children: lines.flatMap((l, i) => [
    ...(i ? [new TextRun({ break: 1 })] : []),
    new TextRun({ text: l, font: 'Consolas', size: 18 }),
  ]),
});

const callout = (title, body, tone = 'warn') => new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: [W],
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    left: { style: BorderStyle.SINGLE, size: 18, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    right: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
  },
  rows: [new TableRow({ children: [new TableCell({
    width: { size: W, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: tone === 'warn' ? WARN_BG : 'EEF4FB' },
    margins: { top: 150, bottom: 150, left: 190, right: 190 },
    children: [
      new Paragraph({ spacing: { after: 85 }, children: [new TextRun({
        text: title, bold: true, size: 21, color: tone === 'warn' ? '8A5A00' : NAVY })] }),
      ...body.map(bd => new Paragraph({
        spacing: { after: 65, line: 285 },
        children: (Array.isArray(bd) ? bd : [{ t: bd }]).map(r => new TextRun({
          text: r.t, bold: r.b, italics: r.i, font: r.code ? 'Consolas' : undefined,
          size: r.code ? 19 : 21 })),
      })),
    ],
  })] })],
});

const table = (headers, rows, widths) => new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: widths,
  borders: {
    top: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    bottom: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    left: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    right: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: 'D9D9D9' },
    insideVertical: { style: BorderStyle.SINGLE, size: 2, color: 'D9D9D9' },
  },
  rows: [
    new TableRow({ tableHeader: true, children: headers.map((hd, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: HDR_BG },
      margins: { top: 95, bottom: 95, left: 135, right: 135 },
      children: [new Paragraph({ children: [new TextRun({ text: hd, bold: true, size: 20, color: NAVY })] })],
    })) }),
    ...rows.map(r => new TableRow({ children: r.map((cell, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      margins: { top: 95, bottom: 95, left: 135, right: 135 },
      children: [new Paragraph({ children: (Array.isArray(cell) ? cell : [{ t: cell }]).map(x =>
        new TextRun({ text: x.t, bold: x.b, italics: x.i,
          font: x.code ? 'Consolas' : undefined, size: x.code ? 18 : 20, color: x.color })) })],
    })) })),
  ],
});

/** Full-width figure, scaled to the text column. */
const figure = (file, srcW, srcH, caption) => {
  const targetW = 620;                       // points across the A4 text column
  const scale = targetW / srcW;
  return [
    new Paragraph({
      spacing: { before: 200, after: 90 },
      alignment: AlignmentType.CENTER,
      children: [new ImageRun({
        type: 'png',
        data: fs.readFileSync(file),
        transformation: { width: targetW, height: Math.round(srcH * scale) },
      })],
    }),
    new Paragraph({
      spacing: { after: 220 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: caption, size: 18, italics: true, color: GREY })],
    }),
  ];
};


const brk = () => new Paragraph({ children: [new PageBreak()] });

/**
 * Word merges two tables that sit directly next to each other, so a callout
 * placed after a data table inherits its borders and reads as one object.
 * A zero-height paragraph between them keeps them apart.
 */
const separate = (items) => {
  const out = [];
  items.forEach((el, i) => {
    out.push(el);
    const next = items[i + 1];
    if (el instanceof Table && next instanceof Table) {
      out.push(new Paragraph({ spacing: { after: 0, before: 0, line: 20 }, children: [] }));
    }
  });
  return out;
};

const TITLE = 'PracticeLab — Analytics Guide';
const shot = (name, caption) => figure(`analytics_shots/${name}.png`, 2880, 1900, caption);
const tabTable = rows => table(['Tab', 'The question it answers'], rows, [1750, 7610]);

const doc = new Document({
  creator: 'PracticeLab',
  title: TITLE,
  description: 'Every analytics tab across PracticeLab, Auditor and Assessment',
  numbering: { config: [
    { reference: 'b', levels: [
      { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 380, hanging: 230 } } } },
      { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 740, hanging: 230 } } } },
    ] },
    { reference: 's', levels: [
      { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 380, hanging: 250 } } } },
    ] },
  ] },
  styles: { default: { document: { run: { font: 'Calibri', size: 21 } } } },
  sections: [{
    properties: { page: { margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ text: TITLE + '   |   ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
        new TextRun({ text: ' / ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
      ],
    })] }) },
    children: separate([

// ── cover ───────────────────────────────────────────────────────────────────
new Paragraph({ spacing: { before: 2200 }, children: [] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 110 },
  children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 340 },
  children: [new TextRun({ text: 'Analytics Guide', size: 30, color: ACCENT })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
  children: [new TextRun({ text: '' })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
  children: [new TextRun({ text: 'Twenty-six tabs across four modules — what each one answers, and how to read it', size: 21, color: GREY, italics: true })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
  children: [new TextRun({ text: 'Companion to the Feature & Workflow Guide', size: 20, color: GREY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
  children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}`, size: 19, color: GREY })] }),
brk(),

// ── 0. orientation ──────────────────────────────────────────────────────────
h1('About this guide'),
p('Analytics is the largest feature set in the application and the least self-explanatory. Three of the four modules carry their own analytics area, each with its own tab bar, and a fourth sits on the Chart Library. Twenty-six tabs in total.'),
p('The Feature & Workflow Guide covers how work is created and run. This one covers only what comes out of it: what each tab answers, what its figures mean, and — the part that causes real mistakes — the handful of rules that hold across all of them.'),

h2('The four analytics surfaces'),
table(['Surface', 'Where', 'Tabs', 'Unit of analysis'], [
  ['PracticeLab', 'PracticeLab → Analytics', '10', 'A graded chart'],
  ['Auditor', 'Auditor → Analytics', '7', 'A reviewed chart, and the errors planted in it'],
  ['Assessment', 'Assessments → Analytics', '8', 'An answered question'],
  ['Chart Library', 'Trainer → Analytics', '1', 'A chart, and how often it was opened'],
], [1900, 2500, 800, 4160]),
p('They are not variants of one screen. A PracticeLab figure is about coding accuracy against an answer key; an Auditor figure is about whether someone SPOTTED an error that was deliberately introduced; an Assessment figure is about a multiple-choice answer. The vocabulary overlaps — score, pass rate, specialty — and the quantities do not.'),

callout('Read chapter 1 before using any tab', [
  'The rules in the next chapter are not style notes. Each was written after a real defect in which a figure was read as something it was not — a share compared against a score threshold, a coder counted twice, a batch quietly excluded. Every one of them is still easy to make when reading the screens.',
], 'info'),
brk(),

// ── 1. rules ────────────────────────────────────────────────────────────────
h1('1. Rules that hold on every tab'),

h2('1.1  Three quantities look alike and must never be compared'),
table(['Quantity', 'What it is', 'Compare it against'], [
  [[{ t: 'Average score', b: true }], 'A per-chart SCORE — how well the coding matched the key', 'That specialty’s own pass mark (80% for IP, 90% for OP)'],
  [[{ t: 'Pass rate', b: true }], 'A population SHARE — how many charts, or how many coders, cleared the mark', 'The cohort target of 70%'],
  [[{ t: 'Errors per chart', b: true }], 'A RATE', 'Other rates only'],
], [1900, 3560, 3900]),
p('The colours on screen encode this distinction, which is why a specialty showing 85% of charts passing can be green while a specialty averaging 85% is red. They are different numbers with the same symbol after them.'),

h2('1.2  “Pass rate” means two different things, and the screen says which'),
p('A pass rate is either over charts or over coders, and the two disagree for the same batch:'),
bullet('Chart basis — passed charts ÷ total charts. Used on the analytics tabs.'),
bullet('Coder basis — passed coders ÷ total coders. Used on a batch’s Results screen.'),
rich([{ t: 'A coder passes by passing more than half their charts' }, { t: ' — a majority rule, not an average of their scores. One coder who passes 2 of 3 charts is 100% on the coder basis and 66.7% on the chart basis. Both are correct; they answer different questions.' }]),
p('The “Needs attention” banner deliberately reports coders — “only 1 of 3 coders passed” — because a training session is scheduled for people, not for charts.'),

h2('1.3  Pass marks are per specialty and come from the server'),
p('There is no single pass mark. Each specialty carries its own, set in Scoring Config, and every figure that is coloured takes the threshold from the data rather than from a fixed list. A row that spans specialties — a coder, a topic — has no single pass mark, and the screen says “mixed” rather than picking one.'),

h2('1.4  A coder is identified by employee ID'),
p('Grouping is by employee ID, falling back to the typed name only when no ID exists. This matters most on grids: name-keyed grouping produces two rows for one person, which reads as two coders with patchy attendance rather than as a duplicate.'),

h2('1.5  Scope — batches, direct assignments, or both'),
p('PracticeLab work arrives two ways: through a formal batch, or as a direct assignment to one person. The scope switch sits under the tab bar and applies to eight of the ten tabs.'),
table(['Setting', 'Shows'], [
  ['Batches', 'Formal batch work only — the default for team aggregates'],
  ['Direct Assignments', 'Ad-hoc assignments only'],
  ['Both', 'Everything'],
], [2200, 7160]),
rich([{ t: 'Where a view cannot honour the switch it says so, and says how much it is leaving out — the amber note reading ' }, { t: '“18 graded charts from direct assignments not shown”', i: true }, { t: '. Silent exclusion is the failure this guards against: a trainer once read “3 batches” on a screen while ten existed.' }]),

h2('1.6  Dates: created versus graded'),
p('Batch counts filter on when the batch was CREATED; grading figures filter on when the work was GRADED. Both dates are carried so the screen can label which it used — the strip under the scope switch says so explicitly. They are not interchangeable: filtering batches on result dates would make a batch half-appear whenever its results straddled the range boundary.'),

h2('1.7  NA is a real value and is not zero'),
p('Where there is nothing to measure, the figure reads NA. An auditor who was never given a chart with a deletable error has no Delete Score — not a Delete Score of zero. Rendering it as 0% would report a failure that never had the chance to happen.'),

h2('1.8  What the charts show, and why they are capped'),
bullet('Time series keep the most RECENT points — the question is where something is heading.'),
bullet('Ranked bars keep the EXTREMES at both ends, not the top n. Keeping only the top hides every struggling row the moment the list grows, which is the opposite of what the tab is for.'),
bullet('Batch columns cap at 25 with no “All” option. Past that, the date range is the right instrument — 200 columns is roughly thirteen screens sideways.'),
brk(),

// ── 2. PracticeLab ──────────────────────────────────────────────────────────
h1('2. PracticeLab analytics'),
p('Ten tabs. The unit is a graded chart: one coder’s attempt at one chart, scored against its answer key.'),
...shot('pl_overview', 'PracticeLab → Analytics → Overview. The date and specialty filter sits above the tab bar and applies to every tab; the scope switch sits below it.'),
tabTable([
  ['Overview', 'Headline figures for the whole team — batches open and closed, charts graded, pass rate, most and least practised specialty, and which specialties need attention. The pass rate trend runs across the most recent batches.'],
  ['Specialty', 'Performance by specialty, with a deep dive: the standing of one specialty against the others, its top categories, and the charts within it that are going worst.'],
  ['Batches', 'How each batch went, over time. Cumulative across all batches, so it answers whether the team is improving rather than how one cohort did.'],
  ['Coders', 'Coder Profile — one coder end to end: trend, specialty spread, and where they sit against the team.'],
  ['Topics', 'Topic Mastery — performance by chart topic rather than by specialty. This is the tab that names what to teach.'],
  ['Signals', 'Chart Signals — which charts are worth teaching with. Ranks charts by how much they discriminate, and flags the hardest as candidates for a session.'],
  ['Matrix', 'Coders against batches or specialties, as a grid. Sortable and searchable, paged on the server, with a below-target-only filter.'],
  ['Charts', 'Chart Audit — everything that happened on one chart, across every coder who attempted it.'],
  ['Errors', 'Error Analysis — which mistakes, by whom, and what to do about them. Covered below; it is the densest tab in the application.'],
  ['E/M', 'E/M levels and medical decision making — level direction, and where the reasoning goes wrong.'],
]),

h2('The Errors tab'),
p('Errors, not charts, are the unit here, and the tab is built around one idea: an error made by many coders on many charts is a curriculum item, while an error made once is not. Filters narrow by issue type (Missed, Wrong POA, Wrong Modifier, Over coded, Wrong Code) and by section (PDx, SDx, PCS, CPT).'),
...shot('pl_errors', 'The Errors tab. Error Insights at the top are generated from the data below them, and the PATTERN row at the foot separates team-wide gaps from one-off slips.'),
bullet('Error Insights — plain-language readings of the distribution: whether error density is even across specialties, which section dominates, and whether a few codes account for most of the total.'),
bullet('Errors per chart is the figure to compare between specialties. Total errors follows volume, so the specialty with the most practice will always appear worst.'),
bullet('What the errors are about — diagnosis chapter, CC/MCC status, and the six PCS axes (root operation, approach, body system, device, qualifier, body part). This is a share of errors, not a difficulty rate: a chapter appears because these charts use it, not only because it is hard.'),
bullet('Pattern chips — Team-wide, One chart, One coder, Scattered. Scattered items are hidden by default and counted, because they are noise for teaching purposes.'),
callout('CPT lines are not described', [
  'The application carries no CPT descriptions — the code set is licensed per user by the AMA and this repository is public. CPT errors are counted and shown as bare codes, and the footer says how many were left undescribed for that reason.',
]),

h2('The E/M tab'),
p('E/M is graded on the 2023 AMA medical-decision-making table rather than on code matching, so it gets a tab of its own. It reports level direction — upcoding against downcoding, which are the same error count and opposite problems — and splits the reasoning into COPA, Data Review and Risk, with a per-coder breakdown.'),
p('Level errors are near misses along a ladder — 99213 for 99214 — or the same level on the wrong ladder, which is the new-versus-established mistake. New-patient office, established office and ED are three separate ladders; critical care sits outside them all.'),
...shot('pl_em', 'The E/M tab. Level direction and the three reasoning areas are reported separately, because a shifted reasoning element usually does not move the level at all.'),
brk(),

// ── 3. Auditor ──────────────────────────────────────────────────────────────
h1('3. Auditor analytics'),
p('Seven tabs. The unit is a reviewed chart and the errors deliberately introduced into it. The question is never “did they code it right” but “did they SPOT what was wrong”.'),
...shot('au_overview', 'Auditor → Analytics → Overview. Clean vs Opportunity is the module’s central measurement: whether an auditor can leave a correct chart alone.'),

h2('The vocabulary'),
table(['Term', 'Meaning'], [
  [[{ t: 'Audit Score', b: true }], 'The weighted headline figure, and what the training verdict is based on.'],
  [[{ t: 'Error Detection Rate', b: true }], 'The share of introduced errors found AND corrected. Flagging alone earns nothing — an auditor who marks every line wrong knows nothing.'],
  [[{ t: 'Found, corrected wrongly', b: true }], 'Spotted the error, supplied the wrong replacement. Reported separately and never scored, because “found 4, corrected 2” and “found 2 of 4” both come to 50% and are different coaching conversations.'],
  [[{ t: 'Overcall', b: true }], 'Changed something that was already correct. The cost of over-eagerness, and the reason clean charts are measured.'],
  [[{ t: 'Clean chart', b: true }], 'A chart with nothing wrong in it. Scored on restraint — leaving it alone.'],
  [[{ t: 'Opportunity chart', b: true }], 'A chart carrying introduced errors. Scored on detection.'],
], [2100, 7260]),
rich([{ t: 'Clean and Opportunity are ', }, { t: 'trainer vocabulary only', b: true }, { t: '. The auditor’s own screens never use the words, and charts render identically whether or not they carry errors — a clean chart drawn differently would tell the auditor the answer before they looked.' }]),

...shot('au_review', 'Review Metrics. Clicking a score card focuses the detail panel beside it. Revise and Delete read NA here because no chart in scope carried a revisable or deletable error.'),
tabTable([
  ['Overview', 'Audit score, detection rate, clean and opportunity scores, pass rate, the weekly trend, and the three risk signals — missed errors, corrected wrongly, and overcalls.'],
  ['Review Metrics', 'The score broken out three ways: by ACTION (Add, Revise, Delete), by CODE FAMILY (PDx, SDx, PCS, CPT), and by ATTRIBUTE (POA, Modifier, Query). Clicking any card opens its detail below — found against introduced, with the miss count.'],
  ['Auditors', 'One auditor end to end. Search by name, then their profile, entries and standing.'],
  ['Batches', 'Batch performance, with the highest and lowest scoring batch called out.'],
  ['Specialties', 'Scores by specialty. Inpatient leads with PCS Score rather than DRG accuracy.'],
  ['Error Patterns', 'Which kinds of introduced error get missed. Splits system-generated errors from errors authored on real coder mistakes, and reports detection by section and action, PCS character, diagnosis chapter, and E/M level direction — including whether an MDM error actually moved the level or was reasoning only.'],
  ['Chart Signals', 'A chart-level matrix: which charts carry the highest miss risk, which carry the highest overcall risk, which are stable, and which need review. Searchable.'],
]),
callout('Scores, not accuracy', [
  'The auditor tabs say Score throughout — Audit Score, Clean Chart Score, PCS Score, Query Score — never Accuracy. The two are not synonyms here: a score carries the module’s weighting, and accuracy would imply a plain proportion.',
], 'info'),
brk(),

// ── 4. Assessment ───────────────────────────────────────────────────────────
h1('4. Assessment analytics'),
p('Eight tabs. The unit is an answered multiple-choice question. Nothing here involves a chart or an answer key.'),
...shot('as_overview', 'Assessments → Analytics → Overview. The period filter is specific to this module: preset windows, a custom range, and a batch selector.'),

h2('A different filter'),
p('The PracticeLab and Auditor tabs share a date-range and specialty filter. Assessment does not: it filters by PERIOD — All time, 30 days, 90 days, 12 months, or a custom range — plus a batch selector. Two tabs, Drill-down and Coder, carry no filter bar at all, because they are already scoped to one paper or one person.'),

tabTable([
  ['Overview', 'Total assessments, coders assessed, pass rate, average score, completion rate and auto-submit rate, with pass rate by assessment and the most-tested specialties.'],
  ['Batches', 'One batch: its assessments, pass rate, average, and a coder × topic accuracy matrix. Both report downloads live here.'],
  ['Drill-down', 'One assessment paper end to end — score distribution, min/max, completion, auto-submits, accuracy by topic, difficulty calibration, and every question ranked most-missed first. Coder results sort by score, time, name or employee ID.'],
  ['Specialty', 'Accuracy by specialty, with the best and weakest named and a per-specialty detail panel.'],
  ['Topic', 'The same by topic — strong topics, the weakest, and what needs review.'],
  ['Questions', 'Question Signals — which questions teach and which mislead. Each question is labelled Healthy, Too easy, Very hard, Misleading or Skipped. A misleading question is one strong coders get wrong, which is a defect in the question rather than in the cohort.'],
  ['Matrix', 'Coder × specialty grid with a gap count per coder. Specialty columns are chosen by hand. Exports to Excel.'],
  ['Coder', 'One coder’s assessment history — trend over time, pass rate, difficulty breakdown, and weakest topics.'],
]),
...shot('as_questions', 'Question Signals. Every question carries a label; Misleading is the one that matters, because it points at a defect in the question rather than in the cohort.'),
callout('Completion rate and auto-submit rate are different measurements', [
  'Completion counts sessions that were started and finished against sessions issued — the gap is tokens that lapsed unstarted. Auto-submit counts papers the timer submitted rather than the coder, as a share of papers submitted. A high auto-submit rate means the paper is too long for its clock; a low completion rate means tokens are not being used.',
], 'info'),
brk(),

// ── 5. Chart Library ────────────────────────────────────────────────────────
h1('5. Chart Library analytics'),
p('One screen, at Trainer → Analytics, and the only analytics in the application not about performance. It reports the library itself: charts by specialty, total views, and the most and least viewed charts.'),
...shot('lib_analytics', 'Trainer → Analytics. The only analytics screen not about performance — it reports the library itself.'),
p('Its use is curation rather than coaching. A chart with no views in a library that is otherwise well used is either mis-filed or not worth keeping, and the least-viewed list is the fastest way to find one.'),

h2('Getting figures out'),
table(['Surface', 'Export', 'Contains'], [
  ['PracticeLab', 'Export All Results (.xlsx)', 'Every graded result in the current filter'],
  ['PracticeLab — Errors', 'Export (.xlsx)', 'The error code table as filtered'],
  ['Auditor', 'Export Workbook (.xlsx)', 'The analytics set as a multi-sheet workbook'],
  ['Assessment — Batches', 'Batch Report (.pdf), All Coder Reports (.zip)', 'The batch report, and one PDF per coder'],
  ['Assessment — Matrix', 'Matrix (.xlsx)', 'The coder × specialty grid as shown'],
], [2200, 3000, 4160]),
p('Every workbook follows one house style — navy header row, frozen headers, fitted columns — so a sheet from one module opens looking like a sheet from another.'),
brk(),

// ── 6. how to ───────────────────────────────────────────────────────────────
h1('6. How to answer the usual questions'),
p('Which tab to open, for the questions that actually get asked.'),
table(['The question', 'Where to go'], [
  ['Is the team getting better?', 'PracticeLab → Batches. Cumulative across batches, so it shows direction rather than one cohort.'],
  ['What should the next training session cover?', 'PracticeLab → Errors, then the Team-wide pattern chip. Those are the errors several coders make on several charts.'],
  ['How is one coder doing?', 'PracticeLab → Coders for coding, Assessment → Coder for testing. Both include direct assignments.'],
  ['Which charts are worth teaching with?', 'PracticeLab → Signals. Ranks by how much a chart discriminates, not by how hard it is.'],
  ['Which specialty is in trouble?', 'PracticeLab → Overview. The Needs attention banner names it and says how many coders passed.'],
  ['Are auditors over-correcting?', 'Auditor → Overview. Compare Clean Chart Score against Opportunity Chart Score; a low clean score with a high opportunity score is over-eagerness.'],
  ['What kind of error gets missed?', 'Auditor → Error Patterns. Splits by section, action, PCS character and E/M direction.'],
  ['Is a question any good?', 'Assessment → Questions. Misleading means strong coders got it wrong.'],
  ['Why did so many papers auto-submit?', 'Assessment → Overview, then Drill-down for the paper. Auto-submit is a clock problem, not a knowledge problem.'],
  ['Which charts is nobody opening?', 'Trainer → Analytics, Least Viewed.'],
], [3000, 6360]),

h1('7. Notes for the team'),
h2('Where the figures come from'),
rich([{ t: 'Every figure on these tabs is an aggregate computed in SQL on the server, not in the browser. Changing the filter or the scope makes a round trip; the current numbers stay on screen with an ' }, { t: '“Updating…”', i: true }, { t: ' marker beside the switch rather than the page blanking. Results are cached per filter-and-scope combination, so returning to a view already seen is instant.' }]),
p('Filtering, ordering and paging all happen on the server, in that order. A search applied after paging would only ever filter the rows already loaded — which is a defect these endpoints were rewritten to avoid. Where a list is paged, three totals are reported separately: everything, everything matching the filter, and what is on this page.'),

h2('Limits worth knowing'),
bullet('Analytics needs graded work. A batch that has been allocated but not submitted contributes nothing, and specialties with no graded work are counted and named rather than silently dropped.'),
bullet('CPT is absent throughout — codes appear bare, and the answer-key checks decline to judge five-digit numeric codes rather than pretend to have checked them.'),
bullet('The Coder Matrix batch columns are closed formal batches by definition, so that grid cannot honour the scope switch. It says what it is excluding.'),
bullet('Reference code descriptions come from a CMS load that is run by hand. In an environment where it was never run, descriptions are simply absent — the screens degrade to silence rather than erroring, so this looks like a feature that does not exist. GET /codes/status reports what is loaded.'),

h2('This document'),
rich([{ t: 'Generated by ' }, { t: 'docs/_analytics_docx_build.js', code: true }, { t: '. Edit the builder, never the .docx — a hand edit is lost on the next build. Screenshots live in ' }, { t: 'docs/analytics_shots/', code: true }, { t: ' and are captured from the live system, so they carry real batch names and real figures.' }]),

    ]),
  }],
});

Packer.toBuffer(doc).then(b => {
  fs.writeFileSync('PracticeLab_Analytics_Guide.docx', b);
  console.log('written ' + b.length + ' bytes');
});
