const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat, TableOfContents, Footer, PageNumber,
} = require('docx');

// ── palette ──────────────────────────────────────────────────────────────────
const NAVY = '1F3864';
const ACCENT = '2E75B6';
const GREY = '595959';
const RED = 'B23A33';
const HDR_BG = 'DCE6F1';
const CODE_BG = 'F2F2F2';
const WARN_BG = 'FFF4E5';
const TOTAL_W = 9360;          // A4 portrait usable width in DXA

// ── helpers ──────────────────────────────────────────────────────────────────
const p = (text, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 120, line: 280 },
  alignment: opts.align,
  indent: opts.indent,
  children: [new TextRun({
    text, size: opts.size ?? 21, color: opts.color, bold: opts.bold,
    italics: opts.italics, font: opts.font,
  })],
});

/** Paragraph built from [{t, b, i, code}] runs — for inline emphasis. */
const rich = (runs, opts = {}) => new Paragraph({
  spacing: { after: opts.after ?? 120, line: 280 },
  indent: opts.indent,
  children: runs.map(r => new TextRun({
    text: r.t,
    bold: r.b, italics: r.i,
    font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : (opts.size ?? 21),
    color: r.color ?? (r.code ? '9C27B0' : undefined),
  })),
});

const h1 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1,
  spacing: { before: 360, after: 160 },
  children: [new TextRun({ text, bold: true, size: 30, color: NAVY })],
});

const h2 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_2,
  spacing: { before: 280, after: 120 },
  children: [new TextRun({ text, bold: true, size: 24, color: NAVY })],
});

const h3 = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_3,
  spacing: { before: 200, after: 100 },
  children: [new TextRun({ text, bold: true, size: 22, color: ACCENT })],
});

const bullet = (text, level = 0) => new Paragraph({
  numbering: { reference: 'bullets', level },
  spacing: { after: 80, line: 280 },
  children: [new TextRun({ text, size: 21 })],
});

const richBullet = (runs, level = 0) => new Paragraph({
  numbering: { reference: 'bullets', level },
  spacing: { after: 80, line: 280 },
  children: runs.map(r => new TextRun({
    text: r.t, bold: r.b, italics: r.i,
    font: r.code ? 'Consolas' : undefined,
    size: r.code ? 19 : 21,
    color: r.color ?? (r.code ? '9C27B0' : undefined),
  })),
});

const numbered = (text, level = 0) => new Paragraph({
  numbering: { reference: 'steps', level },
  spacing: { after: 80, line: 280 },
  children: [new TextRun({ text, size: 21 })],
});

/** Monospace block, shaded, for commands and SQL. */
const code = (lines) => new Paragraph({
  shading: { type: ShadingType.CLEAR, fill: CODE_BG },
  spacing: { before: 100, after: 140, line: 260 },
  border: {
    left: { style: BorderStyle.SINGLE, size: 12, color: ACCENT, space: 6 },
  },
  indent: { left: 120 },
  children: lines.flatMap((l, i) => [
    ...(i ? [new TextRun({ break: 1 })] : []),
    new TextRun({ text: l, font: 'Consolas', size: 18 }),
  ]),
});

/** Callout box for the things that bite. */
const callout = (title, body, tone = 'warn') => new Table({
  width: { size: TOTAL_W, type: WidthType.DXA },
  columnWidths: [TOTAL_W],
  borders: {
    top: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    bottom: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    left: { style: BorderStyle.SINGLE, size: 18, color: tone === 'warn' ? 'E8A33D' : ACCENT },
    right: { style: BorderStyle.SINGLE, size: 4, color: tone === 'warn' ? 'E8A33D' : ACCENT },
  },
  rows: [new TableRow({
    children: [new TableCell({
      width: { size: TOTAL_W, type: WidthType.DXA },
      shading: { type: ShadingType.CLEAR, fill: tone === 'warn' ? WARN_BG : 'EEF4FB' },
      margins: { top: 140, bottom: 140, left: 180, right: 180 },
      children: [
        new Paragraph({
          spacing: { after: 80 },
          children: [new TextRun({ text: title, bold: true, size: 21, color: tone === 'warn' ? '8A5A00' : NAVY })],
        }),
        ...body.map(b => new Paragraph({
          spacing: { after: 60, line: 280 },
          children: (Array.isArray(b) ? b : [{ t: b }]).map(r => new TextRun({
            text: r.t, bold: r.b, italics: r.i,
            font: r.code ? 'Consolas' : undefined,
            size: r.code ? 19 : 21,
          })),
        })),
      ],
    })],
  })],
});

