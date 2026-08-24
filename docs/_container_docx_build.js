// Dated when it is built, not when someone remembered to change the string.
// A regenerated document carrying an old date is worse than an undated one:
// the reader has no way to tell it was refreshed.
const BUILT = new Date().toLocaleDateString('en-GB',
  { day: 'numeric', month: 'long', year: 'numeric' });

const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, ShadingType, BorderStyle,
  PageBreak, LevelFormat, Footer, PageNumber,
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


const TITLE = 'PracticeLab — Container Deployment Guide';

const doc = new Document({
  creator: 'PracticeLab',
  title: TITLE,
  description: 'Building, configuring, running and verifying the container image',
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
  children: [new TextRun({ text: 'Container Deployment Guide', size: 30, color: ACCENT })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
  children: [new TextRun({ text: '' })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
  children: [new TextRun({ text: 'Build · configure · run · verify · update', size: 21, color: GREY, italics: true })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
  children: [new TextRun({ text: 'Audience: infrastructure and platform engineers', size: 20, color: GREY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
  children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}`, size: 19, color: GREY })] }),
brk(),

// ── about ───────────────────────────────────────────────────────────────────
h1('About this document'),
p('PracticeLab is a web application for training and assessing medical coders. This guide covers running it from the container image defined by the Dockerfile at the repository root: what the image contains, how to build and configure it, what happens when it starts, how to confirm it is genuinely working, and how to deploy a later version.'),
p('It assumes no familiarity with the application. It does not cover the database migration itself, which has its own document, nor application features or grading rules.'),
callout('Everything here has been executed', [
  'The procedures and outputs in this guide are not written from the Dockerfile — the image was built, started, and exercised, and the values quoted are the values it returned. Where a failure is described, it is a failure that was actually produced.',
], 'info'),

h2('Related documents'),
table(['Document', 'What it covers'], [
  ['Data Architecture and Migration Specification', 'The database schema, object storage, and the dump-and-restore procedure. Read it first — the database must exist before the container is useful.'],
  ['Database Schema Reference', 'Every table and column.'],
], [3400, 5960]),

brk(),

// ── 1 ───────────────────────────────────────────────────────────────────────
h1('1. What the image contains'),
p('The application is normally two pieces: a Python API and a compiled JavaScript interface. The image contains both, served by one process on one port. There is nothing to install on the host and nothing to build.'),

h2('1.1 Inside the image'),
bullet('Python 3.11.9 and the fourteen backend packages.'),
bullet('The compiled front end, built during the image build.'),

h2('1.2 Deliberately outside the image'),
table(['Not included', 'Why'], [
  [[{ t: 'The database', b: true }], 'PostgreSQL is a separate service. A container is disposable; your data is not. This is what makes the image safe to replace, scale and roll back.'],
  [[{ t: 'Chart page images', b: true }], 'Held in S3-compatible object storage, also external.'],
  [[{ t: 'Node.js', b: true }], 'The front end is compiled in a build stage that is then discarded. Roughly 172 MB of build tooling never reaches the server that runs this.'],
], [2600, 6760]),

h2('1.3 Properties a platform team will ask about'),
table(['Property', 'Value'], [
  ['Approximate size', '523 MB'],
  ['Listens on', 'Port 8000'],
  ['Runs as', [{ t: 'uid 10001', code: true }, { t: ' (', }, { t: 'practicelab', code: true }, { t: ') — not root' }]],
  ['Persistent state', 'None. The container is stateless and scales horizontally'],
  ['Health endpoint', [{ t: 'GET /health', code: true }, { t: ' — also wired as the image HEALTHCHECK' }]],
  ['Writable paths needed', [{ t: '/tmp', code: true }, { t: ' only. The filesystem may otherwise be mounted read-only' }]],
], [2600, 6760]),

brk(),

// ── 2 ───────────────────────────────────────────────────────────────────────
h1('2. Before you start'),
table(['Requirement', 'Notes'], [
  ['A container runtime', 'Docker, Podman, Kubernetes, OpenShift — any OCI-compatible platform. The commands in this guide use Docker; translate as needed.'],
  [[{ t: 'PostgreSQL 15 or later', b: true }], 'Restore the supplied database dump into it before starting the container. See the Migration Specification.'],
  [[{ t: 'S3-compatible object storage', b: true }], 'Holds every chart page image. Cloudflare R2, AWS S3, MinIO, Ceph, ECS and StorageGRID all work.'],
], [2900, 6460]),

callout('Storage failures are invisible in the interface', [
  'The application starts perfectly well with wrong or missing storage credentials. Charts list, batches open, results display, analytics compute — and every chart image is broken.',
  [{ t: 'Verification must include opening a chart and confirming the page renders. Seeing a chart in a list proves only the database.', b: true }],
]),

brk(),

// ── 3 ───────────────────────────────────────────────────────────────────────
h1('3. Building the image'),
p('Run from the repository root, where the Dockerfile sits:'),
code([
  'docker build \\',
  '  --platform linux/amd64 \\',
  '  --build-arg BUILD_REF=$(git rev-parse --short HEAD) \\',
  '  -t practicelab:1.0 .',
]),

h2('3.1 The two arguments that matter'),
rich([{ t: '--platform linux/amd64', code: true }, { t: ' — required only when the image is built on an Apple Silicon Mac and run on ordinary x86 servers. Omit it when building on the same architecture you will run on. An image built for the wrong architecture fails at start, not at build.' }]),
rich([{ t: 'BUILD_REF', code: true }, { t: ' — stamped into the image and reported by ' }, { t: '/health', code: true }, { t: '. This is what makes “which version is running?” a question with an answer rather than something inferred from behaviour. Any meaningful string will do: a commit hash, a release number.' }]),

h2('3.2 If your policy requires an approved base image'),
rich([{ t: 'Change the two ' }, { t: 'FROM', code: true }, { t: ' lines. Nothing else in the file depends on them. The build stage needs Node 20; the runtime stage needs Python 3.11.' }]),
callout('The Python version is not negotiable', [
  'This code is tested on Python 3.9 and 3.11 only. It has already been broken once by a host silently building it on 3.14 — a fault that stayed invisible until a stack trace happened to show the interpreter path.',
  [{ t: 'Putting the interpreter inside the image is the point of this exercise: it is the only pin that cannot be overridden by a host setting.', b: true }],
]),

brk(),

// ── 4 ───────────────────────────────────────────────────────────────────────
h1('4. Configuration'),
p('Nine environment variables. Six have no default and the application will refuse to start without them. That is deliberate: a silent start on half a configuration is worse than a clear failure.'),

table(['Variable', 'Required', 'Notes'], [
  [[{ t: 'DATABASE_URL', code: true }], [{ t: 'Yes', b: true }], [{ t: 'postgresql://user:pass@host:5432/practicelab', code: true }, { t: '. The postgres:// and postgresql+asyncpg:// forms are also accepted and normalised.' }]],
  [[{ t: 'MASTER_ADMIN_PASSPHRASE', code: true }], [{ t: 'Yes', b: true }], 'The single shared credential gating chart retirement, deletion, force-close and the question bank. Treat as a secret; rotate through your normal process.'],
  [[{ t: 'STORAGE_ENDPOINT_URL', code: true }], [{ t: 'Yes', b: true }], 'Object storage endpoint.'],
  [[{ t: 'STORAGE_ACCESS_KEY', code: true }], [{ t: 'Yes', b: true }], 'Scope the credential to this one bucket.'],
  [[{ t: 'STORAGE_SECRET_KEY', code: true }], [{ t: 'Yes', b: true }], ''],
  [[{ t: 'STORAGE_BUCKET_NAME', code: true }], [{ t: 'Yes', b: true }], 'Bucket holding chart page images.'],
  [[{ t: 'STORAGE_PUBLIC_URL', code: true }], 'No', 'Must be present but is currently unread. Any value.'],
  [[{ t: 'CORS_ORIGINS', code: true }], 'No', [{ t: 'Not needed in this deployment.', b: true }, { t: ' One container serves the interface and the API from the same origin, so the browser never makes a cross-origin request.' }]],
  [[{ t: 'FRONTEND_URL', code: true }], 'No', 'Used only when generating links.'],
], [2700, 1100, 5560]),

callout('Keep them in a file, not on the command line', [
  'Values passed as arguments appear in shell history and in process listings. An env-file keeps the passphrase and the storage keys out of both.',
], 'info'),

brk(),

// ── 5 ───────────────────────────────────────────────────────────────────────
h1('5. Running it'),
code([
  'docker run -d --name practicelab \\',
  '  -p 8000:8000 \\',
  '  --env-file /etc/practicelab/practicelab.env \\',
  '  --restart unless-stopped \\',
  '  practicelab:1.0',
]),

h2('5.1 Behind a reverse proxy'),
p('Nothing special is required. The application serves the interface and the API from one origin, so there is no path rewriting to configure — proxy everything to port 8000.'),

h2('5.2 Running more than one replica'),
p('The container holds no session state, so it scales horizontally. Every replica runs the startup migrations described in the next section; those are idempotent and guarded, so this is safe. Staggering starts avoids duplicate log noise.'),

brk(),

// ── 6 ───────────────────────────────────────────────────────────────────────
h1('6. What happens at startup'),
p('The application runs its own schema migrations on every start, not only the first. There is no separate migration step to schedule and no migration tool to install.'),
p('Migrations are additive: they create tables and add columns, and never drop or rewrite. An older image will therefore normally run against a newer schema, which is what makes rollback safe.'),

h2('6.1 Migration failures are logged, not fatal'),
rich([{ t: 'A migration that fails is recorded and startup continues. After any upgrade, search the logs for:' }]),
code(['Migration DDL failed']),
p('On a correctly configured database this must not appear. Any occurrence should be investigated before the environment is accepted.'),

h2('6.2 One ordering rule'),
rich([{ t: 'If the ' }, { t: 'assessment_questions', code: true }, { t: ' table is empty at startup, the application seeds a set of sample questions.' }]),
callout('Restore the database first, then start the container', [
  [{ t: 'Restore, then start', b: true }, { t: ' — the table is already populated, seeding is skipped. Correct.' }],
  [{ t: 'Start, then restore', b: true }, { t: ' — seeded rows are present and the restore fails on duplicate keys.' }],
  'If the container has already been started against an empty database, drop and recreate the database before restoring.',
]),

brk(),

// ── 7 ───────────────────────────────────────────────────────────────────────
h1('7. Verifying the deployment'),
p('This section is the reason the guide exists. The application does not fail loudly when it is misconfigured — it degrades to silence, and a broken environment looks like a working one.'),

h2('7.1 The quick check'),
code(['curl -s http://localhost:8000/health']),
code(['{"status":"ok","python":"3.11.9","database":"postgresql",', ' "build":"51ba232","serving_ui":true}']),
p('Read all four fields. Each has a failure meaning:'),
table(['Field', 'Expected', 'If it says otherwise'], [
  [[{ t: 'python', code: true }], [{ t: '3.11.x', code: true }], 'The image was not built from this Dockerfile.'],
  [[{ t: 'database', code: true }], [{ t: 'postgresql', code: true }], [{ t: 'sqlite', code: true }, { t: ' means DATABASE_URL never reached the container. The application is writing to a temporary file and will lose everything on restart — while appearing entirely healthy.', b: true }]],
  [[{ t: 'build', code: true }], 'Your BUILD_REF', 'A different version is running than the one you deployed.'],
  [[{ t: 'serving_ui', code: true }], [{ t: 'true', code: true }], 'The image is serving the API only; the interface will not load.'],
], [1900, 1900, 5560]),

rich([{ t: '/health', code: true }, { t: ' reads configuration, not the database. It stays green while the database is unreachable, so treat it as a liveness check and not a readiness one.' }]),

h2('7.2 The real check'),
rich([{ t: '/health', code: true }, { t: ' proves the process is up and nothing more. The supplied smoke script exercises the running service instead:' }]),
code([
  'python3 scripts/smoke_deployed.py --base http://localhost:8000 \\',
  "  --write --passphrase 'YOUR_PASSPHRASE'",
]),
p('It uses only the Python standard library, so it runs on a locked-down host with nothing installed, and exits non-zero on any failure so it can gate a deployment.'),
callout('Use --write', [
  'This application degrades to silence rather than erroring, so read-only checks pass against a database that cannot be written to. That is not hypothetical: it is exactly how an entire module was unwritable in the hosted environment while every read-only check reported healthy.',
  'The write check stores one record and removes it again. A run that is asked for --write and cannot perform one fails rather than skipping.',
]),

h2('7.3 What a misconfigured start actually looks like'),
p('Worth seeing once, because none of it is an error message. This is a real run against a container started without a valid database URL, in an environment where the reference code sets had never been loaded:'),
code([
  '  ok   running the pinned Python (3.11)',
  '  FAIL talking to PostgreSQL — database reports sqlite',
  '  ok   charts',
  '  ok   practicelab batches',
  '  ok   auditor batches',
  "  FAIL J18.9 has a description — got 200 {'descriptions': {}, ...}",
  '',
  '  12 checks, 2 failed',
]),
p('Every read path passes. The application is up, serving and answering — while writing to a file it will lose on restart, and rendering every code description as blank. Neither condition surfaces anywhere in the interface.'),

h2('7.4 Then look at it'),
step('Open the address in a browser and confirm the interface loads.'),
step('Open a chart and confirm the page image renders. This is the storage check, and the one most likely to fail.'),
step('Open an existing batch and confirm results and scores display.'),
step('Open Analytics and confirm the figures match the source environment.'),

brk(),

// ── 8 ───────────────────────────────────────────────────────────────────────
h1('8. Deploying a new version'),
p('The routine for every subsequent release:'),
code([
  'docker build --platform linux/amd64 \\',
  '  --build-arg BUILD_REF=$(git rev-parse --short HEAD) \\',
  '  -t practicelab:1.1 .',
  'docker stop practicelab && docker rm practicelab',
  'docker run -d --name practicelab -p 8000:8000 \\',
  '  --env-file /etc/practicelab/practicelab.env \\',
  '  --restart unless-stopped practicelab:1.1',
  'curl -s http://localhost:8000/health',
]),
rich([{ t: 'Confirm the ' }, { t: 'build', code: true }, { t: ' field reports the version you just deployed. There is no database step: schema changes travel inside the image and apply themselves at startup.' }]),

h2('8.1 Rolling back'),
p('Run the previous image tag. Because migrations only add and never remove, the older application will normally run against the newer schema — but validate rather than assume, and keep the previous tag until the new one has been accepted.'),

brk(),

// ── 9 ───────────────────────────────────────────────────────────────────────
h1('9. Reference code sets'),
p('ICD-10-CM, ICD-10-PCS, HCPCS Level II and the MS-DRG CC/MCC list — roughly 186,000 rows — are loaded by hand, once, per environment:'),
code(['python3 scripts/ingest_code_sets.py --write']),
p('Nothing calls this automatically, and deliberately so: it downloads several megabytes from cms.gov, and attaching that to startup would make every deployment slow and a CMS outage a failed start.'),
rich([{ t: 'Everything that reads this data degrades to silence, so an environment where it was never loaded is indistinguishable from one where the feature does not exist. ' }, { t: 'GET /codes/status', code: true }, { t: ' reports what is present. Use ' }, { t: '--from-dir', code: true }, { t: ' to load from local files where there is no route to cms.gov.' }]),

h1('10. Troubleshooting'),
table(['Symptom', 'Cause and remedy'], [
  ['Container exits immediately at start', 'One of the six required environment variables is missing. The log names it. This is intended behaviour, not a fault.'],
  [[{ t: '/health', code: true }, { t: ' reports ' }, { t: 'database: sqlite', code: true }], [{ t: 'DATABASE_URL', code: true }, { t: ' did not reach the container. Data written since it started is in a temporary file and will be lost.' }]],
  ['Interface loads but every chart image is broken', 'Object storage credentials are wrong, or the keys were altered during transfer. Object keys must be preserved exactly; a transfer that adds a prefix breaks every chart with no error.'],
  ['Restore fails on duplicate keys', 'The container was started before the restore and seeded sample questions. Drop and recreate the database, then restore, then start.'],
  ['Code descriptions render blank everywhere', 'The reference code sets were never ingested in this environment. See section 9.'],
  [[{ t: 'Migration DDL failed', code: true }, { t: ' in the logs' }], 'A schema migration did not apply. Startup continued regardless, so the application is running against an incomplete schema. Investigate before accepting the environment.'],
  ['Image will not start on the server', 'Built for the wrong architecture. Rebuild with --platform linux/amd64.'],
], [3000, 6360]),

    ]),
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('PracticeLab_Container_Deployment.docx', buf);
  console.log('written', buf.length, 'bytes');
});
