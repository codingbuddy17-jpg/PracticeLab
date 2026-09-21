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
  heading: HeadingLevel.HEADING_1, keepNext: true, keepLines: true, spacing: { before: 400, after: 170 },
  children: [new TextRun({ text: t, bold: true, size: 30, color: NAVY })],
});
const h2 = t => new Paragraph({
  heading: HeadingLevel.HEADING_2, keepNext: true, keepLines: true, spacing: { before: 300, after: 130 },
  children: [new TextRun({ text: t, bold: true, size: 24, color: NAVY })],
});
const h3 = t => new Paragraph({
  heading: HeadingLevel.HEADING_3, keepNext: true, keepLines: true, spacing: { before: 220, after: 110 },
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
    // A table followed by anything needs air below it; LibreOffice and Word
    // both set the next paragraph flush against the table's bottom border.
    if (el instanceof Table && next) {
      out.push(new Paragraph({ spacing: { after: 100, before: 0, line: 20 }, children: [] }));
    }
  });
  return out;
};

// ═══════════════════════════════════════════════════════════════════════════
// Three role guides from one set of chapters. Coder chapters appear in the
// Coder guide and the Complete guide word for word; trainer chapters in the
// Trainer guide and the Complete guide. Edit a chapter once and every guide
// that carries it changes with it.
// ═══════════════════════════════════════════════════════════════════════════

const img = (dir, name, caption) => figure(`${dir}/${name}.png`, 2880, 1900, caption);
const g  = (n, c) => img('guide_shots', n, c);
const u  = (n, c) => img('userguide_shots', n, c);
const an = (n, c) => img('analytics_shots', n, c);
let listInstance = 0;
const how = steps => {
  const inst = ++listInstance;
  return steps.map(t => new Paragraph({
    numbering: { reference: 's', level: 0, instance: inst }, spacing: { after: 85, line: 285 },
    children: [new TextRun({ text: t, size: 21 })],
  }));
};
const sections = rows => table(['Section', 'What it is for'], rows, [2600, 6760]);
const trouble = rows => table(['What you see', 'What it means', 'What to do'], rows, [3000, 3180, 3180]);
const tick = '✓', dash = '—';