/** Table with a header row. widths must sum to TOTAL_W. */
const table = (headers, rows, widths) => new Table({
  width: { size: TOTAL_W, type: WidthType.DXA },
  columnWidths: widths,
  borders: {
    top: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    bottom: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    left: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    right: { style: BorderStyle.SINGLE, size: 2, color: 'BFBFBF' },
    insideHorizontal: { style: BorderStyle.SINGLE, size: 2, color: 'D9D9D9' },
    insideVertical: { style: BorderStyle.SINGLE, size: 2, color: 'D9D9D9' },
  },
  rows: [
    new TableRow({
      tableHeader: true,
      children: headers.map((hd, i) => new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        shading: { type: ShadingType.CLEAR, fill: HDR_BG },
        margins: { top: 90, bottom: 90, left: 130, right: 130 },
        children: [new Paragraph({
          children: [new TextRun({ text: hd, bold: true, size: 20, color: NAVY })],
        })],
      })),
    }),
    ...rows.map(r => new TableRow({
      children: r.map((cell, i) => new TableCell({
        width: { size: widths[i], type: WidthType.DXA },
        margins: { top: 90, bottom: 90, left: 130, right: 130 },
        children: [new Paragraph({
          children: (Array.isArray(cell) ? cell : [{ t: cell }]).map(x => new TextRun({
            text: x.t, bold: x.b, italics: x.i,
            font: x.code ? 'Consolas' : undefined,
            size: x.code ? 18 : 20,
            color: x.color,
          })),
        })],
      })),
    })),
  ],
});

const rule = () => new Paragraph({
  spacing: { before: 200, after: 200 },
  border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'D9D9D9' } },
  children: [],
});

const pageBreak = () => new Paragraph({ children: [new PageBreak()] });

