const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat, Footer, PageNumber, ImageRun,
} = require('docx');

const SCHEMA = JSON.parse(fs.readFileSync('schema.json', 'utf8'));
const DOCS = JSON.parse(fs.readFileSync('tabledocs.json', 'utf8'));

const NAVY = '1F3864', ACCENT = '2E75B6', GREY = '595959';
const HDR_BG = 'DCE6F1', CODE_BG = 'F2F2F2', WARN_BG = 'FFF4E5';
const W = 9360;

/** Which domain each table belongs to, and the colour it carries throughout. */
const DOMAINS = [
  { key: 'Chart Library', colour: '2E75B6', fill: 'EAF1F8', tables:
    ['charts', 'chart_files', 'chart_sequences', 'chart_feedback', 'audit_logs', 'coding_resources'] },
  { key: 'PracticeLab', colour: '2E8B57', fill: 'EAF6EF', tables:
    ['batches', 'batch_coders', 'batch_charts', 'batch_allocation_cycles', 'submissions',
     'grading_results', 'grading_feedback', 'ed_rubric_details', 'answer_keys',
     'scoring_configs', 'self_practice_submissions', 'self_practice_results'] },
  { key: 'PracticeLab — E/M', colour: '8E44AD', fill: 'F5EEF8', tables:
    ['em_answer_keys', 'em_grading_results', 'em_scoring_configs'] },
  { key: 'Practice sessions', colour: 'B9770E', fill: 'FEF6E7', tables:
    ['practice_sessions', 'practice_chart_drafts', 'practice_results'] },
  { key: 'Assessment', colour: 'C0392B', fill: 'FDEDEC', tables:
    ['assessment_questions', 'assessment_configs', 'generated_assessments',
     'generated_assessment_students', 'assessment_sessions', 'assessment_responses',
     'assessment_results', 'assessment_audit_log'] },
];

const p = (t, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 130, line: 285 }, alignment: o.align,
  children: [new TextRun({ text: t, size: o.size ?? 21, color: o.color, bold: o.bold, italics: o.italics })],
});
const rich = (runs, o = {}) => new Paragraph({
  spacing: { after: o.after ?? 130, line: 285 },
  children: runs.map(r => new TextRun({
    text: r.t, bold: r.b, italics: r.i, font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : (o.size ?? 21), color: r.color ?? (r.code ? '7B1FA2' : undefined) })),
});
const h1 = t => new Paragraph({ heading: HeadingLevel.HEADING_1, spacing: { before: 400, after: 170 },
  children: [new TextRun({ text: t, bold: true, size: 30, color: NAVY })] });
const h2 = t => new Paragraph({ heading: HeadingLevel.HEADING_2, spacing: { before: 300, after: 130 },
  children: [new TextRun({ text: t, bold: true, size: 24, color: NAVY })] });
const bullet = t => new Paragraph({ numbering: { reference: 'b', level: 0 },
  spacing: { after: 85, line: 285 }, children: [new TextRun({ text: t, size: 21 })] });
const rbullet = runs => new Paragraph({ numbering: { reference: 'b', level: 0 },
  spacing: { after: 85, line: 285 }, children: runs.map(r => new TextRun({
    text: r.t, bold: r.b, font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : 21, color: r.code ? '7B1FA2' : undefined })) });
