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

const doc = new Document({
  creator: 'PracticeLab',
  title: 'PracticeLab — Data Architecture and Migration Specification',
  description: 'Database, object storage and migration procedure',
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
        new TextRun({ text: 'PracticeLab — Data Architecture and Migration Specification   |   ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.CURRENT], size: 16, color: GREY }),
        new TextRun({ text: ' / ', size: 16, color: GREY }),
        new TextRun({ children: [PageNumber.TOTAL_PAGES], size: 16, color: GREY }),
      ],
    })] }) },
    children: separate([
      // ── cover ────────────────────────────────────────────────────────────
      new Paragraph({ spacing: { before: 2200 }, children: [] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 110 },
        children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 340 },
        children: [new TextRun({ text: 'Data Architecture and Migration Specification', size: 30, color: ACCENT })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
        border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
        children: [new TextRun({ text: '' })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
        children: [new TextRun({ text: 'Database schema · object storage · migration procedure', size: 21, color: GREY, italics: true })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
        children: [new TextRun({ text: 'Audience: infrastructure, database and application engineers', size: 20, color: GREY })] }),
      new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
        children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}`, size: 19, color: GREY })] }),
      brk(),

      // ── 0. about ─────────────────────────────────────────────────────────
      h1('About this document'),
      p('PracticeLab is a web application for training and assessing medical coders. It holds a library of de-identified clinical charts, distributes them to coders as graded assignments, scores their coded output against trainer-supplied answer keys, and runs multiple-choice assessments.'),
      p('This specification describes where PracticeLab keeps its data and how to move it to another environment. It covers the database schema, the object storage that holds chart images, and a step-by-step migration procedure with verification.'),
      p('It assumes no prior familiarity with the application. It does not cover application features, user workflows or the grading rules.'),

      h3('Contents'),
      ...[
        ['1.', 'System architecture', true],
        ['1.1', 'Components', false],
        ['1.2', 'What each component holds', false],
        ['2.', 'Data architecture', true],
        ['2.1', 'Charts: ingestion and retrieval', false],
        ['2.2', 'Spreadsheet inputs: answer keys and question banks', false],
        ['2.3', 'Schema map', false],
        ['3.', 'Object storage', true],
        ['3.1', 'Current implementation', false],
        ['3.2', 'Requirements of a storage backend', false],
        ['3.3', 'Migration options by effort', false],
        ['4.', 'Migration procedure', true],
        ['4.1', 'Schema provisioning', false],
        ['4.2', 'Environment configuration', false],
        ['4.3', 'Sequence of operations', false],
        ['4.4', 'Database dump and restore', false],
        ['4.5', 'Storage transfer', false],
        ['4.6', 'Application first start', false],
        ['5.', 'Verification', true],
        ['6.', 'Operational notes', true],
        ['7.', 'Decisions required', true],
      ].map(([n, l, major]) => new Paragraph({
        spacing: { after: major ? 60 : 40, before: major ? 130 : 0 },
        indent: { left: major ? 0 : 400 },
        children: [
          new TextRun({ text: n + '  ', bold: major, size: major ? 21 : 20, color: major ? NAVY : GREY }),
          new TextRun({ text: l, bold: major, size: major ? 21 : 20, color: major ? NAVY : '404040' }),
        ],
      })),
      brk(),

      // ── 1. architecture ──────────────────────────────────────────────────
      h1('1. System architecture'),
      ...figure('fig1_architecture.png', 1241, 721,
        'Figure 1 — Component topology and data paths'),

      h2('1.1 Components'),
      p('PracticeLab comprises four components. Two execute code and hold no persistent state; two hold data and execute none.'),
      table(
        ['Component', 'Technology', 'Executes code', 'Holds data'],
        [
          ['Front end', 'React static site', 'In the browser only', 'No'],
          ['Backend API', 'FastAPI, Python 3.11', 'Yes — all application logic', 'No'],
          ['Relational database', 'PostgreSQL', 'No', 'Yes — 46 tables'],
          ['Object storage', 'S3-compatible bucket', 'No', 'Yes — chart page images'],
        ],
        [2300, 2900, 2280, 1880],
      ),
      p('The front end contains no business logic. It renders views and calls the backend for every piece of data, including chart images. The backend is the only component that connects to either data store, and the only one holding credentials.'),

      h2('1.2 What each component holds'),
      table(
        ['Component', 'Persistent state', 'Rebuilt from', 'Migration action'],
        [
          ['Front end', 'None', 'Source repository', 'Redeploy'],
          ['Backend API', 'None', 'Source repository', 'Redeploy'],
          ['Database', 'All application records', 'Backup only', [{ t: 'pg_dump', code: true }, { t: ' / restore — section 4' }]],
          ['Object storage', 'Chart page images', 'Backup only', 'Bucket transfer — section 4.5'],
        ],
        [2000, 2600, 2200, 2560],
      ),
      callout('Two of the four components carry data, and they are backed up separately', [
        'A database backup does not contain chart images. An object storage backup does not contain any other record.',
        [{ t: 'Both must be transferred for the application to be functional after migration.', b: true }],
      ]),
      brk(),

      // ── 2. data architecture ─────────────────────────────────────────────
      h1('2. Data architecture'),
      h2('2.1 Charts: ingestion and retrieval'),
      ...figure('fig2_chartflow.png', 1241, 641,
        'Figure 2 — Chart ingestion and retrieval'),

      h3('Ingestion'),
      p('A chart is uploaded as a PDF, an image file, or a Word document. The application converts it and does not retain the uploaded file.'),
      bullet('PDF documents are rendered page-by-page to PNG at 1.7× scale'),
      bullet('Image files (PNG, JPG, TIFF, BMP, WEBP) are converted to PNG'),
      bullet('Word documents are rendered to page images'),
      bullet('Other file types are rejected at upload'),
      p('Each page image is written to object storage. Text is extracted during conversion and stored in the database to support in-chart search. The source file is discarded once conversion completes.'),
      callout('The page images are the only copy of chart content', [
        'The application retains no archive of uploaded source files.',
        [{ t: 'Loss of the object storage bucket is loss of every chart, and is not recoverable from a database backup.', b: true }],
      ]),

      h3('Storage key format'),
      code(['charts/{chart_id}/{page_order:04d}_{original_filename}.png',
            '', 'example:  charts/142/0000_Discharge Summary.pdf.png']),
      rich([{ t: 'The key embeds the numeric ' }, { t: 'chart_id', code: true },
             { t: ', not the human-readable chart number such as ' }, { t: 'IP001', code: true }, { t: '. Consequently:' }]),
      bullet('A bucket transfer that preserves keys requires no database changes'),
      bullet('Renaming a chart in the application does not relocate any stored object'),

      h3('Database record'),
      rich([{ t: 'chart_files', code: true }, { t: ' holds one row per page:' }]),
      table(
        ['Column', 'Contents'],
        [
          [[{ t: 'storage_key', code: true }], 'Object key in the bucket'],
          [[{ t: 'page_order', code: true }], 'Page sequence within the chart'],
          [[{ t: 'page_text', code: true }], 'Text extracted at upload, used for in-chart search'],
          [[{ t: 'original_filename, total_pages, uploaded_by', code: true }], 'Upload metadata'],
        ],
        [3700, 5660],
      ),
      rich([{ t: 'charts', code: true }, { t: ' holds one row per chart: chart number, alias, specialty, category, difficulty, status, rationale, view count and uploader.' }]),

      h3('Retrieval'),
      p('Chart images are served through the backend. The browser issues a request to the API, the API retrieves the object from storage server-side, and the bytes are streamed back in the response.'),
      code(['GET /charts/{chart_id}/page/{page_order}']),
      p('The browser is never given a storage URL and never holds storage credentials. This has the following consequences for deployment:'),
      table(
        ['Property', 'Value'],
        [
          ['Front end connects to storage', [{ t: 'No', b: true }]],
          ['Browser holds storage credentials', [{ t: 'No', b: true }]],
          ['Storage must be reachable from user browsers', [{ t: 'No', b: true }]],
          ['Storage requires CORS configuration', [{ t: 'No', b: true }]],
          ['Storage may be private and internal-network-only', [{ t: 'Yes', b: true }]],
        ],
        [5560, 3800],
      ),
      rich([{ t: 'Responses carry ' }, { t: 'Cache-Control: private, max-age=3600', code: true },
             { t: ', so a browser reuses a page image for one hour without a further request.' }]),
      callout('An unused function in the storage module', [
        [{ t: 'services/storage.py', code: true }, { t: ' defines ' }, { t: 'get_presigned_url()', code: true }, { t: '. It is imported but never called; presigned URLs are not used by the application.' }],
        [{ t: 'Reading that function as evidence that browsers fetch directly from storage will lead to network access being provisioned that the application does not require.', b: true }],
      ]),
      brk(),

      h2('2.2 Spreadsheet inputs: answer keys and question banks'),
      p('Trainers supply answer keys and assessment questions as Excel workbooks. Three upload paths exist: IP/OP answer keys, E/M answer keys, and the assessment question bank.'),
      rich([{ t: 'No uploaded workbook is retained.', b: true },
             { t: ' Each upload path reads the file, parses it, writes the parsed values to PostgreSQL and discards the file. No workbook is written to object storage or stored as a database blob.' }]),
      h3('Consequences'),
      rbullet([{ t: 'Migration: ', b: true }, { t: 'no workbook requires transfer. A restored database contains every answer key and question.' }]),
      rbullet([{ t: 'Recovery: ', b: true }, { t: 'an uploaded workbook cannot be retrieved from the application. The answer-key export regenerates an equivalent workbook from stored values; it is not the original file.' }]),
      rbullet([{ t: 'Audit: ', b: true }, { t: 'the application records the parsed result, not the submitted file.' }]),

      h3('Destination tables'),
      rich([{ t: 'IP/OP answer keys → ' }, { t: 'answer_keys', code: true }, { t: ', one row per chart:' }]),
      table(
        ['Column', 'Type', 'Contents'],
        [
          [[{ t: 'pdx_code, pdx_poa', code: true }], 'text', 'Principal diagnosis and POA indicator'],
          [[{ t: 'sdx', code: true }], 'JSON', [{ t: '[{code, poa, ccmcc}, …]', code: true }]],
          [[{ t: 'pcs', code: true }], 'JSON', [{ t: '[{code}, …]', code: true }, { t: ' — inpatient procedures' }]],
          [[{ t: 'cpt', code: true }], 'JSON', [{ t: '[{code, modifier, pointers, units}, …]', code: true }]],
          [[{ t: 'facility_level, profee_level', code: true }], 'text', 'ED Single Path specialty only'],
        ],
        [3300, 1200, 4860],
      ),
      rich([{ t: 'E/M answer keys → ' }, { t: 'em_answer_keys', code: true },
             { t: ', one row per chart across 48 columns: medical decision-making element counts, derived complexity levels, E/M code and modifier, encounter category, critical care minutes, and diagnosis and procedure codes as JSON.' }]),
      rich([{ t: 'Assessment questions → ' }, { t: 'assessment_questions', code: true },
             { t: ', one row per question: question text, four options, correct answer, specialty, topic, difficulty and status.' }]),

      h3('JSON columns'),
      rich([{ t: '36 columns across the schema are typed ' }, { t: 'JSON', code: true },
             { t: '. Under PostgreSQL these are native JSON columns and are queryable with JSON operators. Their internal structure is defined by the application rather than enforced by the schema; the shapes above are authoritative.' }]),
      brk(),

      h2('2.3 Schema map'),
      ...figure('fig3_schema.png', 1241, 801,
        'Figure 3 — The tables, grouped by functional domain'),
      p('The schema divides into six domains. The Chart Library is referenced by the PracticeLab and Auditor domains; the Assessment domain is independent of charts entirely, as assessments are multiple-choice papers rather than coding work.'),
      callout('Six tables are absent from the ORM models', [
        [{ t: 'em_answer_keys, em_grading_results, em_scoring_configs, practice_sessions, practice_chart_drafts, practice_results', code: true }, { t: ' are created by raw migration DDL only.' }],
        [{ t: 'A schema generated from the SQLAlchemy models alone will appear correct and will be missing the entire E/M grading and practice-session subsystems.', b: true }],
      ]),
      brk(),

      // ── 3. object storage ────────────────────────────────────────────────
      h1('3. Object storage'),
      h2('3.1 Current implementation'),
      p('The bucket is currently hosted on Cloudflare R2, which exposes an S3-compatible API. The application uses the boto3 AWS SDK with a configurable endpoint:'),
      code([
        'boto3.client(',
        '    "s3",',
        '    endpoint_url=settings.STORAGE_ENDPOINT_URL,',
        '    aws_access_key_id=settings.STORAGE_ACCESS_KEY,',
        '    aws_secret_access_key=settings.STORAGE_SECRET_KEY,',
        '    config=Config(signature_version="s3v4"),',
        ')',
      ]),
      h3('Values required from the current provider'),
      table(
        ['Value', 'Source', 'Environment variable'],
        [
          ['Account identifier', 'Cloudflare dashboard → R2', [{ t: 'Forms part of STORAGE_ENDPOINT_URL', code: true }]],
          ['Access key ID and secret', 'R2 → Manage API Tokens', [{ t: 'STORAGE_ACCESS_KEY, STORAGE_SECRET_KEY', code: true }]],
          ['Bucket name', 'R2 → Buckets', [{ t: 'STORAGE_BUCKET_NAME', code: true }]],
        ],
        [2600, 2900, 3860],
      ),
      code(['endpoint format:  https://<ACCOUNT_ID>.r2.cloudflarestorage.com']),
      callout('API token secrets are displayed once, at creation', [
        'A secret that has not been recorded cannot be retrieved. Issue a replacement token instead.',
        'Tokens are independent of stored data: issuing or revoking a token does not affect objects in the bucket.',
        'Required permissions: read and write. The application writes on chart upload, reads on chart view, and deletes on chart removal.',
      ], 'info'),

      h2('3.2 Requirements of a storage backend'),
      p('The application performs three storage operations:'),
      table(
        ['Operation', 'Invoked when'],
        [
          [[{ t: 'put_object', code: true }], 'A chart is uploaded — one call per page'],
          [[{ t: 'get_object', code: true }], 'A chart page is viewed'],
          [[{ t: 'delete_object', code: true }], 'A chart is removed'],
        ],
        [2900, 6460],
      ),
      p('No listing, multipart upload, versioning, lifecycle policy, access control list, bucket policy, object tagging or presigned URL generation is used. The application stores objects under keys and retrieves them.'),
      rich([{ t: 'The selection of a storage backend is therefore governed by existing organisational infrastructure rather than by any capability the application requires.', b: true }]),

      h2('3.3 Migration options by effort'),
      h3('Tier 1 — configuration only, no code change'),
      p('Any S3-compatible service. The client already targets a non-AWS endpoint, so no code path changes.'),
      table(
        ['Option', 'Typical context'],
        [
          [[{ t: 'AWS S3', b: true }], 'An existing AWS presence'],
          [[{ t: 'MinIO', b: true }], 'Self-hosted, on-premises or in Kubernetes. Common where data residency is mandated'],
          [[{ t: 'Ceph RADOS Gateway', b: true }], 'An existing Ceph deployment'],
          [[{ t: 'Dell ECS · NetApp StorageGRID · Pure FlashBlade · Hitachi HCP', b: true }], 'On-premises enterprise object storage appliances'],
          [[{ t: 'Google Cloud Storage', b: true }], 'Via the S3-compatible XML API using HMAC keys'],
          [[{ t: 'Wasabi · Backblaze B2', b: true }], 'S3-compatible providers selected on cost'],
        ],
        [3700, 5660],
      ),
      p('Configuration change required:'),
      code([
        'STORAGE_ENDPOINT_URL   →  new service endpoint',
        'STORAGE_ACCESS_KEY     →  new access key',
        'STORAGE_SECRET_KEY     →  new secret',
        'STORAGE_BUCKET_NAME    →  new bucket name, if changed',
      ]),

      h3('Tier 2 — approximately thirty lines of code'),
      rich([{ t: 'Azure Blob Storage', b: true }, { t: ' is the principal non-S3 option and has no native S3 API. Implementation is contained: the three operations are wrapped in ' }, { t: 'backend/services/storage.py', code: true }, { t: ', and no other module imports boto3.' }]),
      table(
        ['Function', 'Called by'],
        [
          [[{ t: 'upload_bytes(key, data, content_type)', code: true }], 'Chart upload'],
          [[{ t: 'open_object(key)', code: true }], [{ t: 'Chart page retrieval — returns ' }, { t: '(body, content_type)', code: true }]],
          [[{ t: 'delete_object(key)', code: true }], 'Chart removal'],
        ],
        [4300, 5060],
      ),

      h3('Tier 3 — same three functions, with durability implications'),
      p('A mounted network share (NFS or SMB) or local disk. Implementation is trivial, but durability becomes a property of that volume rather than of a replicated object store, and running more than one API instance requires the volume to be shared. Appropriate for a single-instance deployment that is expected to remain so.'),

      h3('Recommendation'),
      p('Where the organisation operates any existing object storage, use it. A Tier 1 migration is configuration only and introduces no code to test.'),
      p('Select Azure Blob Storage where the organisation is Azure-standardised and non-Azure object storage would represent a policy exception. The implementation is small but is code, and requires testing that configuration does not.'),
      p('Avoid the network-share option unless the deployment is single-instance by design.'),

      h3('Invariants across all options'),
      rbullet([{ t: 'The database is unchanged. ' }, { t: 'chart_files.storage_key', code: true }, { t: ' retains the same values' }]),
      bullet('Chart images continue to be proxied by the backend; the browser does not contact storage'),
      bullet('No CORS configuration is required'),
      bullet('Storage need only be reachable from the backend and may reside entirely within the internal network'),
      brk(),

      // ── 4. procedure ─────────────────────────────────────────────────────
      h1('4. Migration procedure'),
      h2('4.1 Schema provisioning'),
      p('The application has no schema script and does not use a migration framework such as Alembic. The schema is created by the application at startup:'),
      code([
        'def init_db():',
        '    Base.metadata.create_all(bind=engine)   # tables defined as ORM models',
        '    _run_migrations()                       # 21 CREATE TABLE + ~115 ALTER statements',
      ]),
      p('An empty PostgreSQL database and a correctly configured application are sufficient to produce a complete schema. No DDL file is required or available.'),
      callout('Migration statements fail silently by design', [
        [{ t: 'Each statement is executed independently, and a failure is logged as a warning while startup continues:' }],
        [{ t: 'logger.warning("Migration DDL failed (non-fatal): %s | sql=%s", exc, sql[:200])', code: true }],
        [{ t: 'This prevents a schema problem from taking the API offline, but means a partial failure is not otherwise visible. Startup logs must be inspected after the first start against a new database — see section 4.6.', b: true }],
      ]),
      p('There is no schema version table. Each statement re-checks whether its target already exists and is skipped if so, making repeated startup safe and idempotent. A schema version cannot be queried; the schema corresponds to the deployed application revision. Application rollback does not revert the schema.'),

      h2('4.2 Environment configuration'),
      table(
        ['Variable', 'Required', 'Purpose'],
        [
          [[{ t: 'DATABASE_URL', code: true }], 'Yes', 'PostgreSQL connection string'],
          [[{ t: 'STORAGE_ENDPOINT_URL', code: true }], 'Yes', 'S3-compatible endpoint'],
          [[{ t: 'STORAGE_ACCESS_KEY', code: true }], 'Yes', 'Storage access key'],
          [[{ t: 'STORAGE_SECRET_KEY', code: true }], 'Yes', 'Storage secret'],
          [[{ t: 'STORAGE_BUCKET_NAME', code: true }], 'Yes', 'Bucket name'],
          [[{ t: 'STORAGE_PUBLIC_URL', code: true }], 'Yes', 'Not read by application code — see note below'],
          [[{ t: 'MASTER_ADMIN_PASSPHRASE', code: true }], 'Yes', 'Authorises protected trainer operations. No default'],
          [[{ t: 'CORS_ORIGINS', code: true }], 'No', 'Comma-separated permitted front-end origins'],
          [[{ t: 'FRONTEND_URL', code: true }], 'No', 'Defaults to local development address'],
        ],
        [3400, 1400, 4560],
      ),
      rich([{ t: 'DATABASE_URL', code: true }, { t: ' accepts the ' }, { t: 'postgres://', code: true },
             { t: ', ' }, { t: 'postgresql://', code: true }, { t: ' and ' }, { t: 'postgresql+asyncpg://', code: true },
             { t: ' schemes; the application normalises them.' }]),
      callout('STORAGE_PUBLIC_URL is required but unused', [
        'The application will not start unless this variable is set, and no application code reads its value. It is a residual configuration item.',
        'Set it to any non-empty value; the bucket URL is a reasonable choice. No behaviour depends on it.',
      ]),

      h2('4.3 Sequence of operations'),
      rich([{ t: 'The database must be restored before the application is started for the first time.', b: true }, { t: ' See section 4.6 for the reason.' }]),
      step('Provision an empty PostgreSQL database'),
      step('Produce a dump from the source database (4.4)'),
      step('Restore the dump into the new database (4.4)'),
      step('Transfer or re-point object storage (4.5)'),
      step('Verify row counts against the source (5)'),
      step('Configure environment variables and start the API (4.2, 4.6)'),
      step('Inspect startup logs for migration warnings (4.6)'),
      step('Complete functional verification (5)'),

      h2('4.4 Database dump and restore'),
      h3('Confirm the source version'),
      code(['SELECT version();']),
      p('Restoring into an earlier major version than the source will fail. Provision a matching or later major version.'),
      h3('Dump'),
      code([
        'pg_dump \\',
        '  --format=custom \\',
        '  --no-owner \\',
        '  --no-privileges \\',
        '  --file=practicelab_$(date +%Y%m%d).dump \\',
        '  "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"',
      ]),
      rbullet([{ t: '--no-owner', code: true }, { t: ' and ' }, { t: '--no-privileges', code: true },
               { t: ' — role names differ between environments; without these the restore reports an error for every object' }]),
      rbullet([{ t: '--verbose', code: true }, { t: ' may be added for per-object progress' }]),
      h3('Restore'),
      code([
        'createdb practicelab',
        '',
        'pg_restore \\',
        '  --no-owner \\',
        '  --no-privileges \\',
        '  --dbname="postgresql://USER:PASSWORD@HOST:PORT/practicelab" \\',
        '  practicelab_YYYYMMDD.dump',
      ]),
      p('The restore is expected to complete without errors. Any error should be resolved before proceeding: a partially restored database will still start the application, because the startup migrations will create any missing table as empty.'),

      h3('Restoring a directory-format backup'),
      p('Backups supplied through the project repository under docs/ are directory-format dumps that have been compressed with tar. They are not plain SQL, and psql will not read them. Extract first, then restore against the extracted directory.'),
      code(['tar -xzf 2026-08-31T16_37Z.dir.tar.gz']),
      p('This produces a timestamped directory containing a chartviewer directory of .dat files and a toc.dat. pg_restore is pointed at that inner directory, not at the archive and not at a single file.'),
      code([
        'createdb practicelab',
        '',
        'pg_restore \\',
        '  --no-owner \\',
        '  --no-privileges \\',
        '  --clean --if-exists \\',
        '  --dbname="postgresql://USER:PASSWORD@HOST:PORT/practicelab" \\',
        '  "2026-08-31T16:37Z/chartviewer"',
      ]),
      rbullet([{ t: 'The directory name contains colons and must be quoted. An unquoted path fails as though the file were missing.' }]),
      rbullet([{ t: '--clean --if-exists', code: true }, { t: ' drops existing objects first, making the restore repeatable. Both may be omitted when restoring into a database that has just been created.' }]),
      rbullet([{ t: '--jobs=4', code: true }, { t: ' restores tables in parallel. This is the principal reason to use directory format and is not available for plain-SQL dumps.' }]),
      rbullet([{ t: 'A dump may be inspected without restoring it: ' }, { t: 'pg_restore --list "DIR/chartviewer"', code: true }]),
      callout('The dump does not contain credentials', [
        [{ t: 'The administrative passphrase and the object storage keys are held in environment variables and are never written to the database.' }],
        [{ t: 'A restored database alone will not run the application. The environment variables in section 2 must be set as well, or the API starts and fails every file request.', b: true }],
      ]),

      h2('4.5 Storage transfer'),
      p('Two approaches are available.'),
      rich([{ t: 'Re-point. ', b: true }, { t: 'Configure the new environment against the existing bucket. No data is moved. The environment requires outbound access to the provider endpoint.' }]),
      rich([{ t: 'Transfer. ', b: true }, { t: 'Copy objects to the target bucket:' }]),
      code(['rclone sync SOURCE:BUCKET TARGET:BUCKET --progress']),
      code([
        'aws s3 sync s3://SOURCE_BUCKET s3://TARGET_BUCKET \\',
        '  --endpoint-url https://<ACCOUNT_ID>.r2.cloudflarestorage.com',
      ]),
      callout('Object keys must be preserved exactly', [
        [{ t: 'Keys are recorded in ' }, { t: 'chart_files.storage_key', code: true }, { t: ' and are the sole reference from a database row to its image.' }],
        [{ t: 'A transfer that adds a prefix or alters key structure will render every chart unreadable, with no error at migration time.', b: true }],
      ]),

      h2('4.6 Application first start'),
      rich([{ t: 'init_db()', code: true }, { t: ' executes on every application start, not only the first. Three behaviours are relevant.' }]),
      h3('Sample data seeding'),
      rich([{ t: 'If ' }, { t: 'assessment_questions', code: true },
             { t: ' is empty at startup, the application inserts a set of sample assessment questions. This determines the required ordering:' }]),
      rbullet([{ t: 'Restore, then start', b: true }, { t: ' — the table is populated and seeding is skipped. Correct.' }]),
      rbullet([{ t: 'Start, then restore', b: true }, { t: ' — seeded rows are present and the restore fails on unique constraint violations against ' }, { t: 'question_id', code: true }, { t: '.' }]),
      p('If the application has already been started against the empty database, drop and recreate the database before restoring.'),
      h3('Log inspection'),
      p('After the first start against the migrated database, search the startup logs for:'),
      code(['Migration DDL failed']),
      rich([{ t: 'On a correctly restored database this must not appear. Any occurrence should be investigated before the environment is accepted.', b: true }]),
      brk(),

      // ── 5. verification ──────────────────────────────────────────────────
      h1('5. Verification'),
      h2('5.1 Row counts'),
      p('Execute against both source and target and compare:'),
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
      h2('5.2 Sequence positions'),
      p('A custom-format restore normally restores sequence positions correctly. Verification is recommended: an incorrect sequence produces a duplicate key error on the first insert after go-live rather than at migration time. To correct one:'),
      code([
        'SELECT setval(',
        "  pg_get_serial_sequence('charts', 'id'),",
        '  (SELECT COALESCE(MAX(id), 1) FROM charts)',
        ');',
      ]),
      rich([{ t: 'Six tables were originally defined with ' }, { t: 'INTEGER PRIMARY KEY', code: true },
             { t: ', which is an auto-assigning rowid alias in SQLite but a plain integer with no default in PostgreSQL. Sequences were attached by later migrations — ' },
             { t: 'practice_sessions, practice_chart_drafts, practice_results', code: true },
             { t: ' and ' },
             { t: 'em_answer_keys, em_grading_results, em_scoring_configs', code: true },
             { t: '. These warrant particular attention: with no default, every insert omitting id raises NotNullViolation, which took the whole E/M module out of service in the hosted environment. The repair migrations are re-runnable and safe on a populated table.' }]),
      h2('5.3 Service checks'),
      code(['curl -s https://<internal-api-host>/health',
            '# {"status":"ok","python":"3.11.9","database":"postgresql"}']),
      rich([{ t: '/health', code: true }, { t: ' reports process availability, the running interpreter version and which database engine is configured. It reads the connection string rather than the database, so it stays green while the database is unreachable — confirm the interpreter is the pinned 3.11 and the engine is postgresql, then perform a database read:' }]),
      code(['curl -s "https://<internal-api-host>/charts/search?page_size=1"']),
      h2('5.4 Functional verification'),
      step('Chart Library — locate a chart, open it, and confirm the page image renders'),
      step('PracticeLab — open an existing batch and confirm results and scores are displayed'),
      step('Assessment — open Analytics and confirm figures correspond to the source environment'),
      callout('Storage failures are not visible in list views', [
        'A migration in which the database is transferred and object storage is not produces an application that appears entirely functional: charts are listed, batches open, results display and analytics compute. Every chart image is broken.',
        [{ t: 'Verification must include opening a chart and confirming the page renders. Confirming that a chart appears in a list is not sufficient.', b: true }],
      ]),
      brk(),

      // ── 6. operations ────────────────────────────────────────────────────
      h1('6. Operational notes'),
      h2('6.1 Backups'),
      p('The application performs no backups. Two independent schedules are required:'),
      rbullet([{ t: 'PostgreSQL — ' }, { t: 'pg_dump', code: true }, { t: ' on a scheduled basis, daily being typical' }]),
      bullet('Object storage — bucket backup or replication, covering chart images'),
      p('Neither protects the other. A database backup contains no chart images; a bucket backup contains no records.'),
      h2('6.2 Deployments'),
      rich([{ t: 'Each release executes ' }, { t: 'init_db()', code: true },
             { t: ' again and applies any new additive migrations automatically. Following a deployment that alters the schema, inspect logs for ' },
             { t: 'Migration DDL failed', code: true }, { t: '.' }]),
      h2('6.3 Rollback'),
      p('Application rollback does not revert schema changes. Because migrations are additive, an earlier application revision will generally operate against a later schema, but this is not guaranteed and should be validated rather than assumed.'),
      h2('6.4 Sizing'),
      code(['SELECT COUNT(*) AS page_count FROM chart_files;']),
      p('Each row corresponds to one PNG object. Rendered chart pages are typically a few hundred kilobytes. Querying the bucket directly gives an exact figure and is preferable to estimation. The database itself is small: text, codes and JSON, with no binary content.'),
      brk(),

      // ── 7. decisions ─────────────────────────────────────────────────────
      h1('7. Decisions required'),
      p('The following must be determined before the migration is scheduled.'),
      table(
        ['#', 'Decision', 'Reference', 'Owner'],
        [
          ['1', 'PostgreSQL major version to provision', '4.4', ''],
          ['2', 'Storage backend selection, and re-point or transfer', '3.3, 4.5', ''],
          ['3', 'Custodianship and rotation policy for MASTER_ADMIN_PASSPHRASE', '4.2', ''],
          ['4', 'Front-end origin for CORS_ORIGINS', '4.2', ''],
          ['5', 'Backup schedule and retention for database and bucket', '6.1', ''],
          ['6', 'Network path from the backend to the selected storage', '3.3', ''],
        ],
        [500, 5300, 1560, 2000],
      ),
      p('A mismatched CORS_ORIGINS value produces a front end that loads successfully and fails every subsequent request; it is worth confirming explicitly rather than assuming a default.',
        { italics: true, color: GREY }),
    ]),
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('PracticeLab_Data_Architecture_and_Migration.docx', buf);
  console.log('written', buf.length, 'bytes');
});