// ── document ─────────────────────────────────────────────────────────────────
const doc = new Document({
  creator: 'PracticeLab',
  title: 'PracticeLab — Database & Storage Handover',
  description: 'Migration runbook and data storage model',
  numbering: {
    config: [
      {
        reference: 'bullets',
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 360, hanging: 220 } } } },
          { level: 1, format: LevelFormat.BULLET, text: '◦', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 220 } } } },
        ],
      },
      {
        reference: 'steps',
        levels: [
          { level: 0, format: LevelFormat.DECIMAL, text: '%1.', alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 360, hanging: 240 } } } },
        ],
      },
    ],
  },
  styles: {
    default: { document: { run: { font: 'Calibri', size: 21 } } },
  },
  sections: [{
    properties: { page: { margin: { top: 1080, bottom: 1080, left: 1080, right: 1080 } } },
    footers: {
      default: new Footer({
        children: [new Paragraph({
          alignment: AlignmentType.CENTER,
          children: [
            new TextRun({ text: 'PracticeLab — Database & Storage Handover   |   Page ', size: 16, color: GREY }),
            new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
            new TextRun({ text: ' of ', size: 16, color: GREY }),
            new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
          ],
        })],
      }),
    },
    children: [
      // ── title page ─────────────────────────────────────────────────────────
      new Paragraph({ spacing: { before: 2400, after: 0 }, children: [] }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 100 },
        children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 300 },
        children: [new TextRun({ text: 'Database & Storage Handover', size: 34, color: ACCENT })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 60 },
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
        children: [new TextRun({ text: '' })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 200, after: 80 },
        children: [new TextRun({
          text: 'Migration runbook and data storage model',
          size: 22, color: GREY, italics: true,
        })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { after: 80 },
        children: [new TextRun({
          text: 'For the receiving infrastructure and database team',
          size: 20, color: GREY,
        })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        spacing: { before: 600 },
        children: [new TextRun({ text: 'Prepared 12 August 2026', size: 19, color: GREY })],
      }),
      pageBreak(),

      // ── contents ───────────────────────────────────────────────────────────
      h1('Contents'),
      // A static list rather than a TOC field: a Word TOC renders empty until
      // someone updates fields, and this document will be emailed around and
      // read as-is more often than it is opened in Word.
      ...[
        ['1.', 'How the application is put together', true],
        ['1.1', 'There is one backend, not two', false],
        ['1.2', 'The fourth piece, which is not in that dashboard', false],
        ['1.3', 'The whole picture in one page', false],
        ['2.', 'Where the data lives', true],
        ['2.1', 'Charts — upload, storage keys, presigned URLs', false],
        ['2.2', 'Answer keys and other spreadsheet inputs', false],
        ['3.', 'Migration runbook', true],
        ['3.1', 'The short answer to "send us the scripts and backup"', false],
        ['3.2', 'What the application needs, and its environment variables', false],
        ['3.3', 'Recommended migration path', false],
        ['3.4', 'Dump and restore', false],
        ['3.5', 'What happens on first boot', false],
        ['3.6', 'Verification', false],
        ['3.7', 'Table inventory', false],
        ['3.8', 'Sizing', false],
        ['3.9', 'Ongoing operations', false],
        ['4.', 'Open items for the receiving team', true],
      ].map(([num, label, major]) => new Paragraph({
        spacing: { after: major ? 60 : 40, before: major ? 140 : 0 },
        indent: { left: major ? 0 : 400 },
        children: [
          new TextRun({ text: num + '  ', bold: major, size: major ? 22 : 20, color: major ? NAVY : GREY }),
          new TextRun({ text: label, bold: major, size: major ? 22 : 20, color: major ? NAVY : '404040' }),
        ],
      })),
      pageBreak(),

      // ══ PART 0 — orientation ═══════════════════════════════════════════════
      h1('1. How the application is put together'),
      p('Before the migration detail, an orientation — this answers the question that comes up first when someone looks at the hosting dashboard and counts the boxes.'),

      h2('1.1 There is one backend, not two'),
      p('The hosting dashboard shows three entries. Only two of them are applications; the third is storage.'),
      table(
        ['What you see', 'What it actually is', 'Is it a "backend"?'],
        [
          [[{ t: 'chart-viewer-ui', code: true }], 'The website itself — the pages a trainer or coder opens in the browser. Static files: HTML, JavaScript, CSS. No logic of its own; it asks the backend for everything.', [{ t: 'No', b: true }, { t: ' — it is the front end.' }]],
          [[{ t: 'chart-viewer-api', code: true }], 'The backend. All the logic lives here: grading, uploads, answer keys, analytics, reports. Written in Python.', [{ t: 'Yes', b: true }, { t: ' — this is the only one.' }]],
          [[{ t: 'chart-viewer-db', code: true }], 'The PostgreSQL database. It does not run any application code — it stores rows and answers queries when the backend asks.', [{ t: 'No', b: true }, { t: ' — it is the database.' }]],
        ],
        [2200, 4760, 2400],
      ),
      p('So: one front end, one backend, one database. The database appears alongside the two services in the dashboard because the host manages it for you, not because it is a third application.'),

      h2('1.2 The fourth piece, which is not in that dashboard'),
      callout('There is a storage bucket, and it is easy to miss', [
        'Chart page images are not in the database and not on either service. They sit in S3-compatible object storage, which is a separate provider and does not appear in the hosting dashboard alongside the other three.',
        [{ t: 'A migration that moves the database and both services, and forgets the bucket, produces an application where every chart is a broken image.', b: true }],
      ]),

      h2('1.3 The whole picture in one page'),
      table(
        ['Piece', 'Runs where', 'Holds what', 'Migrate how'],
        [
          ['Front end (UI)', 'Static site host', 'Nothing. Rebuilt from source code.', 'Redeploy from the repository'],
          ['Backend (API)', 'Web service', 'Nothing. Rebuilt from source code.', 'Redeploy from the repository'],
          ['Database', 'Managed PostgreSQL', 'All records: charts metadata, answer keys, batches, results, assessments', [{ t: 'pg_dump', code: true }, { t: ' and restore — Part 3' }]],
          ['Object storage', 'S3-compatible bucket', 'Chart page images — the only copy', 'Copy the bucket, or re-point at the existing one'],
        ],
        [1900, 2000, 3260, 2200],
      ),
      p('Only the last two hold anything. The first two are code, and code comes from the repository.'),

      rule(),
      p('The rest of this document is in two parts. Part 2 explains what is actually stored and where, which is worth reading before Part 3. Part 3 is the step-by-step migration.', { italics: true, color: GREY }),
      pageBreak(),

      // ══ PART 2 — storage model ═════════════════════════════════════════════
      h1('2. Where the data lives'),
      p('When a trainer uploads a chart or an answer-key spreadsheet, what is actually stored, and where. There are two stores, and they behave completely differently.'),

      table(
        ['', 'Object storage', 'PostgreSQL'],
        [
          ['Chart page images', [{ t: 'Yes — the only copy', b: true }], 'Storage key and extracted text only'],
          ['Original uploaded PDF', [{ t: 'Not retained', b: true, color: RED }], [{ t: 'Not retained', b: true, color: RED }]],
          ['Answer-key spreadsheets', [{ t: 'Not retained', b: true, color: RED }], 'Parsed values only'],
          ['Question-bank spreadsheets', [{ t: 'Not retained', b: true, color: RED }], 'Parsed rows only'],
          ['Everything else', 'No', 'Yes'],
        ],
        [3200, 3080, 3080],
      ),
      rich([
        { t: 'The headline for the migration: ' },
        { t: 'chart images must be migrated separately from the database, and no uploaded spreadsheet needs migrating at all', b: true },
        { t: ' — because none of them were ever kept.' },
      ]),

      h2('2.1 Charts'),
      h3('What happens on upload'),
      p('A trainer uploads a PDF, image or Word document. The application does not store that file. It converts it:'),
      code(['upload.pdf   →   page 1 PNG,  page 2 PNG,  page 3 PNG  …']),
      bullet('PDFs are rendered page-by-page to PNG at 1.7× scale'),
      bullet('Images (png, jpg, tiff, bmp, webp) are converted to PNG'),
      bullet('Word documents are rendered to page images'),
      bullet('Anything else is rejected'),
      p('Each resulting page is uploaded to object storage. The original file is discarded once conversion completes.'),

      callout('There is no archive of source PDFs anywhere in the system', [
        'The page images in object storage ARE the charts.',
        [{ t: 'Losing that bucket means losing every chart, and no database backup will bring them back.', b: true }],
      ]),

      h3('Storage key format'),
      code(['charts/{chart_id}/{page_order:04d}_{original_filename}.png', '', 'example:  charts/142/0000_Discharge Summary.pdf.png']),
      rich([
        { t: 'The key contains the numeric ' },
        { t: 'chart_id', code: true },
        { t: ', not the human chart number (' },
        { t: 'IP001', code: true },
        { t: '). Two consequences:' },
      ]),
      bullet('A straight bucket copy that preserves keys needs no database changes.'),
      bullet('Renaming a chart in the interface does not move any files.'),

      h3('What PostgreSQL holds'),
      rich([{ t: 'chart_files', code: true }, { t: ' — one row per page:' }]),
      table(
        ['Column', 'Contents'],
        [
          [[{ t: 'storage_key', code: true }], 'Path into the bucket (above)'],
          [[{ t: 'page_order', code: true }], 'Page sequence'],
          [[{ t: 'page_text', code: true }], 'Text extracted at upload, used for in-chart search'],
          [[{ t: 'original_filename, total_pages, uploaded_by', code: true }], 'Metadata'],
        ],
        [3600, 5760],
      ),
      rich([{ t: 'charts', code: true }, { t: ' — one row per chart: number, alias, specialty, category, difficulty, status, rationale, view count, uploader.' }]),

      h3('How pages reach the browser'),
      p('Files are not public. The API generates a presigned URL per request, valid for one hour by default. So:'),
      bullet('Bucket permissions can stay private'),
      bullet('A leaked URL expires'),
      bullet("The bucket must be reachable from the API, not from the user's browser directly"),

      h2('2.2 Answer keys and other spreadsheet inputs'),
      h3('The short version'),
      rich([
        { t: 'No uploaded spreadsheet is stored anywhere.', b: true },
        { t: ' Not in the database, not in object storage. Every Excel upload path reads the bytes, parses them, writes the parsed values to PostgreSQL, and discards the file.' },
      ]),
      p('Verified across all three upload paths — IP/OP answer keys, E/M answer keys, and the assessment question bank. None of them touch object storage.'),

      h3('What that means practically'),
      richBullet([{ t: 'For migration: ', b: true }, { t: 'there is nothing to migrate. Once the database is restored, every key is present.' }]),
      richBullet([{ t: 'For the trainers: ', b: true }, { t: 'the spreadsheet they uploaded is not recoverable from the application. If they want the original file, they keep their own copy. The app can regenerate an equivalent spreadsheet from stored data, but it is a fresh export, not the file they sent.' }]),
      richBullet([{ t: 'For audit: ', b: true }, { t: 'there is no record of the file itself, only its effects.' }]),

      h3('Where the parsed values land'),
      rich([{ t: 'IP/OP answer keys', b: true }, { t: ' → ' }, { t: 'answer_keys', code: true }, { t: ', one row per chart:' }]),
      table(
        ['Column', 'Type', 'Contents'],
        [
          [[{ t: 'pdx_code, pdx_poa', code: true }], 'text', 'Principal diagnosis and POA'],
          [[{ t: 'sdx', code: true }], 'JSON', [{ t: '[{code, poa, ccmcc}, …]', code: true }]],
          [[{ t: 'pcs', code: true }], 'JSON', [{ t: '[{code}, …]', code: true }, { t: '  (inpatient procedures)' }]],
          [[{ t: 'cpt', code: true }], 'JSON', [{ t: '[{code, modifier, pointers, units}, …]', code: true }]],
          [[{ t: 'facility_level, profee_level', code: true }], 'text', 'ED Single Path only'],
        ],
        [3200, 1200, 4960],
      ),
      rich([{ t: 'E/M answer keys', b: true }, { t: ' → ' }, { t: 'em_answer_keys', code: true }, { t: ', one row per chart: 47 columns covering the MDM element counts (COPA, Data Review, Risk), the derived levels, the E/M code and modifier, the encounter category, critical-care minutes, plus ' }, { t: 'dx_codes', code: true }, { t: ' and ' }, { t: 'procedure_cpts', code: true }, { t: ' as JSON.' }]),
      rich([{ t: 'Assessment questions', b: true }, { t: ' → ' }, { t: 'assessment_questions', code: true }, { t: ', one row per question: text, four options, correct answer, specialty, topic, difficulty, status.' }]),

      h3('A note on the JSON columns'),
      rich([
        { t: '19 columns across the schema are typed ' }, { t: 'JSON', code: true },
        { t: '. On PostgreSQL these are real JSON columns; on SQLite (local development only) they are TEXT and the driver deserialises them. This matters for anyone writing SQL directly against the database: ' },
        { t: 'answer_keys.cpt', code: true },
        { t: ' is queryable with PostgreSQL JSON operators, and its shape is documented above rather than being enforced by the schema.' },
      ]),
      pageBreak(),

      // ══ PART 3 — runbook ═══════════════════════════════════════════════════
      h1('3. Migration runbook'),

      h2('3.1 The short answer to "send us the scripts and backup"'),
      rich([
        { t: 'There is no schema script to send.', b: true },
        { t: ' This application has no ' }, { t: 'schema.sql', code: true },
        { t: ' and no Alembic. It creates its own schema on first boot:' },
      ]),
      code([
        'def init_db():',
        '    Base.metadata.create_all(bind=engine)   # tables defined as ORM models',
        '    _run_migrations()                       # 21 raw CREATE TABLE + ~100 ALTERs',
      ]),
      p('So the schema is the application. Point the API at an empty PostgreSQL database, set the environment variables, start it, and it builds everything.'),
      rich([{ t: 'The backup is a normal ' }, { t: 'pg_dump', code: true }, { t: '. That part is conventional — see 3.4.' }]),

      callout('Do not build the schema by hand from the ORM models', [
        [{ t: 'Six tables exist only in the raw migration DDL and are absent from the models: ' }, { t: 'em_answer_keys, em_grading_results, em_scoring_configs, practice_sessions, practice_chart_drafts, practice_results', code: true }, { t: '.' }],
        [{ t: 'create_all()', code: true }, { t: ' alone produces a database that looks right and is missing the entire E/M and practice-session subsystem.' }],
      ]),

      h2('3.2 What the application needs'),
      table(
        ['Component', 'Requirement'],
        [
          ['Database', 'PostgreSQL. Confirm the source version first — see 3.4.1'],
          ['API runtime', [{ t: 'Python 3.11.9 (' }, { t: 'backend/runtime.txt', code: true }, { t: ')' }]],
          ['Object storage', [{ t: 'S3-compatible bucket — ' }, { t: 'not optional', b: true }, { t: ', see Part 2' }]],
        ],
        [2600, 6760],
      ),
      h3('Environment variables'),
      p('All required unless noted.'),
      table(
        ['Variable', 'Purpose'],
        [
          [[{ t: 'DATABASE_URL', code: true }], 'PostgreSQL connection string'],
          [[{ t: 'STORAGE_ENDPOINT_URL', code: true }], 'S3-compatible endpoint'],
          [[{ t: 'STORAGE_ACCESS_KEY', code: true }], 'Storage access key'],
          [[{ t: 'STORAGE_SECRET_KEY', code: true }], 'Storage secret key'],
          [[{ t: 'STORAGE_BUCKET_NAME', code: true }], 'Bucket holding chart files'],
          [[{ t: 'STORAGE_PUBLIC_URL', code: true }], 'Public base URL for file access'],
          [[{ t: 'MASTER_ADMIN_PASSPHRASE', code: true }], 'Gates protected trainer actions. No default — the app will not start without it'],
          [[{ t: 'CORS_ORIGINS', code: true }], 'Comma-separated allowed frontend origins (default: localhost dev)'],
          [[{ t: 'FRONTEND_URL', code: true }], 'Optional, defaults to localhost dev'],
        ],
        [3400, 5960],
      ),
      rich([
        { t: 'DATABASE_URL', code: true },
        { t: ' accepts ' }, { t: 'postgres://', code: true }, { t: ', ' },
        { t: 'postgresql://', code: true }, { t: ' or ' }, { t: 'postgresql+asyncpg://', code: true },
        { t: ' — the app normalises the scheme itself.' },
      ]),

      h2('3.3 Recommended migration path'),
      rich([{ t: 'Restore a full dump into an empty database, then start the app.', b: true }, { t: ' Not the other way round. The reason is in 3.5.3.' }]),
      numbered('Provision an empty PostgreSQL database'),
      numbered('pg_dump from source (3.4)'),
      numbered('pg_restore into the new database (3.4)'),
      numbered('Verify row counts (3.6)'),
      numbered('Set environment variables, start the API'),
      numbered('Check startup logs for migration warnings (3.5.1)'),
      numbered('Verify via /health and a real screen (3.6)'),

      h2('3.4 Dump and restore'),
      h3('3.4.1 Confirm the source version first'),
      code(['SELECT version();']),
      p('Restoring into an older major version than the source will fail. Match the major version, or go newer.'),

      h3('3.4.2 Dump'),
      p('Custom format, which restores faster and lets you restore selectively:'),
      code([
        'pg_dump \\',
        '  --format=custom \\',
        '  --no-owner \\',
        '  --no-privileges \\',
        '  --file=practicelab_$(date +%Y%m%d).dump \\',
        '  "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"',
      ]),
      richBullet([{ t: '--no-owner', code: true }, { t: ' / ' }, { t: '--no-privileges', code: true }, { t: ' — the internal database will have different role names. Without these the restore emits errors for every object.' }]),
      richBullet([{ t: 'Add ' }, { t: '--verbose', code: true }, { t: ' if you want per-object progress.' }]),
      rich([{ t: 'A plain-SQL dump (' }, { t: '--format=plain --file=practicelab.sql', code: true }, { t: ') is also fine and easier to review, but restores more slowly.' }]),

      h3('3.4.3 Restore'),
      p('Into a genuinely empty database:'),
      code([
        'createdb practicelab',
        '',
        'pg_restore \\',
        '  --no-owner \\',
        '  --no-privileges \\',
        '  --dbname="postgresql://USER:PASSWORD@HOST:PORT/practicelab" \\',
        '  practicelab_YYYYMMDD.dump',
      ]),
      rich([{ t: 'For a plain-SQL dump: ' }, { t: 'psql -d "postgresql://..." -f practicelab.sql', code: true }]),
      p('Expect zero errors. Investigate any that appear rather than proceeding — a partially restored database will still start the app, because the app\'s migrations will happily create whatever is missing as empty tables.'),

      h2('3.5 What happens on first boot'),
      rich([{ t: 'Read this before starting the API. ' }, { t: 'init_db()', code: true }, { t: ' runs on every application start, not just the first.' }]),

      h3('3.5.1 Migrations are additive and non-fatal'),
      p('Every migration step is wrapped so that a failure is logged as a warning and startup continues:'),
      code(['logger.warning("Migration DDL failed (non-fatal): %s | sql=%s", exc, sql[:200])']),
      p('This is deliberate — a schema problem should not take the API down — but it means a partial failure is quiet. After the first boot against the new database, search the startup logs for:'),
      code(['Migration DDL failed']),
      rich([{ t: 'On a correctly restored database this should appear ' }, { t: 'zero', b: true }, { t: ' times. Anything there needs investigating before the app is considered live.' }]),

      h3('3.5.2 There is no migration version table'),
      p('Nothing records which migrations have run. Each one re-checks whether its column or table already exists and skips if so. Consequences:'),
      bullet('Running the app repeatedly is safe and idempotent.'),
      bullet('Your DBA cannot ask "what schema version is this?" The honest answer is "whatever the currently deployed code builds."'),
      bullet('Rolling the application back to an older release does not roll the schema back. The schema only moves forward.'),

      h3('3.5.3 Sample data is seeded into an empty question bank'),
      rich([{ t: 'If ' }, { t: 'assessment_questions', code: true }, { t: ' is empty at boot, the app inserts sample assessment questions. This is why the restore must come before the first boot:' }]),
      richBullet([{ t: 'Restore first, then boot', b: true }, { t: ' → table is populated, seed skips. Correct.' }]),
      richBullet([{ t: 'Boot first, then restore', b: true }, { t: ' → seeded rows already exist and the restore will hit unique-constraint violations on ' }, { t: 'question_id', code: true }, { t: '. Avoid.' }]),
      p('If the app has already been booted against the empty database, drop and recreate the database before restoring rather than trying to reconcile.'),

      h2('3.6 Verification'),
      h3('3.6.1 Row counts — run against source and target, compare'),
      code([
        "SELECT 'charts', COUNT(*) FROM charts",
        "UNION ALL SELECT 'chart_files', COUNT(*) FROM chart_files",
        "UNION ALL SELECT 'answer_keys', COUNT(*) FROM answer_keys",
        "UNION ALL SELECT 'em_answer_keys', COUNT(*) FROM em_answer_keys",
        "UNION ALL SELECT 'batches', COUNT(*) FROM batches",
        "UNION ALL SELECT 'batch_charts', COUNT(*) FROM batch_charts",
        "UNION ALL SELECT 'grading_results', COUNT(*) FROM grading_results",
        "UNION ALL SELECT 'practice_sessions', COUNT(*) FROM practice_sessions",
        "UNION ALL SELECT 'practice_results', COUNT(*) FROM practice_results",
        "UNION ALL SELECT 'assessment_questions', COUNT(*) FROM assessment_questions",
        "UNION ALL SELECT 'assessment_sessions', COUNT(*) FROM assessment_sessions",
        "UNION ALL SELECT 'assessment_results', COUNT(*) FROM assessment_results",
        'ORDER BY 1;',
      ]),

      h3('3.6.2 Sequences'),
      p('A pg_restore of a custom-format dump normally restores sequence positions correctly. Verify rather than assume — the symptom of getting this wrong is a duplicate-key error on the first insert after go-live.'),
      p('To repair one:'),
      code([
        'SELECT setval(',
        "  pg_get_serial_sequence('charts', 'id'),",
        '  (SELECT COALESCE(MAX(id), 1) FROM charts)',
        ');',
      ]),
      rich([
        { t: 'Repeat per affected table. Six tables were originally created with ' },
        { t: 'INTEGER PRIMARY KEY', code: true },
        { t: ' rather than ' }, { t: 'SERIAL', code: true },
        { t: ' and had sequences attached later by migration (' },
        { t: 'practice_sessions, practice_chart_drafts, practice_results', code: true },
        { t: ' and their dependants) — these are the most likely to need attention.' },
      ]),

      h3('3.6.3 Application health'),
      code(['curl -s https://YOUR-INTERNAL-API/health', '# {"status":"ok"}']),
      rich([{ t: '/health', code: true }, { t: ' confirms the process is up. It does not touch the database — use this instead for a real read:' }]),
      code(['curl -s "https://YOUR-INTERNAL-API/charts/search?page_size=1"']),

      h3('3.6.4 End-to-end smoke test'),
      numbered('Chart Library — search a chart, open it, confirm the file renders. This is the storage check, and the one most likely to fail.'),
      numbered('PracticeLab — open an existing batch, confirm results and scores display.'),
      numbered('Assessment — open Analytics, confirm figures match the source environment.'),

      callout('The failure mode to watch for', [
        'A database-only migration produces an application that looks entirely healthy: charts list, batches open, results display, analytics compute. Every chart is a broken image.',
        [{ t: 'Verify by opening a chart and confirming the page renders, not by confirming the chart appears in a list.', b: true }],
      ]),

      h2('3.7 Table inventory'),
      p('32 tables, grouped by subsystem.'),
      table(
        ['Subsystem', 'Tables'],
        [
          ['Chart Library', [{ t: 'charts, chart_files, chart_sequences, chart_feedback, audit_logs, coding_resources', code: true }]],
          ['PracticeLab', [{ t: 'batches, batch_coders, batch_charts, batch_allocation_cycles, submissions, grading_results, grading_feedback, ed_rubric_details, answer_keys, scoring_configs, self_practice_submissions, self_practice_results', code: true }]],
          ['PracticeLab E/M', [{ t: 'em_answer_keys, em_grading_results, em_scoring_configs', code: true }]],
          ['PracticeLab sessions', [{ t: 'practice_sessions, practice_chart_drafts, practice_results', code: true }]],
          ['Assessment', [{ t: 'assessment_questions, assessment_configs, generated_assessments, generated_assessment_students, assessment_sessions, assessment_responses, assessment_results, assessment_audit_log', code: true }]],
        ],
        [2400, 6960],
      ),

      h2('3.8 Sizing'),
      p('To estimate the bucket:'),
      code(['SELECT COUNT(*) AS page_count FROM chart_files;']),
      p('Every row is one PNG. Typical rendered chart pages run a few hundred KB each, so multiply for a rough figure — or query the bucket directly for the exact size, which is more reliable than an estimate.'),
      p('The PostgreSQL side is small by comparison: text, codes and JSON, with no binary content of any kind.'),

      h2('3.9 Ongoing operations'),
      richBullet([{ t: 'Backups. ', b: true }, { t: 'Nothing in the application performs them. Schedule ' }, { t: 'pg_dump', code: true }, { t: ' (daily is typical) plus a bucket backup for the chart files.' }]),
      richBullet([{ t: 'Deployments. ', b: true }, { t: 'Each release runs ' }, { t: 'init_db()', code: true }, { t: ' again. Additive migrations apply automatically; check the logs for ' }, { t: 'Migration DDL failed', code: true }, { t: ' after any deploy that changed the schema.' }]),
      richBullet([{ t: 'Rollback. ', b: true }, { t: 'Application rollback does not roll the schema back. Because migrations only add, an older application release generally runs against a newer schema — but this is not guaranteed and should be tested rather than relied on.' }]),

      pageBreak(),
      h1('4. Open items for the receiving team'),
      p('Decisions and confirmations needed before the migration can be scheduled.'),
      table(
        ['#', 'Item', 'Owner'],
        [
          ['1', 'Confirm the PostgreSQL major version to provision (3.4.1)', ''],
          ['2', 'Decide storage: re-point at the existing bucket, or copy it (Part 2)', ''],
          ['3', [{ t: 'Confirm who holds ' }, { t: 'MASTER_ADMIN_PASSPHRASE', code: true }, { t: ' and how it is rotated' }], ''],
          ['4', [{ t: 'Set ' }, { t: 'CORS_ORIGINS', code: true }, { t: ' to the internal frontend origin — a mismatch produces a frontend that loads and then fails every request' }], ''],
          ['5', 'Agree the backup schedule and retention', ''],
        ],
        [600, 6760, 2000],
      ),
    ],
  }],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync('PracticeLab_Database_Storage_Handover.docx', buf);
  console.log('written', buf.length, 'bytes');
});