// ── COVER ───────────────────────────────────────────────────────────────────
const cover = (title, audience, blurb) => [
  new Paragraph({ spacing: { before: 2200 }, children: [] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 110 },
    children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 340 },
    children: [new TextRun({ text: title, size: 30, color: ACCENT })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } }, children: [new TextRun('')] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
    children: [new TextRun({ text: blurb, size: 21, color: GREY, italics: true })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
    children: [new TextRun({ text: `For: ${audience}`, size: 20, color: GREY })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
    children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}`, size: 19, color: GREY })] }),
  brk(),
];

// ── ROLE GRID (shared) ──────────────────────────────────────────────────────
const roleGrid = () => [
  table(['Area', 'Coder', 'Trainer', 'Admin'], [
    ['Chart search and viewer', tick, tick, tick],
    ['Practice, audit and assessment sessions (own code)', tick, dash, dash],
    ['Report a chart problem', tick, tick, tick],
    ['Workspace and every trainer screen', dash, tick, tick],
    ['Chart Management, answer keys, batches, assessments, analytics', dash, tick, tick],
    ['Actions that need the master passphrase', dash, dash, tick],
  ], [5160, 1400, 1400, 1400]),
];

// ═══════════════════════════════ CODER CHAPTERS ═════════════════════════════
const coderIntro = () => [
  h1('Before you start'),
  p('PracticeLab is where you read clinical charts, practise coding them, and sit knowledge assessments. You do not need an account or a password. Your trainer gives you a code for each piece of assigned work.'),
  table(['You want to…', 'Go to', 'You need'], [
    ['Read a chart', 'The home screen', 'Nothing'],
    ['Code assigned charts', 'Practice (right-hand side)', 'An access code, e.g. PRC-ABCD1234'],
    ['Audit assigned charts', 'Practice (same place)', 'An audit code, e.g. AUD-ABCD1234'],
    ['Sit an assessment', 'Assessment (right-hand side)', 'An Assessment ID, e.g. ASM-X7K2M9QP'],
  ], [2700, 3000, 3660]),
  callout('Your code is personal', [
    'A code opens one person’s work. Do not share it and do not use anyone else’s. Your results are recorded against the name and employee ID the code was issued to.',
  ], 'info'),
  p('The first time you open PracticeLab it asks your name. That name is stored in your browser only. It labels what you do; it is not a login.'),
];

const coderCharts = () => [
  h1('Finding and reading charts'),
  ...g('coder_home', 'The home screen. Search sits at the top and Coding Resources below it; Recently Viewed appears once you have opened a few charts.'),
  sections([
    ['Search bar', 'Type a chart number (IP048) or a word. You can also leave it empty and search by specialty alone.'],
    ['Specialty and Category', 'Narrow the list. Category options follow the specialty you pick.'],
    ['Recently Viewed', 'The last charts this browser opened, for quick return.'],
    ['Coding Resources', 'Reference links your trainers publish — guidelines, code books, policies.'],
    ['Practice / Assessment', 'The two buttons on the right edge. This is where assigned work starts.'],
  ]),
  h2('How to find a chart'),
  ...how([
    'Type the chart number or a word, or pick a specialty.',
    'Press Search. Results list the chart number, specialty and category.',
    'Click a result to open it. Press the × in the search bar to clear the search and return to the home screen.',
  ]),
  ...g('coder_search', 'A search in progress. Resources move to a strip at the top while results are showing.'),

  h2('The chart viewer'),
  ...u('viewer_image', 'The viewer in Image mode — the pages exactly as scanned.'),
  table(['Control', 'What it does'], [
    ['Thumbnails (grid icon)', 'Show every page as a small preview; click one to jump to it.'],
    ['Image / Text', 'Switch between the scanned page and its extracted text. Text is easier to search and select.'],
    ['Search (magnifier, or Ctrl+F)', 'Find a word anywhere in the chart. Matches appear as page snippets with the word highlighted.'],
    ['Copy', 'Copies the chart number.'],
    ['Zoom in / out, Fit width, Fit page, Rotate', 'Adjust how the page sits on screen.'],
    ['Flag', 'Report a problem with the chart — see below.'],
    ['× or Esc', 'Close the viewer.'],
    ['← → keys', 'Previous and next page.'],
  ], [3200, 6160]),
  ...u('viewer_text', 'Text mode with a search running. Each snippet is a page with a match; the arrows step through them.'),
  h2('How to search inside a chart'),
  ...how([
    'Press Ctrl+F (or the magnifier) and type a word.',
    'Press Search. The count shows how many pages matched.',
    'Click a snippet, or use the up and down arrows, to move between matches.',
    'Press × to clear. If a chart says text is not available, it was scanned without readable text — use Image mode.',
  ]),
  h2('Reporting a problem with a chart'),
  p('Use the flag icon when a page is unreadable, a document is missing, or something on the page should not be there. Choose the problem, add a note if it helps, and send it. It goes straight to your trainers’ Feedback queue.'),
];

const coderPractice = () => [
  h1('Coding assigned charts (Practice)'),
  ...u('practice_entry', 'The Practice entry page. Coding codes and audit codes both work here.'),
  h2('How to start'),
  ...how([
    'On the home screen, click Practice on the right edge.',
    'Enter the access code your trainer gave you and press Open Practice Session.',
    'Your charts appear in the left panel. Click one to open it and its coding form.',
  ]),
  h2('The screen'),
  sections([
    ['Left panel', 'Your assigned charts and their status — Not started, In progress, Complete — plus any you flagged.'],
    ['Chart', 'The chart itself, with the same viewer controls as the home screen.'],
    ['Coding form', 'The fields for this chart. They depend on its specialty — see below.'],
    ['Save Progress / Submit All Charts', 'Save as you go; submit once, at the end, for everything.'],
  ]),
  h2('What the form asks for, by specialty'),
  table(['Specialty', 'You enter'], [
    ['IP-DRG (inpatient)', 'Principal diagnosis and secondary diagnoses, each with a POA indicator, and ICD-10-PCS procedures.'],
    ['ED Facility, ED Single Path, SDS, Surgery, Ancillary', 'First-listed and additional diagnoses, CPT procedures with modifiers, units and diagnosis pointers where the specialty uses them. No POA.'],
    ['ED Profee', 'Diagnoses, the professional ED level, and procedure CPTs if applicable.'],
    ['E/M', 'Patient type (new or established), the E/M code, and — when the visit is levelled by medical decision making — the three MDM sections: Problems (COPA), Data Review, and Risk.'],
    ['Edits, Denials', 'No codes. You write your review, research, recommended resolution and final rationale.'],
  ], [3000, 6360]),
  h3('POA indicators (inpatient only)'),
  table(['Value', 'Meaning'], [
    ['Y', 'Present at admission'], ['N', 'Not present at admission'],
    ['U', 'Documentation insufficient'], ['W', 'Clinically undetermined'], ['E', 'Exempt from POA reporting'],
  ], [1400, 7960]),
  h3('Entering codes'),
  bullet('Type codes with or without the dot or spaces — J18.9 and J189 are both accepted.'),
  bullet('As you type, suggestions and descriptions appear for ICD-10-CM, ICD-10-PCS and HCPCS. CPT codes have no descriptions: that code set is licensed separately and is not in the system.'),
  bullet('Diagnosis pointers are numbers (1, 2, 3, 4), up to four per line.'),
  h2('Flags, notes and queries'),
  bullet('Flag — mark a chart you are unsure about. Your trainer sees the flag.'),
  bullet('Notes — anything you want your trainer to know about the chart. Only trainers see it.'),
  bullet('Query — where the documentation is unclear, answer “Yes — send for query” and write the question you would put to the physician. The query is then required, and your trainer reviews it.'),
  h2('Saving and submitting'),
  ...how([
    'Work saves when you move to another chart. Press Save Progress any time to be sure.',
    'When every chart is done, press Submit All Charts.',
    'Review Before Submit lists each chart’s status and anything missing — for example a diagnosis without POA. Go back and fix it, or submit anyway.',
    'Confirm. Submission is final: you cannot change your codes afterwards.',
    'You see Submission Complete. If your trainer switched results on for this batch, your chart-by-chart feedback appears; otherwise your trainer shares it later.',
  ]),
  callout('Leaving part-way is safe', [
    'If you close the window before submitting, your work is kept. Open Practice with the same code later and carry on where you stopped.',
  ], 'info'),
];

const coderAudit = () => [
  h1('Auditing assigned charts (for auditors)'),
  p('Audit work is the reverse of coding. Each chart arrives already coded, as a claim. Some claims contain errors and some are correct. Your job is to find what is wrong and fix it — and to leave correct codes alone.'),
  h2('How to start'),
  ...how([
    'Click Practice on the home screen, enter your audit code (it begins AUD-) and press Open Practice Session.',
    'Pick a chart from the left panel. The claim is shown section by section beside the chart.',
  ]),
  h2('What you can do to a claim'),
  table(['Action', 'How', 'Use it when'], [
    ['Keep', 'Do nothing', 'The code is correct as it stands.'],
    ['Revise', 'Change the code or its POA, modifier or units in place', 'The code is on the claim but is wrong.'],
    ['Delete', 'Press Delete on the line (Undo reverses it)', 'The code should not be on the claim at all.'],
    ['Add', 'Press “Add a missing code”', 'A code the documentation supports is missing.'],
  ], [1400, 3900, 4060]),
  callout('What counts', [
    [{ t: 'A finding counts only when you both spot it and correct it. ', b: true }, { t: 'Deleting a line or changing a code without putting the right one in its place does not score. And changing a correct code costs you — restraint is measured as carefully as detection.' }],
  ]),
  h2('Queries, notes and submitting'),
  bullet('Physician Query — if the documentation is unclear, answer “Yes — needs a query” and write what you need clarified.'),
  bullet('Notes — optional, for your trainer.'),
  bullet('Save progress as you go; press Submit Audit when every chart is reviewed. Review Before Submit shows what is left, and submitting is final.'),
];

const coderAssessment = () => [
  h1('Sitting an assessment'),
  ...u('assessment_entry', 'The assessment entry page.'),
  h2('How to sit it'),
  ...how([
    'Click Assessment on the home screen, enter your Assessment ID and press Find My Assessment.',
    'Read the Ready to Begin screen — number of questions and time allowed. The clock starts when you press Start Assessment.',
    'Answer each question. Move freely between them from the question list; answers save as you go. Unanswered questions show as Skipped.',
    'Open Review & Submit to check what is left, then press Final Submit and confirm.',
  ]),
  callout('The clock does not stop', [
    'Closing the window does not pause it. When time runs out the paper submits itself with whatever you answered. A submitted paper cannot be reopened.',
    'An Assessment ID is valid for 8 hours from when it was issued.',
  ]),
  p('Afterwards you see either your result — score, pass mark, PASS or DID NOT PASS — or a message that your trainer will share it. Which one depends on how your trainer set up the assessment. You never see the questions again, because they are reused.'),
];

const coderGoodToKnow = () => [
  h1('Good to know'),
  h2('One device at a time'),
  p('A code can be open on only one browser at a time, so nobody else can work on your charts while you are. If you move computers, close PracticeLab on the first one before opening it on the second. If you forget, the hold releases itself after 90 minutes of inactivity, or your trainer can release it straight away.'),
  h2('When your batch closes'),
  p('When your trainer closes a batch, you can no longer save or submit work in it. You can still open your code to read your own results and feedback.'),
  h2('Troubleshooting'),
  trouble([
    ['“Access code not found”', 'The code was mistyped, or it is not a practice or audit code.', 'Check it character by character. Assessment IDs go in Assessment, not Practice.'],
    ['“This access code is already open on another device”', 'Your code is open in another browser or on another computer.', 'Close it there and try again, or ask your trainer to release it.'],
    ['“Could not save — check your connection”', 'The last save did not reach the server.', 'Check your connection and save again before leaving the chart.'],
    ['Cannot submit; batch closed', 'Your trainer has closed the batch.', 'Contact your trainer. Your feedback is still readable.'],
    ['“Some diagnoses are missing POA selection”', 'An inpatient diagnosis has no POA.', 'Choose a POA for each diagnosis.'],
    ['Chart text not available', 'The chart was scanned without readable text.', 'Use Image mode.'],
    ['“Assessment not found”', 'The Assessment ID is wrong or has expired.', 'Check it, or ask your trainer for a new one.'],
  ]),
];

const CODER = () => [coderIntro(), coderCharts(), coderPractice(), coderAudit(), coderAssessment(), coderGoodToKnow()]
  .flat();

// ══════════════════════════════ TRAINER CHAPTERS ════════════════════════════
const trainerIntro = (withAdmin) => [
  h1('Your role'),
  p('Trainers run the platform day to day: they manage the chart library and answer keys, run PracticeLab and audit batches, issue assessments, and read the results. Everything a trainer does happens in the Workspace, at /trainer.'),
  ...roleGrid(),
  withAdmin
    ? p('The last row — actions that need the master passphrase — is the Administrator’s. Those actions are listed in full in the Administrator chapters of this guide.')
    : callout('Some actions need an Administrator', [
        'A small set of actions ask for the master passphrase: anything permanent, anything that changes a finished record, scoring changes that affect everyone, and bulk exports of answers. They are listed in the final chapter of this guide. If you need one done, ask an Administrator.',
      ], 'info'),
];

const trainerWorkspace = () => [
  h1('The Workspace'),
  ...g('trainer_home', 'The Workspace. Each module card opens its area; the tiles beside it are live counts.'),
  sections([
    ['Chart Management', 'The chart library: upload, manage, reports, analytics, feedback.'],
    ['PracticeLab', 'Coding batches, answer keys, scoring and analytics.'],
    ['PracticeLab — Auditor', 'Audit batches, audit keys, audit scoring and analytics.'],
    ['Assessments', 'The question bank, paper generation, sessions and analytics.'],
  ]),
  p('The tiles are worth a glance each morning: open feedback, charts without keys, open batches and the current pass rates are all here.'),
];

const trainerCharts = () => [
  h1('Chart Management'),
  ...g('chart_management', 'The Chart Management hub.'),
  sections([
    ['Upload Charts', 'Add charts. Numbers (IP001, SURG014) are assigned automatically per specialty.'],
    ['Manage Charts', 'Search, edit details, retire and restore, add or replace pages.'],
    ['Reports', 'Filter the library and export it to Excel.'],
    ['Analytics', 'Charts by specialty, most and least viewed.'],
    ['Feedback', 'Problems coders have reported, and their resolution.'],
  ]),
  h2('How to upload charts'),
  ...how([
    'Upload Charts → drag in PDFs or images (several at once is fine).',
    'Set specialty, category and difficulty for each.',
    'Preview to see the numbers that will be assigned, then Upload.',
    'Add answer keys for the new charts — until then they can be read but not graded.',
  ]),
  ...g('manage_charts', 'Manage Charts. The status filter includes Retired.'),
  h2('How to look after a chart'),
  bullet('Edit details — open the chart in Manage Charts and change category, difficulty or rationale.'),
  bullet('Retire — withdraws the chart from coders and breaks saved links, but keeps it, its key and its history. Restore brings it back. Use this instead of deleting.'),
  bullet('Replace pages — for a corrected copy, typically when a page shows information it should not. The chart keeps its number, key and results. You give a reason, which is recorded.'),
  callout('Your own charts', [
    'You can edit, retire, restore and replace pages on charts YOU uploaded. Doing any of these to a colleague’s chart needs an Administrator.',
  ], 'info'),
  h2('How to handle feedback'),
  ...g('feedback', 'The Feedback queue.'),
  ...how(['Open Feedback and read the report.', 'Fix the chart if needed (often by replacing pages).', 'Resolve the item. It can be reopened if the problem returns.']),
  h2('Coding Resources'),
  p('The reference links coders see on the home screen. Add, reorder and remove them from Chart Management.'),
];

const trainerKeys = () => [
  h1('Answer keys'),
  p('An answer key is the correct coding for one chart. A chart without one cannot be graded and is left out of graded batches automatically.'),
  ...g('answer_keys', 'PracticeLab → Answer Keys. Filter by specialty and by whether a key exists.'),
  h2('Three ways to add a key'),
  table(['Method', 'Best for'], [
    ['Excel template — download, fill, upload', 'Many charts at once. The template is specific to each specialty; use the one for the charts you are keying.'],
    ['Key editor — type it in on screen', 'One chart, or a quick correction. Code descriptions appear as you type, which makes it a check as well as an entry form.'],
    ['E/M keys — separate template and screen', 'E/M and ED Profee charts, which are graded on medical decision making rather than code matching.'],
  ], [3600, 5760]),
  callout('Check the key before a batch uses it', [
    'A wrong key is worse than a wrong answer: it silently grades every coder against it. Use the descriptions in the key editor to confirm each code says what you meant.',
  ]),
  p('Adding keys is open to every trainer, and so is editing a key on a chart you uploaded. Editing an existing key on a colleague’s chart, replacing keys on upload, deleting a key and exporting all keys are Administrator actions.'),
];

const trainerPL = () => [
  h1('PracticeLab — running coding batches'),
  ...g('practicelab', 'PracticeLab batches. The newest group opens by default.'),
  sections([
    ['Batches', 'Create, allocate, monitor, grade and close.'],
    ['Answer Keys', 'The correct coding per chart.'],
    ['Analytics', 'Ten views of performance — see the Analytics Guide.'],
    ['Direct Assignment (button)', 'Give specific charts to specific people, outside a batch.'],
  ]),
  table(['', 'Batch', 'Direct assignment'], [
    ['Charts', 'Dealt by the system from a pool you filter', 'Picked by you'],
    ['Suits', 'A cohort working through a pool over cycles', 'One person, one or a few charts'],
    ['Analytics', 'Counted in cohort figures', 'Kept separate, and shown by the scope switch'],
  ], [1500, 4000, 3860]),
  h2('How to run a batch'),
  ...how([
    'New Batch — name, specialty, the filters that define the chart pool, charts per coder, and whether coders see their own results.',
    'Add coders (by name and employee ID, or from a file).',
    'Run Allocation. Each coder is dealt charts they have not seen, and gets an access code.',
    'Copy each access code and send it to its coder.',
    'Watch progress on the batch screen. Coders who joined late are included in the next allocation cycle.',
    'Grade what needs a person (below), then open View Results.',
    'Close the batch when the work is in. Scores become the record.',
  ]),
  ...g('batch_detail', 'A batch in progress: cycles, coders, access codes and per-coder actions.'),
  h2('What needs a trainer’s judgement'),
  table(['Item', 'Where', 'What you decide'], [
    ['DRG Review', 'Inpatient charts flagged by grading', 'Whether a coding error changed the DRG. Marking it an error sets that chart’s DRG component to zero.'],
    ['Query review', 'Charts where the coder raised a physician query', 'Whether the query was warranted, needs rewording, or was not warranted.'],
    ['Grade Cases', 'Edits and Denials (written responses)', 'A rubric score for each part — Acceptable (5), Needs Improvement (3), Not Acceptable (0).'],
  ], [1800, 3200, 4360]),
  h2('Other things on the batch screen'),
  bullet('Release — if a coder is locked out because their code is open on another device, release it and they can open it again straight away.'),
  bullet('Regrade — re-run grading for a session, for example after correcting its answer key.'),
  bullet('Notes — a running log for the batch.'),
  bullet('Results and Insights — per-coder and per-chart results, and what went wrong most. Exports to Excel and PDF.'),
  bullet('Accuracy (DPO) — per-area accuracy shown beside the score, if switched on for the batch. It is recorded either way, so switching it on later needs no regrade.'),
  bullet('Show results to coder — whether coders see chart-by-chart feedback when they submit. Off unless you turn it on.'),
  callout('Closing a batch', [
    'Closing ends submissions: coders can still read their feedback but cannot change or submit work. If some coders never started, the screen says so and offers “Close Unworked”. Reopening a closed batch, or force-closing one, is an Administrator action.',
  ], 'info'),
];

const trainerAuditor = () => [
  h1('PracticeLab — Auditor'),
  p('Audit batches work like coding batches, but the charts go out already coded with errors deliberately introduced, and the auditor finds and corrects them. Roughly a third of charts are left clean on purpose.'),
  ...g('auditor_batches', 'Audit batches.'),
  sections([
    ['Audit Batches', 'Create, allocate, monitor and close.'],
    ['Audit Keys', 'Error sets authored by a trainer for a specific chart, instead of letting the system generate them.'],
    ['Analytics', 'Audit Score, clean versus opportunity charts, what gets missed and what gets over-called.'],
    ['Score Config', 'Scoring weights and the mix of error types. Administrator only.'],
  ]),
  h2('How to run an audit batch'),
  ...how([
    'New Audit Batch — specialty, filters, charts per auditor, and the allocation mode: Automatic, Guided (you set how many clean and authored charts), or Hand-picked (you choose the charts).',
    'Add auditors and Run Allocation. The claims are built and fixed at this point.',
    'Send each auditor their code (AUD-…).',
    'Watch progress on the batch row, for example “4 of 12 scored”. Regenerate an assignment if one needs rebuilding.',
    'Close the batch when the work is in.',
  ]),
  callout('Two rules to keep', [
    'Never tell auditors which charts are clean — the screen deliberately looks identical either way.',
    '“Found” means found and corrected. Flagging alone scores nothing.',
  ]),
  p('Creating, editing and deleting audit error sets, and exporting them, currently need the master passphrase, so they are done by an Administrator.'),
];

const trainerAssessment = () => [
  h1('Assessments'),
  ...g('assessment', 'The Assessment module.'),
  sections([
    ['Pool Summary', 'How many questions the bank holds, by specialty and difficulty. Check before generating.'],
    ['Upload Questions', 'Add questions from the Excel template.'],
    ['Question Bank', 'Browse and edit questions. Administrator only.'],
    ['Generate', 'Build papers and issue them to coders.'],
    ['Sessions', 'Issued sittings, their IDs and status.'],
    ['History', 'Papers already generated, with reports.'],
    ['Analytics', 'Eight views of results — see the Analytics Guide.'],
  ]),
  h2('How to issue an assessment'),
  ...how([
    'Check Pool Summary: can the bank support the mix you want?',
    'Generate — choose the specialty mix, difficulty split, number of questions, time allowed and pass mark, whether coders see their score, and the coders.',
    'If the pool is short for any specialty, the screen lists the shortfall. Add questions, change the mix, or deliberately allow a short paper.',
    'Copy the Assessment IDs from Sessions and send them out. Each is valid for 8 hours.',
    'Read the results in Analytics, or download a batch report or per-coder reports from History.',
  ]),
  ...g('assessment_gen', 'Generate. Each coder gets their own paper and their own Assessment ID.'),
  bullet('Each coder’s paper is drawn separately, and the order of the answer options is shuffled per person.'),
  bullet('Recently used questions are held back, so a group tested twice does not get the same paper.'),
];

const trainerAnalytics = () => [
  h1('Analytics and exports'),
  p('PracticeLab, Auditor and Assessment each have an Analytics tab, and Chart Management has one more — 26 views in all. The PracticeLab Analytics Guide explains each one. Three rules matter before quoting any figure:'),
  bullet('A score (how well one chart was coded) and a pass rate (what share of charts or coders passed) are different numbers. Compare scores to the pass mark and pass rates to the 70% target.'),
  bullet('A batch is reported in coders; a coder is reported in charts. A coder passes by passing more than half their charts.'),
  bullet('NA means nothing to measure. It is not zero.'),
  ...g('pl_analytics', 'PracticeLab → Analytics.'),
  h2('Exports'),
  table(['Where', 'What'], [
    ['PracticeLab → Analytics', 'All results in the current filter (.xlsx)'],
    ['A batch → Results', 'The batch’s results (.xlsx, .pdf)'],
    ['Auditor → Analytics', 'The analytics workbook (.xlsx)'],
    ['Assessment → History / Analytics', 'Batch report (.pdf), all coder reports (.zip), coder matrix (.xlsx)'],
    ['Chart Management → Reports', 'The chart library (.xlsx)'],
  ], [3600, 5760]),
];

const trainerTrouble = () => [
  h1('Troubleshooting'),
  trouble([
    ['A coder says their code is “already open on another device”', 'It is open in another browser.', 'Release it from the batch screen.'],
    ['A chart cannot be added to a batch', 'It has no answer key.', 'Add a key, then allocate again.'],
    ['Allocation deals fewer charts than expected', 'The filtered pool is too small for the number of coders and cycles.', 'Widen the filters or add charts. The batch screen reports how distinct the draws were.'],
    ['“Passphrase required”', 'The action is an Administrator action.', 'Ask an Administrator.'],
    ['Generate refuses to build a paper', 'The bank lacks questions for part of the mix.', 'Read the shortfall list; add questions or change the mix.'],
    ['Code descriptions are blank', 'The reference code sets are not loaded in this environment.', 'Ask an Administrator to load them.'],
    ['A coder cannot submit', 'The batch is closed.', 'Expected. An Administrator can reopen it if the closure was a mistake.'],
  ]),
];

const TRAINER = (withAdmin) => [trainerIntro(withAdmin), trainerWorkspace(), trainerCharts(), trainerKeys(), trainerPL(), trainerAuditor(), trainerAssessment(), trainerAnalytics(), trainerTrouble()]
  .flat();

const adminOnlyList = () => [
  h1('Actions that need an Administrator'),
  p('These ask for the master passphrase. As a trainer, ask an Administrator when you need one.'),
  ...adminGridRows(false),
];

// ════════════════════════════ ADMINISTRATOR CHAPTERS ════════════════════════
const ADMIN_AREAS = [
  ['Chart Management', [
    ['Edit, retire or restore a chart you did not upload', 'Same as for your own; the passphrase is the ownership override.'],
    ['Add or replace pages on a chart you did not upload', 'The replaced images are deleted from storage. Give a reason.'],
    ['Purge a chart', 'Permanent. Refused for any chart with grading history — retire those instead.'],
  ]],
  ['Answer Keys', [
    ['Edit an existing key on a chart you did not upload', 'Changes how that chart is graded from now on.'],
    ['Replace keys on upload', 'Overwrites existing keys with the file’s contents.'],
    ['Upload E/M keys for charts you did not upload', 'As above, for E/M and ED Profee.'],
    ['Delete a key (standard or E/M)', 'The chart can no longer be graded.'],
    ['Export all keys', 'A complete copy of the answers. Treat the file as confidential.'],
  ]],
  ['PracticeLab', [
    ['Reopen a closed batch', 'Coders can submit again. The finished record becomes changeable.'],
    ['Force-close a batch', 'Closes it even with work outstanding. Give a reason.'],
    ['Scoring Config (standard and E/M)', 'Weights and pass marks per specialty type. Applies to future batches only.'],
    ['View all open batches', 'A cross-batch list for housekeeping.'],
    ['Code Set Maintenance', 'Load the CMS reference code sets (the database icon in PracticeLab).'],
  ]],
  ['Auditor', [
    ['Reopen or force-close an audit batch', 'As for PracticeLab.'],
    ['Audit Score Config', 'Scoring weights, over-call penalties, and the mix of error types planted. Applies to future audits only.'],
    ['Create, edit or delete audit error sets; set the CC boundary', 'Authoring the errors a chart carries.'],
    ['Export audit keys', 'Contains every planted error. Confidential.'],
  ]],
  ['Assessment', [
    ['Question Bank — view, edit, change status, delete', 'The bank is the answers, so browsing it is gated too.'],
    ['Export questions', 'Confidential.'],
    ['Override a coder’s response', 'Changes a submitted answer and therefore the score.'],
    ['Delete an assessment', 'Removes the paper and its sessions.'],
    ['Audit log', 'Who did what in the Assessment module.'],
  ]],
];

const adminGridRows = (detailed) => ADMIN_AREAS.flatMap(([area, acts]) => [
  h2(area),
  detailed
    ? table(['Action', 'What happens'], acts, [4000, 5360])
    : table(['Action', 'Coder', 'Trainer', 'Admin'], acts.map(([a]) => [a, dash, dash, tick]), [5760, 1200, 1200, 1200]),
]);

const adminIntro = () => [
  h1('The Administrator role'),
  p('An Administrator can do everything a trainer can, plus the actions that can’t be undone, that change a finished record, that change scoring for everyone, or that hand over answers in bulk. Today those actions are gated by a single shared master passphrase.'),
  callout('Look after the passphrase', [
    'It is one secret shared by everyone who holds the role, and the system cannot tell which Administrator used it. Keep the list of holders short, never paste it into chat or email, and change it whenever someone leaves the role or it may have been seen.',
    'It is currently sent in page addresses on some screens, so it can appear in browser history and server logs. Treat any shared machine as a place it may have been recorded.',
  ]),
  p('A proper sign-in with separate roles is designed (see PracticeLab — Access Control Design). This guide describes the system as it is today.'),
];

const adminActions = () => [
  h1('Administrator actions'),
  p('Every action below asks for the master passphrase. They are grouped by the screen they live on.'),
  ...adminGridRows(true),
];

const adminConfig = () => [
  h1('Scoring configuration'),
  ...g('scoring_config', 'PracticeLab Scoring Config.'),
  p('Scoring Config holds the weight of each component (principal diagnosis, secondary diagnoses, procedures, DRG, and so on) and the pass mark for each specialty type. E/M has its own config, and the Auditor module has another.'),
  bullet('Changes apply to future batches and audits only. Results already graded keep the scores they were given.'),
  bullet('Pass marks differ by specialty — for example 80% for inpatient and 90% for outpatient work. Every coloured figure in analytics uses the right one automatically.'),
  bullet('A single batch can carry its own scoring while it is open. Changing it after the batch closes rewrites a finished record, so do that only deliberately.'),
  h2('How to change scoring'),
  ...how(['Open Scoring Config (the gear on the PracticeLab batches screen, or Score Config in the Auditor module).', 'Change the weights or pass mark.', 'Save and enter the passphrase.', 'Tell trainers: batches created from now on use the new values.']),
];

const adminSystem = () => [
  h1('System upkeep'),
  h2('Reference code sets'),
  p('Code descriptions (ICD-10-CM, ICD-10-PCS, HCPCS and the CC/MCC list) come from CMS and are loaded once per environment. Nothing loads them automatically. Until they are loaded, descriptions are simply blank everywhere — and auditor procedure errors are generated less realistically, which affects scores, not just appearance.'),
  ...how(['Open PracticeLab and click the database icon in the header.', 'Code Set Maintenance shows what is loaded.', 'Start the load and enter the passphrase. It takes a few minutes.']),
  p('CPT descriptions are never loaded: that code set is licensed separately by the AMA.'),
  h2('Things to leave alone'),
  callout('Reset all data', [
    'The system has an API action that erases all PracticeLab data. It has no screen and should never be used on the live system. If your IT team can remove it before go-live, they should.',
  ]),
  h2('Routine checks'),
  bullet('Weekly: open feedback, charts without keys, batches open far longer than planned.'),
  bullet('After any code-set or scoring change: open one chart and one batch result and confirm they look right.'),
  bullet('When someone leaves the Administrator role: change the passphrase.'),
];

const reference = () => [
  h1('Reference'),
  h2('Specialties'),
  table(['Specialty', 'Graded on'], [
    ['IP-DRG', 'Principal and secondary diagnoses with POA, ICD-10-PCS procedures, and the DRG they produce.'],
    ['ED Facility, ED Single Path, SDS, Surgery, Ancillary', 'Diagnoses, CPT procedures, modifiers, units and pointers as the specialty requires.'],
    ['ED Profee', 'Diagnoses and the professional ED level (keyed in the E/M key screen).'],
    ['E/M', 'The E/M level and, where it applies, medical decision making — Problems, Data Review and Risk.'],
    ['Edits, Denials', 'Written responses, graded by rubric by a trainer.'],
  ], [3600, 5760]),
  h2('Glossary'),
  table(['Term', 'Meaning'], [
    ['Access code', 'What a coder or auditor enters to open assigned work. PRC- for coding, AUD- for auditing.'],
    ['Assessment ID', 'What a coder enters to sit an assessment. ASM-…, valid 8 hours.'],
    ['Allocation / cycle', 'One round of dealing charts to a batch. A batch can have several.'],
    ['Answer key', 'The correct coding for a chart.'],
    ['Clean / opportunity chart', 'Auditor terms: a chart with no planted errors, or with some. Never shown to auditors.'],
    ['DRG review', 'A trainer’s decision on whether an inpatient coding error changed the DRG.'],
    ['DPO', 'Per-area accuracy (diagnoses, procedures, DRG) shown beside the score.'],
    ['Direct assignment', 'Charts given to a person outside a batch.'],
    ['Retire', 'Withdraw a chart without deleting it. Reversible.'],
    ['NA', 'Nothing to measure. Not zero.'],
  ], [2600, 6760]),
];

// ═══════════════════════════════ ASSEMBLY ══════════════════════════════════
const about = (lines) => [h1('About this guide'), ...lines.map(l => p(l))];

const GUIDES = [
  {
    file: 'PracticeLab_User_Guide_Coder.docx',
    title: 'User Guide — Coders and Auditors',
    audience: 'Coders and auditors',
    blurb: 'Reading charts, coding and auditing assigned work, and sitting assessments',
    body: () => [
      ...about([
        'Everything you need to use PracticeLab as a coder or an auditor. You will not see the Workspace or any trainer screen, and nothing here needs a password.',
      ]),
      ...CODER(),
    ],
  },
  {
    file: 'PracticeLab_User_Guide_Trainer.docx',
    title: 'User Guide — Trainers',
    audience: 'Trainers',
    blurb: 'Running the chart library, batches, audits and assessments',
    body: () => [
      ...about([
        'How to run PracticeLab as a trainer. It covers every screen in the Workspace and the day-to-day work in each module.',
        'What coders see is covered in the Coder guide — worth reading once, because most questions coders ask are answered there.',
      ]),
      ...TRAINER(false),
      ...adminOnlyList(),
    ],
  },
  {
    file: 'PracticeLab_User_Guide_Complete.docx',
    title: 'User Guide — Complete',
    audience: 'Administrators, and anyone who needs the whole picture',
    blurb: 'Every role, every module, every action',
    body: () => [
      ...about([
        'The complete guide: what coders and auditors do, what trainers do, and what only Administrators do.',
        'Part A is the coder guide, Part B the trainer guide, and Part C the Administrator’s additions. The coder and trainer parts are identical to the separate guides, so a trainer or coder can be pointed at their part of this one.',
      ]),
      h2('Who can do what'), ...roleGrid(),
      partTitle('Part A', 'Coders and auditors'), ...CODER(),
      partTitle('Part B', 'Trainers'), ...TRAINER(true),
      partTitle('Part C', 'Administrators'), ...adminIntro(), ...adminActions(),
      ...adminConfig(), ...adminSystem(), ...reference(),
    ],
  },
];

function partTitle(label, name) {
  return [
    brk(),
    new Paragraph({ spacing: { before: 2600, after: 120 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: label, size: 26, color: ACCENT, bold: true })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: name, size: 44, color: NAVY, bold: true })] }),
    brk(),
  ];
}

for (const G of GUIDES) {
  const TITLE = `PracticeLab — ${G.title}`;
  const doc = new Document({
    creator: 'PracticeLab', title: TITLE, description: G.blurb,
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
      children: separate([...cover(G.title, G.audience, G.blurb), ...G.body().flat()]),
    }],
  });
  Packer.toBuffer(doc).then(b => { fs.writeFileSync(G.file, b); console.log(G.file, b.length); });
}
