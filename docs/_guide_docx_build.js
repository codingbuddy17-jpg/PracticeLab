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


const TITLE = 'PracticeLab — Feature & Workflow Guide';
const shot = (name, caption) => figure(`guide_shots/${name}.png`, 2880, 1900, caption);

/** Key sections / Features / How-to, the three blocks every module gets. */
const keySections = rows => table(['Section', 'What it is for'], rows, [2600, 6760]);
const howTo = steps => steps.map(t => step(t));

const doc = new Document({
  creator: 'PracticeLab',
  title: TITLE,
  description: 'What each module does, and how the work flows through it',
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
  children: [new TextRun({ text: 'Feature & Workflow Guide', size: 30, color: ACCENT })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
  children: [new TextRun({ text: '' })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
  children: [new TextRun({ text: 'What each module does · how the work flows through it', size: 21, color: GREY, italics: true })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
  children: [new TextRun({ text: 'Audience: the team taking on this application', size: 20, color: GREY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
  children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}`, size: 19, color: GREY })] }),
brk(),

// ── about ───────────────────────────────────────────────────────────────────
h1('About this guide'),
p('This is the functional companion to the migration documents. Those describe where the data lives and how to run the service; this one describes what the application DOES — screen by screen, with the workflow each module exists to support.'),
p('It is deliberately quick. Every module gets three things: the sections it contains, what its features are, and the order the work happens in. Where a detail matters more than it looks, it is called out; everything else is left to the screen, which is generally self-explanatory once the shape is known.'),
p('Screenshots are from the live system, so they show real charts and real batches rather than mock-ups.'),

h2('The four modules'),
table(['Module', 'Who uses it', 'What happens there'], [
  ['Chart Library', 'Trainer', 'Charts are uploaded, numbered, described and retired. Coders search and read them.'],
  ['PracticeLab', 'Trainer, then Coder', 'Charts are dealt to coders, coded in the browser, and graded automatically against an answer key.'],
  ['Auditor', 'Trainer, then Auditor', 'Charts arrive ALREADY coded with errors deliberately introduced. The auditor finds and corrects them.'],
  ['Assessment', 'Trainer, then Coder', 'Multiple-choice testing, independent of charts. Timed, from a question bank.'],
], [1900, 1700, 5760]),

h2('Terms used throughout'),
table(['Term', 'Meaning'], [
  [[{ t: 'Answer key', b: true }], 'The correct coding for one chart, uploaded from a spreadsheet or typed in. A chart without one can be read but not graded, and is excluded from graded batches automatically.'],
  [[{ t: 'Batch', b: true }], 'A cohort of coders working a pool of charts. Specialty, category and difficulty filters define the pool.'],
  [[{ t: 'Allocation cycle', b: true }], 'One run of the dealer over a batch. A batch can be allocated repeatedly; each cycle issues fresh charts and fresh access codes. Charts are dealt least-seen-first PER PERSON, so nobody repeats a chart while anything unseen remains.'],
  [[{ t: 'Access code', b: true }], 'What a coder is given instead of a login. It addresses one person’s sitting, and is the only credential the coder side has.'],
  [[{ t: 'Session', b: true }], 'One person’s sitting. Work saves as they go; submitting scores it and is final.'],
  [[{ t: 'DRG', b: true }], 'The inpatient grouping that determines payment. An error that changes the DRG matters far more than one that does not, so inpatient charts are checked for it separately.'],
  [[{ t: 'Introduced errors', b: true }], 'Auditor only. Generated from a weighted mix modelled on real audit findings, so what an auditor practises against resembles what they will meet.'],
], [1700, 7660]),
brk(),

// ── 1. Coder home ───────────────────────────────────────────────────────────
h1('1. Chart search — the coder’s home screen'),
p('Where a coder arrives. It is a library: search, open, read. No credential is needed to reach it, and the name entered on first visit is stored in the browser only — it labels the session, it does not identify anyone.'),
...shot('coder_home', 'The coder home screen before a search. Coding Resources sit at the foot of the page.'),
...shot('coder_search', 'The same screen with a search running. Resources have moved to a strip at the top, and the results carry the chart number, its specialty and its category — but not its difficulty.'),

h2('Key sections'),
keySections([
  ['Search bar', 'By chart number (IP048) or by keyword. Empty search with a filter set is also valid.'],
  ['Specialty / Category filters', 'Narrow the library. Category options follow the specialty chosen.'],
  ['Results', 'Chart number, specialty and category. Difficulty is deliberately NOT shown to coders — it exists so a trainer can match work to a level, and in front of the coder it either excuses a poor result or seeds doubt about a good one.'],
  ['Recently Viewed', 'The last ten charts this browser opened. Initial state only.'],
  ['Coding Resources', 'Reference links a trainer publishes — guidelines, manuals, internal policy.'],
  ['Side rail', 'Practice and Assessment — where a coder enters an access code to start assigned work.'],
]),

h2('Features'),
bullet('A chart open in the viewer has its own address, so it can be sent to a colleague or reloaded into place.'),
bullet('Page navigation, zoom, and text search WITHIN a chart, with matches highlighted.'),
bullet('Coders can flag a problem with a chart — an unreadable page, a missing document — which lands in the trainer’s Feedback queue.'),
rbullet([{ t: 'Retired charts disappear entirely: they leave search, and a saved link to one stops working. ' },
         { t: 'Retiring is the supported way to withdraw a chart', b: true }, { t: ' — it is reversible and the answer key is kept.' }]),

h2('How to'),
step('Type a chart number, or pick a specialty and press Search.'),
step('Click a result to open the viewer.'),
step('Use the page navigator at the foot, or the in-chart search to find a term.'),
step('To start assigned work instead, use Practice or Assessment on the right and enter the access code.'),
brk(),

// ── 2. Chart management ─────────────────────────────────────────────────────
h1('2. Chart Management'),
p('The trainer’s side of the library. Five separate destinations rather than tabs, because they are separate jobs rather than views of one thing.'),
...shot('chart_management', 'The Chart Management hub. Each card is a full screen; the counters are live.'),

h2('Key sections'),
keySections([
  ['Upload Charts', 'Bulk upload of PDFs or images. Chart numbers are assigned automatically from a per-specialty sequence (IP001, SURG014) — they are never typed.'],
  ['Manage Charts', 'Search, edit metadata, retire and restore, and replace a chart’s pages.'],
  ['Reports', 'Filter and export the library as a spreadsheet.'],
  ['Analytics', 'Most viewed, least viewed, and a count by specialty. A librarian’s view of the collection — it contains no coder and no score.'],
  ['Feedback', 'Problems coders have flagged, and their resolution.'],
]),
...shot('manage_charts', 'Manage Charts. Status filter includes Retired, which is where withdrawn charts remain visible to a trainer.'),

h2('Features'),
rbullet([{ t: 'Retire, not delete.', b: true }, { t: ' Retiring hides a chart from coders and breaks saved links, but keeps the record and the answer key so it can be restored. Permanent deletion is refused for any chart with grading history.' }]),
rbullet([{ t: 'Replace pages.', b: true }, { t: ' A chart can have its pages swapped for a corrected copy while keeping its number, its answer key and every grading result. Built for de-identification failures, where the correction changes what is VISIBLE rather than the clinical facts the key was written against. The old images are deleted from storage, which is the point. Passphrase-gated, and the reason is recorded.' }]),
bullet('Answer keys are uploaded per specialty from an Excel template, or typed in on the key editor. E/M and ED Profee use a separate template because they are graded on medical decision making rather than code matching.'),

h2('How to'),
step('Upload: drag files in, set specialty / category / difficulty, preview the numbers that will be assigned, confirm.'),
step('Correct a chart with PHI on a page: Manage Charts → the chart → Replace all pages, give a reason and the passphrase.'),
step('Withdraw a chart: Retire it. Find it again later with the status filter set to Retired.'),
brk(),

// ── 3. PracticeLab coder ────────────────────────────────────────────────────
h1('3. PracticeLab — the coder workflow'),
p('The core of the application. A trainer creates a batch, deals charts to coders, and the system grades what comes back against the answer key.'),
...shot('practicelab', 'PracticeLab batches. Rows group by age; the newest group opens by default. Direct assignments are marked and appear in the same list.'),

h2('Key sections'),
keySections([
  ['Batches', 'Create, allocate, monitor and close. Also where access codes are issued.'],
  ['Answer Keys', 'Upload or type the correct coding per chart. Charts without a key cannot be graded.'],
  ['Analytics', 'Performance across batches, coders, charts, categories and error types.'],
  ['Scoring Config', 'Component weights and pass marks per specialty type. Reached from the gear on the batches screen.'],
]),

h2('Two kinds of assignment'),
table(['', 'Batch', 'Direct assignment'], [
  ['Charts', 'Dealt by the allocator from a filtered pool', 'Picked by the trainer'],
  ['Use', 'A cohort working through a pool over cycles', 'A specific chart to a specific person'],
  ['Appears in', 'Cohort analytics', 'Its own scope — kept out of cohort figures'],
], [1500, 4000, 3860]),

...shot('batch_detail', 'A batch in progress. The step strip across the top is the workflow; below it are the allocation, the coders, and their access codes with per-coder actions.'),

h2('Features'),
rbullet([{ t: 'Allocation is per person and least-seen-first.', b: true }, { t: ' Nobody repeats a chart while anything unseen remains, and one coder exhausting the pool never blocks another. The screen reports how distinct the draws were, so a thin pool is visible rather than silent.' }]),
bullet('Coders work in the browser. Drafts save as they type and on a timer, so a closed tab costs nothing.'),
rbullet([{ t: 'Grading is automatic', b: true }, { t: ', against the key, with weights from the scoring config. Inpatient charts are additionally flagged where an error could have changed the DRG — those go to a trainer for a decision rather than being scored blind.' }]),
rbullet([{ t: 'Findings name the specific code.', b: true }, { t: ' A POA error compares the two POA values; over-coding names the surplus codes; codes carrying CC or MCC weight are marked, because those are what move the DRG.' }]),
bullet('Whether a coder sees their own score is a per-batch switch, off unless the trainer turns it on.'),
rbullet([{ t: 'A session is held to one browser', b: true }, { t: ' so the same access code cannot be worked from two machines. The hold releases itself after 90 minutes of silence, and a trainer can release it sooner.' }]),

h2('How to run a batch'),
step('New Batch — name it, choose the specialty, set the filters that define the chart pool, and add the coders.'),
step('Run Allocation — deals charts and creates one access code per coder. Repeat later for another cycle.'),
step('Distribute the access codes. Coders open Practice, enter the code, and work.'),
step('Resolve any DRG reviews the grading has flagged.'),
step('View Results and Insights; export to Excel or PDF if needed.'),
step('Close the batch. Scores become the record, and access codes stop accepting submissions — though a coder can still read their own feedback.'),
brk(),

// ── 4. Auditor ──────────────────────────────────────────────────────────────
h1('4. PracticeLab — Auditor'),
p('The inverse of the coder module, and the subtlest part of the application. Charts arrive already coded, with errors deliberately introduced. The auditor’s job is to find them and correct them — the real work of an auditing coder.'),
...shot('auditor_batches', 'Audit batches. Structurally the same as PracticeLab batches; the vocabulary and the scoring differ.'),

h2('Key sections'),
keySections([
  ['Audit Batches', 'Create, allocate, monitor, close. Auditors get access codes exactly as coders do.'],
  ['Audit Keys', 'Trainer-authored error sets for a specific chart — the alternative to letting the system generate them.'],
  ['Analytics', 'Audit Score, clean-chart performance, what auditors miss and what they over-call.'],
  ['Score Config', 'Per-action weights, over-call penalties, and the mix that decides which kinds of error get planted.'],
]),

callout('Roughly a third of charts are deliberately left clean', [
  'An auditor who flags problems everywhere is as wrong as one who finds nothing, so restraint is measured alongside detection.',
  [{ t: 'This is why a clean chart must be indistinguishable from a planted one on screen — a chart drawn differently tells the auditor the answer before they read it, and destroys the measurement the module exists for.', b: true }],
]),

h2('Features'),
rbullet([{ t: '“Found” means found AND corrected.', b: true }, { t: ' Flagging alone earns nothing. Detected-but-not-corrected is reported separately and never scored: “found 4, corrected 2” and “found 2 of 4” both come to 50% and are different conversations.' }]),
bullet('Findings are Add, Revise or Delete against specific claim lines — the shape of a real audit.'),
bullet('The form is served per specialty and per chart, so an E/M chart asks about medical decision making and an inpatient chart does not.'),
bullet('A chart can carry several authored versions; which one an auditor sees rotates on that chart’s own use count, so two auditors in one sitting do not compare notes usefully.'),
...shot('auditor_keys', 'Audit Keys — where a trainer authors a specific error set rather than letting the generator decide.'),

h2('How to run an audit batch'),
step('New Audit Batch — specialty, filters, charts per auditor, and the allocation mode (automatic, guided, or hand-picked).'),
step('Add auditors, then Run Allocation. Claims are built and frozen at this point.'),
step('Distribute access codes. Auditors open Audit, enter the code, and review each chart.'),
step('Watch progress on the batch row — “4 of 12 scored”.'),
step('Close the batch when the work is in. A batch with unsubmitted sessions can be force-closed with a reason.'),
brk(),

// ── 5. Assessment ───────────────────────────────────────────────────────────
h1('5. Assessment'),
p('Multiple-choice knowledge testing, independent of charts. A trainer builds a question bank, generates a paper with a chosen mix, and issues timed sessions.'),
...shot('assessment', 'The Assessment module. Seven sections, each a step in the same sequence.'),

h2('Key sections'),
keySections([
  ['Pool Summary', 'What the bank holds, by specialty and difficulty. Read this before generating — a paper cannot be built from questions that are not there.'],
  ['Upload Questions', 'Bulk import from an Excel template.'],
  ['Question Bank', 'Browse, edit and retire questions. Passphrase-gated, because the bank is the answers.'],
  ['Generate', 'Build a paper: specialty mix, difficulty distribution, question count, pass mark, and the coders it is for.'],
  ['Sessions', 'The issued sittings and their access codes.'],
  ['History', 'Papers already generated.'],
  ['Analytics', 'Pass rates, per-question signals, per-coder and per-topic performance.'],
]),
...shot('assessment_gen', 'Generate. The mix is set here; each coder receives their own paper and their own single-use code.'),

h2('Features'),
rbullet([{ t: 'Each coder gets their own paper.', b: true }, { t: ' Questions are drawn per person and frozen at generation, so two coders sitting the same assessment do not see the same paper in the same order.' }]),
rbullet([{ t: 'Sessions are timed and expire', b: true }, { t: ' — eight hours from issue. The paper auto-submits when time runs out, and that is recorded distinctly from a manual submission.' }]),
bullet('Each paper carries its own pass mark rather than a platform default, and every figure judged against it uses that paper’s own bar.'),
bullet('Whether a coder sees their score on submitting is a per-paper switch, off unless the trainer turns it on. What they see is the mark and the bar — never the questions, because the bank is reused.'),
bullet('Questions rotate: recently used ones are held back so a cohort sat twice does not get the same paper.'),

h2('How to issue an assessment'),
step('Check Pool Summary — confirm the bank can support the mix you intend.'),
step('Generate — set the specialty mix, difficulty split, question count, duration and pass mark, then add the coders.'),
step('Copy the access codes from Sessions and distribute them.'),
step('Coders open Take Assessment, enter the code, and sit the paper.'),
step('Read Analytics for the cohort, or export a per-coder report.'),
brk(),

// ── 6. Analytics ────────────────────────────────────────────────────────────
h1('6. Analytics, and how to read it'),
p('Each module carries its own analytics. Three conventions run across all of them and are worth knowing before the numbers are quoted anywhere.'),
...shot('pl_analytics', 'PracticeLab analytics. Sub-views are addressable, so a particular view can be linked to.'),

callout('Three rules the figures obey', [
  [{ t: 'A batch is reported in CODERS; a coder is reported in CHARTS.', b: true }, { t: ' A batch screen says how many coders passed. A coder’s own report says how many of their charts passed. The two genuinely differ — a coder who passes half their charts has not passed — so the label always names the population.' }],
  [{ t: 'Rates ship their denominator.', b: true }, { t: ' Audit accuracy averages chart scores; component accuracy pools findings. Which one is being shown is always stated.' }],
  [{ t: 'NA is not zero.', b: true }, { t: ' A figure with nothing to measure is shown as NA. A specialty that does not compute a metric has not scored zero on it.' }],
]),

h2('Accuracy (DPO)'),
rich([{ t: 'A supplementary per-area accuracy figure — diagnoses, procedures, DRG — reported beside the weighted grading score rather than instead of it. It is computed for every chart whose specialty supports it, but only DISPLAYED where the batch has it switched on. If the figures are there and the switch is off, the Results tab offers to turn it on; nothing is re-graded, because the numbers were already recorded.' }]),
brk(),

// ── 7. For the team taking this on ──────────────────────────────────────────
h1('7. Notes for the team taking this on'),

h2('7.1 Who can do what, today'),
callout('There is no authentication in the application', [
  'Coders and auditors hold an access code; trainers reach their screens by knowing the URL. A single shared passphrase gates the destructive operations — retire, delete, force-close, reopen, the question bank, and page replacement.',
  [{ t: 'A design for proper access control exists as a separate document and is a proposal, not a description. Read PracticeLab — Access Control Design before drawing conclusions about the current model.', b: true }],
]),

h2('7.2 What can be changed without touching code'),
p('More than is obvious. All of the following are held in the database and edited through the trainer screens:'),
bullet('Scoring weights and pass marks — per specialty type, for coders and auditors alike.'),
bullet('The assessment question bank, and each paper’s own pass mark.'),
bullet('Answer keys, standard and E/M.'),
bullet('The mix that decides which kinds of error the auditor generator plants.'),
bullet('Coding resources published to coders.'),
p('Changing any of these takes effect on the next batch. No deployment is involved.'),

h2('7.3 Reference code sets'),
rich([{ t: 'ICD-10-CM, ICD-10-PCS and HCPCS descriptions are loaded by a script that is run ONCE per environment and is not called automatically. Everything that reads them degrades to silence, so an environment where the load was never run looks identical to one where the feature does not exist — code descriptions simply render blank. ' }, { t: 'GET /codes/status', code: true }, { t: ' reports what is present.' }]),
rich([{ t: 'This is not only cosmetic: the auditor’s procedure mutation draws replacements from those tables, so without them a share of planted PCS errors are strings that are not codes.' }]),

h2('7.4 Where to go next'),
table(['Question', 'Document'], [
  ['Where does the data live, and how do we move it?', 'Data Architecture and Migration'],
  ['What is every table and column?', 'Database Schema Reference'],
  ['How do we run it?', 'Container Deployment Guide'],
  ['How should access be controlled?', 'Access Control Design (proposal)'],
], [4200, 5160]),

    ]),
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('PracticeLab_Feature_and_Workflow_Guide.docx', buf);
  console.log('written', buf.length, 'bytes');
});