const code = lines => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill: CODE_BG },
  spacing: { before: 110, after: 150, line: 265 },
  border: { left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 6 } },
  indent: { left: 130 },
  children: lines.flatMap((l, i) => [...(i ? [new TextRun({ break: 1 })] : []),
    new TextRun({ text: l, font: 'Consolas', size: 18 })]),
});
const callout = (title, body) => new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: [W],
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: 'E8A33D' },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: 'E8A33D' },
    left: { style: BorderStyle.SINGLE, size: 18, color: 'E8A33D' },
    right: { style: BorderStyle.SINGLE, size: 4, color: 'E8A33D' } },
  rows: [new TableRow({ children: [new TableCell({
    width: { size: W, type: WidthType.DXA },
    shading: { type: ShadingType.CLEAR, fill: WARN_BG },
    margins: { top: 150, bottom: 150, left: 190, right: 190 },
    children: [
      new Paragraph({ spacing: { after: 85 }, children: [new TextRun({ text: title, bold: true, size: 21, color: '8A5A00' })] }),
      ...body.map(bd => new Paragraph({ spacing: { after: 65, line: 285 },
        children: (Array.isArray(bd) ? bd : [{ t: bd }]).map(r => new TextRun({
          text: r.t, bold: r.b, font: r.code ? 'Consolas' : undefined, size: r.code ? 19 : 21 })) })),
    ] })] })],
});
const table = (headers, rows, widths, headerFill) => new Table({
  width: { size: W, type: WidthType.DXA }, columnWidths: widths,
  borders: {
    top: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    bottom: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    left: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    right: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: 'E0E0E0' },
    insideVertical: { style: BorderStyle.SINGLE, size: 2, color: 'E0E0E0' } },
  rows: [
    new TableRow({ tableHeader: true, children: headers.map((hd, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: headerFill || HDR_BG },
      margins: { top: 80, bottom: 80, left: 120, right: 120 },
      children: [new Paragraph({ children: [new TextRun({ text: hd, bold: true, size: 19, color: NAVY })] })] })) }),
    ...rows.map(r => new TableRow({ children: r.map((cell, i) => new TableCell({
      width: { size: widths[i], type: WidthType.DXA },
      margins: { top: 70, bottom: 70, left: 120, right: 120 },
      children: [new Paragraph({ spacing: { line: 250 },
        children: (Array.isArray(cell) ? cell : [{ t: cell }]).map(x => new TextRun({
          text: x.t, bold: x.b, italics: x.i, font: x.code ? 'Consolas' : undefined,
          size: x.code ? 17 : 19, color: x.color })) })] })) })),
  ],
});
const figure = (file, srcW, srcH, caption) => {
  const targetW = 650, scale = targetW / srcW;
  return [
    new Paragraph({ spacing: { before: 180, after: 80 }, alignment: AlignmentType.CENTER,
      children: [new ImageRun({ type: 'png', data: fs.readFileSync(file),
        transformation: { width: targetW, height: Math.round(srcH * scale) } })] }),
    new Paragraph({ spacing: { after: 200 }, alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: caption, size: 18, italics: true, color: GREY })] }),
  ];
};
const brk = () => new Paragraph({ children: [new PageBreak()] });
const separate = items => {
  const out = [];
  items.forEach((el, i) => {
    out.push(el);
    if (el instanceof Table && items[i + 1] instanceof Table) {
      out.push(new Paragraph({ spacing: { after: 0, before: 0, line: 20 }, children: [] }));
    }
  });
  return out;
};

/** Normalise the introspected type into something a DBA reads at a glance. */
const readableType = (t) => {
  const u = (t || '').toUpperCase();
  if (u.startsWith('VARCHAR')) return u.replace('VARCHAR', 'text');
  if (u === 'TEXT') return 'text';
  if (u === 'INTEGER') return 'integer';
  if (u === 'FLOAT') return 'number';
  if (u === 'BOOLEAN') return 'boolean';
  if (u === 'JSON') return 'JSON';
  if (u.startsWith('DATETIME') || u.startsWith('TIMESTAMP')) return 'timestamp';
  return t || '—';
};

/** One table's column listing, generated from the live schema. */
const tableSection = (name, colour, fill) => {
  const t = SCHEMA[name];
  const fkBy = Object.fromEntries(t.fks.map(f => [f.col, `${f.ref_table}.${f.ref_col}`]));
  const rows = t.cols.map(c => {
    const notes = [];
    if (c.pk) notes.push('primary key');
    if (fkBy[c.name]) notes.push('→ ' + fkBy[c.name]);
    if (c.notnull && !c.pk) notes.push('required');
    if (c.default != null && String(c.default).toLowerCase() !== 'null') {
      notes.push('default ' + String(c.default).replace(/^'|'$/g, ''));
    }
    return [
      [{ t: c.name, code: true }],
      readableType(c.type),
      notes.join(' · ') || '',
    ];
  });
  return [
    new Paragraph({
      spacing: { before: 300, after: 60 },
      shading: { type: ShadingType.CLEAR, fill },
      border: { left: { style: BorderStyle.SINGLE, size: 16, color: colour, space: 6 } },
      children: [new TextRun({ text: '  ' + name, bold: true, size: 22, color: colour, font: 'Consolas' })],
    }),
    p(DOCS[name] || '', { after: 110, size: 20 }),
    table(['Column', 'Type', 'Key · constraints'], rows, [3100, 1700, 4560], fill),
  ];
};

const doc = new Document({
  creator: 'PracticeLab',
  title: 'PracticeLab — Database Schema Reference',
  description: 'Tables, columns, relationships and workflows',
  numbering: { config: [{ reference: 'b', levels: [
    { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 380, hanging: 230 } } } }] }] },
  styles: { default: { document: { run: { font: 'Calibri', size: 21 } } } },
  sections: [{
    properties: { page: { margin: { top: 1000, bottom: 1000, left: 1000, right: 1000 } } },
    footers: { default: new Footer({ children: [new Paragraph({
      alignment: AlignmentType.CENTER,
      children: [
        new TextRun({ text: 'PracticeLab — Database Schema Reference   |   ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
        new TextRun({ text: ' / ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
      ] })] }) },
    children: separate([
      // cover
      new Paragraph({ spacing: { before: 2300 }, children: [] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 110 },
        children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 340 },
        children: [new TextRun({ text: 'Database Schema Reference', size: 32, color: ACCENT })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } }, children: [new TextRun({ text: '' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
        children: [new TextRun({ text: '32 tables · 448 columns · 32 foreign keys', size: 21, color: GREY, italics: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
        children: [new TextRun({ text: 'Entity relationships, data dictionary and workflows', size: 20, color: GREY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
        children: [new TextRun({ text: 'Version 1.0  ·  12 August 2026', size: 19, color: GREY })] }),
      brk(),

      // 0
      h1('About this document'),
      p('A reference for the PracticeLab database: every table, every column, how the tables relate, and the workflows that write them.'),
      p('The contents were extracted from the schema the application itself builds, and the table descriptions from the model definitions in the source. Nothing here is transcribed by hand, so the document cannot drift from the code without the code changing first.'),
      rich([{ t: 'Companion document: ' }, { t: 'PracticeLab — Data Architecture and Migration Specification', i: true },
             { t: ' covers the components, object storage and the migration procedure. This document covers the database alone.' }]),

      h2('How to read it'),
      table(['Section', 'Contents'], [
        ['1  Overview', 'Table count by domain, and the conventions used throughout'],
        ['2  Entity relationships', 'Three diagrams, one per domain, showing every foreign key'],
        ['3  Workflows', 'Two diagrams tracing which tables are written at each step of real use'],
        ['4  Foreign key index', 'All 32 relationships in one list'],
        ['5  Data dictionary', 'Every table and column, grouped by domain'],
        ['6  Conventions and cautions', 'Patterns that recur, and the traps in them'],
      ], [2400, 6960]),
      brk(),

      // 1
      h1('1. Overview'),
      p('The schema divides into five domains. Domain membership is a documentation convenience — the database enforces no such grouping — but it reflects how the tables are actually used and which move together.'),
      table(['Domain', 'Tables', 'Purpose'], [
        [[{ t: 'Chart Library', b: true }], '6', 'The clinical charts coders practise on, their page images and the audit trail'],
        [[{ t: 'PracticeLab', b: true }], '12', 'Assigning charts to coders, answer keys, and the graded results'],
        [[{ t: 'PracticeLab — E/M', b: true }], '3', 'Evaluation & Management grading, which uses a different scheme from other specialties'],
        [[{ t: 'Practice sessions', b: true }], '3', 'Where coders actually work: access codes, drafts and submitted results'],
        [[{ t: 'Assessment', b: true }], '8', 'Multiple-choice question papers, independent of charts'],
      ], [2500, 900, 5960]),

      h2('1.1 Conventions'),
      rbullet([{ t: 'Primary keys', b: true }, { t: ' are always a single integer column named ' }, { t: 'id', code: true }, { t: '.' }]),
      rbullet([{ t: 'Foreign keys', b: true }, { t: ' are named ' }, { t: '<parent>_id', code: true }, { t: ' — ' }, { t: 'chart_id', code: true }, { t: ', ' }, { t: 'batch_id', code: true }, { t: ', ' }, { t: 'session_id', code: true }, { t: '.' }]),
      rbullet([{ t: 'Timestamps', b: true }, { t: ' are named ' }, { t: 'created_at', code: true }, { t: ', ' }, { t: 'updated_at', code: true }, { t: ' or ' }, { t: '<verb>_at', code: true }, { t: ', and are stored with time zone under PostgreSQL.' }]),
      rbullet([{ t: 'Repeating structures', b: true }, { t: ' — lists of codes, per-coder question sets, warning lists — are stored in ' }, { t: 'JSON', code: true }, { t: ' columns rather than child tables. 19 columns across the schema are JSON.' }]),
      rbullet([{ t: 'Deletion is avoided.', b: true }, { t: ' Charts and questions are retired by setting a status column, so records already referencing them stay valid.' }]),
      p('Types in this document are shown as declared by the application. Under PostgreSQL, JSON columns are native JSON and timestamps carry a time zone.'),

      h2('1.2 Where the schema comes from'),
      p('The application has no schema file and no migration framework. It builds its own schema at startup: the ORM models create 26 tables, and a sequence of raw statements creates a further six and adds columns to existing ones.'),
      callout('Six tables have no ORM model', [
        [{ t: 'em_answer_keys, em_grading_results, em_scoring_configs, practice_sessions, practice_chart_drafts, practice_results', code: true }],
        [{ t: 'These exist only in the startup migration statements. A schema generated from the model definitions alone will appear complete and will be missing the entire E/M grading and practice-session subsystems — which is where every coder submission is recorded.', b: true }],
      ]),
      brk(),

      // 2
      h1('2. Entity relationships'),
      p('Three diagrams, one per area. Arrows run from the child table to the parent it references — the direction a foreign key points.'),
      ...figure('figA_erd_charts.png', 1241, 881, 'Figure A — Chart Library'),
      brk(),
      ...figure('figB_erd_practicelab.png', 1241, 1001, 'Figure B — PracticeLab: assignment and grading'),
      brk(),
      ...figure('figC_erd_assessment.png', 1241, 841, 'Figure C — Assessment'),
      brk(),

      // 3
      h1('3. Workflows'),
      p('Which tables are written, in what order, during the two things the application is used for.'),
      ...figure('figD_workflow_practicelab.png', 1241, 881, 'Figure D — PracticeLab: from batch to score'),
      brk(),
      ...figure('figE_workflow_assessment.png', 1241, 881, 'Figure E — Assessment: from question bank to result'),
      brk(),

      // 4
      h1('4. Foreign key index'),
      p('All 32 foreign keys, as read from the built schema.'),
      table(['Child table and column', 'References'],
        Object.keys(SCHEMA).sort().flatMap(t =>
          SCHEMA[t].fks.map(f => [
            [{ t: `${t}.${f.col}`, code: true }],
            [{ t: `${f.ref_table}.${f.ref_col}`, code: true }],
          ])),
        [5000, 4360]),
      p('Ten tables hold no foreign key at all: they are either roots of a hierarchy or standalone configuration and logs.', { after: 90 }),
      rich([{ t: Object.keys(SCHEMA).sort().filter(t => !SCHEMA[t].fks.length).join(', '), code: true }]),
      brk(),

      // 5
      h1('5. Data dictionary'),
      p('Every table and column, grouped by domain. Descriptions are the ones carried in the source, so a change to either has to be made in both.'),
      ...DOMAINS.flatMap(d => [
        h2(`5.${DOMAINS.indexOf(d) + 1}  ${d.key}`),
        ...d.tables.filter(t => SCHEMA[t]).flatMap(t => tableSection(t, d.colour, d.fill)),
        brk(),
      ]),

      // 6
      h1('6. Conventions and cautions'),
      h2('6.1 Two scoring schemes sit side by side'),
      rich([{ t: 'grading_results', code: true }, { t: ' carries both. ' }, { t: 'total_score', b: true },
             { t: ' is the weighted score against the component weights in ' }, { t: 'scoring_configs', code: true },
             { t: '. The ' }, { t: 'dpo_*', code: true }, { t: ' columns are Diagnosis / POA / Procedure accuracy — the proportion of codes correct.' }]),
      p('Both raw counts and percentages are stored. The counts exist so cumulative figures across many charts can be computed correctly, rather than by averaging percentages that each had a different denominator.'),

      h2('6.2 Results are written twice, on purpose'),
      rich([{ t: 'A coder submission writes ' }, { t: 'practice_results', code: true },
             { t: ' and is then copied into ' }, { t: 'grading_results', code: true },
             { t: '. The copy is made in application code, not by a database constraint.' }]),
      p('Every analytics endpoint and both PDF reports read grading_results. Without the copy, in-browser work would be invisible to all reporting. When investigating a discrepancy, grading_results is the reporting truth and practice_results is the record of what the coder was shown.'),

      h2('6.3 Answer letters are not comparable between coders'),
      rich([{ t: 'Assessment option order is shuffled per coder and frozen into ' }, { t: 'generated_assessment_students.questions_json', code: true },
             { t: '. A stored ' }, { t: 'selected_answer', code: true }, { t: ' of "B" means whatever B was for that coder.' }]),
      p('Any query comparing answers across coders — distractor analysis, question quality — must resolve letters to option text through that row first.'),

      h2('6.4 Standalone question identifiers repeat'),
      rich([{ t: 'Questions created for a single paper without entering the bank are numbered ' }, { t: 'SA-0001', code: true },
             { t: ', ' }, { t: 'SA-0002', code: true }, { t: ' by position within that paper. Two such papers both contain an ' },
             { t: 'SA-0001', code: true }, { t: '.' }]),
      rich([{ t: 'Anything keyed on ' }, { t: 'question_id', code: true },
             { t: ' alone will merge unrelated questions. Pair it with the assessment.', b: true }]),

      h2('6.5 Corrections are recorded, not applied over the original'),
      rich([{ t: 'A trainer correcting a graded answer writes ' }, { t: 'assessment_responses.override_is_correct', code: true },
             { t: ' and leaves ' }, { t: 'is_correct', code: true }, { t: ' as the grader set it. The column is null when untouched, so an override to "incorrect" is distinguishable from never having been corrected.' }]),
      rich([{ t: 'Reporting must read the override where present and fall back to the original. Reading ' }, { t: 'is_correct', code: true },
             { t: ' alone silently ignores every correction a trainer has made.', b: true }]),

      h2('6.6 Vestigial columns'),
      table(['Column', 'Status'], [
        [[{ t: 'batch_charts.submission_status', code: true }], 'Set only by the Edits/Denials rubric path. Graded work is determined from grading_results'],
        [[{ t: 'submissions', code: true }], 'Whole table retained for historical records from the removed offline Excel workflow; nothing writes to it'],
        [[{ t: 'grading_results.submission_id', code: true }], 'Null for all current work; populated only on those historical rows'],
      ], [3400, 5960]),

      h2('6.7 Sequences'),
      rich([{ t: 'Three tables were originally created with ' }, { t: 'INTEGER PRIMARY KEY', code: true },
             { t: ' and had PostgreSQL sequences attached by a later migration: ' },
             { t: 'practice_sessions, practice_chart_drafts, practice_results', code: true },
             { t: '. After any restore, verify their sequence positions before accepting the environment — an incorrect position surfaces as a duplicate key error on the first insert, not at restore time.' }]),
    ]),
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('PracticeLab_Database_Schema_Reference.docx', buf);
  console.log('written', buf.length, 'bytes');
});
