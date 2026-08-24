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


const TITLE = 'PracticeLab — Access Control Design';

const doc = new Document({
  creator: 'PracticeLab',
  title: TITLE,
  description: 'Roles, authentication and authorisation for the internal deployment',
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

new Paragraph({ spacing: { before: 2200 }, children: [] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 110 },
  children: [new TextRun({ text: 'PracticeLab', bold: true, size: 56, color: NAVY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 340 },
  children: [new TextRun({ text: 'Access Control Design', size: 30, color: ACCENT })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
  border: { top: { style: BorderStyle.SINGLE, size: 6, color: 'BFBFBF' } },
  children: [new TextRun({ text: '' })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 220, after: 90 },
  children: [new TextRun({ text: 'Roles · authentication · authorisation', size: 21, color: GREY, italics: true })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 90 },
  children: [new TextRun({ text: 'Audience: information security, identity and application engineers', size: 20, color: GREY })] }),
new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 560 },
  children: [new TextRun({ text: `Version 1.0  ·  ${BUILT}  ·  PROPOSAL, NOT YET BUILT`, size: 19, color: RED })] }),
brk(),

h1('About this document'),
p('PracticeLab trains and assesses medical coders. This document proposes how access to it should be controlled once it is running inside the organisation, and records the design decisions behind that proposal.'),
callout('Nothing described here is built yet', [
  'This is a design for review, not a description of the system. Section 1 states what the application does today, which is materially weaker, and should be read first.',
  [{ t: 'The measurements in section 1 were taken from the running application and are accurate as of the date on the cover.', b: true }],
]),
h2('Decisions already taken'),
p('Three questions were settled with the application owner before this design was written. They are recorded because the design depends on them, and changing any of them changes the answer.'),
table(['Question', 'Answer', 'Consequence'], [
  ['Do assessment scores carry consequences for the individual?', [{ t: 'Yes', b: true }], 'Verified identity becomes a correctness requirement, not a hardening measure. A shared or forwarded credential produces a falsified record.'],
  ['Do coders have corporate accounts?', [{ t: 'Yes', b: true }], 'Single sign-on against the corporate directory is viable and is the recommended mechanism.'],
  ['Are auditors a separate population from coders?', [{ t: 'Yes', b: true }], 'No person holds both roles, so roles are exclusive and permissions never compose.'],
], [3700, 1250, 4410]),

brk(),

h1('1. What the application does today'),
p('Measured against the running system rather than described from intent.'),
callout('There is no authentication of any kind', [
  'No login, no session cookie, no token validation on a route, no authentication dependency anywhere in the application. This was verified by searching for every common mechanism.',
  [{ t: 'Of roughly 200 API operations, about fifteen sit behind a single shared passphrase. The remainder are open to anyone who can reach the service.', b: true }],
]),
table(['Actor', 'What identifies them today', 'Strength'], [
  ['Coder', 'A name typed into browser storage. Nothing verifies it.', [{ t: 'None', b: true, color: RED }]],
  ['Practice / audit session', 'A token in the URL. No expiry column exists.', [{ t: 'Possession only', color: RED }]],
  ['Assessment sitting', 'A token in the URL, expiring after eight hours.', [{ t: 'Possession only', color: RED }]],
  ['Trainer', 'Knowledge of the URL. Nothing else.', [{ t: 'None', b: true, color: RED }]],
  ['Administrator', 'One shared passphrase, held by everyone who needs it.', 'Shared secret'],
], [2100, 4400, 2860]),

h2('1.1 What this means in practice'),
rbullet([{ t: 'Anyone who reaches a trainer URL can read every answer key.', b: true }, { t: ' In the auditor module they can read the planted errors, which does not merely leak answers — it voids the measurement the module exists to produce.' }]),
rbullet([{ t: 'A token proves possession, not identity.', b: true }, { t: ' An assessment link can be forwarded and sat by somebody else, and nothing in the application can detect it. Given the answer to question one above, that is a falsified record.' }]),
bullet('Every graded result attributes to a self-declared name and employee id. Two people can claim the same one.'),
bullet('Tokens travel in the URL, so they enter browser history and leak in any screenshot.'),

h2('1.2 One control that does work'),
p('Retiring a chart genuinely revokes access to it: both the chart record and its page images return 404 afterwards, so a saved link stops working. Chart page images are also served as pre-signed URLs that expire after one hour.'),

brk(),

h1('2. What is worth protecting'),
p('Ranked by what is lost if it leaks, rather than by convention. This ranking drives the sequence in section 6.'),
table(['#', 'Asset', 'Consequence of exposure', 'Protected today'], [
  ['1', [{ t: 'Answer keys and planted errors', b: true }], 'Scores across every module become meaningless. In the auditor module the planted-error list destroys the restraint measurement the module was built for.', [{ t: 'No', b: true, color: RED }]],
  ['2', [{ t: 'The assessment question bank', b: true }], 'Questions are reused across cohorts, so a single leak contaminates every future sitting.', 'Passphrase'],
  ['3', 'Individual results and analytics', 'One coder sees another\'s performance. Damaging to trust, not to integrity.', [{ t: 'No', color: RED }]],
  ['4', 'The chart library', 'Charts are de-identified, and browsing them is a study activity. Lowest of the four.', 'Partly'],
], [600, 2300, 4600, 1860]),

brk(),

h1('3. Roles'),
p('Four roles. Each is stated as a single rule, because a permission model that cannot be summarised in one line cannot be reviewed.'),
table(['Role', 'Rule', 'Notes'], [
  [[{ t: 'Participant', b: true }], 'Sees only the sessions assigned to them.', 'Covers coders and auditors alike. Both workflows are the same shape — work is assigned, done, submitted — so which kind of session appears follows from the assignment rather than the role.'],
  [[{ t: 'Manager', b: true }], 'Read-only analytics for PracticeLab, Auditor and Assessment. No answer keys.', 'Spans modules but reaches none of their controls. See section 4.'],
  [[{ t: 'Trainer', b: true }], 'Full operational access.', 'Charts, answer keys, batches, allocation, grading, assessment generation.'],
  [[{ t: 'Administrator', b: true }], 'Trainer, plus destructive operations.', 'Retire and delete, force-close, reopen, question bank edits.'],
], [1700, 3100, 4560]),

callout('Why coders and auditors share one role', [
  'They are separate populations, but the access RULE is identical: see what is assigned to you. Keeping them as one role means a person who moves from coding to auditing needs no permission change — they simply begin receiving different assignments. A separate auditor role would have made that a provisioning task, and provisioning tasks are forgotten.',
  'The directory may still hold separate groups for the two, for provisioning and reporting. Those groups would not be performing authorisation, and it is worth stating that explicitly so nobody later assumes they are.',
], 'info'),

brk(),

h1('4. The manager role in detail'),
p('This role was specified late and is the most easily got wrong, because the obvious rules are subtly unsafe.'),

h2('4.1 It maps cleanly onto the API'),
rich([{ t: 'The application exposes ' }, { t: '48', b: true }, { t: ' analytics endpoints. Every one of them is a ' }, { t: 'GET', code: true }, { t: '. None mutates anything, so a read-only role is not fighting the architecture.' }]),

h2('4.2 But "reports are read-only" is not a safe rule'),
p('Five of the thirty report and export endpoints hand over answers:'),
code([
  '/practicelab/answer-key/export',
  '/auditor/keys/export                <-- the planted errors',
  '/assessment/questions/export',
  '/assessment/questions/export-all',
  '/assessment/{id}/export-answer-key',
]),
callout('A manager is the role with a motive', [
  'The team\'s numbers are the thing being measured, and the manager is measured on them. This is not a statement about any individual — it is the reason the role should be defined so that the question can never arise.',
  [{ t: '/auditor/keys/export', code: true }, { t: ' is the sharpest case: it returns the planted errors. A manager holding it could tell their team what to look for, and every audit score afterwards would be worthless.' }],
]),

h2('4.3 The rule'),
bullet('Allow: all 48 analytics endpoints.'),
bullet('Allow: the 25 report and export endpoints that do not reveal answers, including the per-coder reports and matrices.'),
rbullet([{ t: 'Deny: the five endpoints listed above.', b: true }]),
rbullet([{ t: 'Deny: everything that writes, without exception.', b: true }]),
p('Chart Library analytics is excluded from the role. It reports most-viewed and least-viewed charts and a count by specialty — a librarian\'s view of the collection, containing no coder and no score. A manager has no use for it, and excluding it removes an entire module from the role\'s surface.'),

h2('4.4 Navigation'),
p('Analytics currently sits inside the trainer screens, behind tabs. Filtering those tabs per role is possible — all four modules declare their tabs as lists — but it is the weaker design: it fails open the next time somebody adds a tab and forgets to exclude it, and it lands the manager on a default tab they are not allowed to see.'),
rich([{ t: 'A separate manager home, with one card per analytics surface, fails closed instead: the manager path never touches a trainer screen, so a new tab is excluded by default rather than by memory.', b: true }]),
callout('Hiding is not a control', [
  'Hidden tabs are presentation. The boundary must be the API refusing the request. The interface work exists so a manager never meets a control they cannot use; the server work exists so that it would not matter if they did.',
]),

brk(),

h1('5. Authentication'),
h2('5.1 Single sign-on'),
p('Because all four populations hold corporate accounts, one integration against the corporate identity provider serves every role. Roles follow from directory group membership, so joiners and leavers are handled by the process that already exists rather than by a second one inside this application.'),
table(['Item', 'Recommendation'], [
  ['Protocol', 'OpenID Connect. SAML is acceptable if it is the organisational standard.'],
  ['Directory groups required', 'Four, one per role. Provisioning these is usually the longest lead time — raise it early.'],
  ['Role source', 'A group claim in the token. The application maps group to role and stores nothing about permissions itself.'],
  ['Unauthenticated exceptions', [{ t: '/health', code: true }, { t: ' only, so that platform monitoring and the deployment smoke test continue to work.' }]],
], [2900, 6460]),

h2('5.2 What happens to the existing tokens'),
rich([{ t: 'The session token stops being a credential and becomes an ' }, { t: 'assignment reference', b: true }, { t: ' — it says which work is yours, not who you are. This removes the forwarding problem outright, because the link is worthless to anyone who cannot sign in as its owner, and it preserves the existing session machinery rather than discarding it.' }]),

h2('5.3 What single sign-on does not solve'),
p('It verifies who signed in. It cannot prevent somebody signing in and then handing over the keyboard. Where an assessment score carries a consequence, that gap is real and closing it requires proctoring — an invigilator, a lockdown browser, or camera supervision — which is a separate decision about the training programme rather than about this application.'),
p('Requiring re-authentication at the point of submission is a cheaper middle ground. It is not proctoring, but it raises the effort and produces a record.'),

brk(),

h1('6. Sequence'),
p('Ordered by value delivered per unit of work, and by what can proceed independently.'),
table(['#', 'Step', 'Why here', 'Depends on'], [
  ['1', [{ t: 'Trainer authentication', b: true }], 'The only thing standing between a coder and every answer key is currently knowledge of a URL. Highest value, smallest surface, independent of everything else. A shared trainer password is an acceptable stopgap for the period before single sign-on lands.', 'Nothing'],
  ['2', [{ t: 'Session expiry', b: true }], 'Done. Recorded here because it was part of this design. See section 7.', 'Nothing'],
  ['3', [{ t: 'Single sign-on and roles', b: true }], 'Replaces typed names with verified identity and makes every later control meaningful. The manager role should be built here rather than before, since it needs roles to exist.', 'Directory groups; migration'],
  ['4', [{ t: 'Participant chart scoping', b: true }], 'Restricting the library to assigned charts. Genuinely the least urgent of these, and it needs a decision on whether the library is a study resource.', 'Roles'],
], [600, 2200, 5300, 1260]),

brk(),

h1('7. Already implemented'),
p('One part of this design is built and deployed, and is recorded here so the document describes the system accurately.'),
h2('7.1 A session ends when its batch closes'),
p('Practice and audit tokens had no expiry and never have had. A timer was considered and rejected: tokens are distributed days before the work begins, a batch runs for days rather than for one sitting, and any fixed duration would either expire mid-batch or be long enough to protect nothing.'),
rich([{ t: 'Closing a batch is already a deliberate trainer action meaning ' }, { t: 'the work is done', i: true }, { t: ', so it is the honest place for access to end. The auditor module already enforced this. PracticeLab did not: its four checks were all trainer-side, and a coder\'s own submission was never gated, so a token could still write results into a batch whose results had already become the record.' }]),
callout('The write ends; the reading does not', [
  'An expired token still opens its own feedback. A coder who cannot see how they did has lost the point of the exercise, and that distinction is what keeps this a control rather than an irritation.',
  'Reopening a batch already exists behind the master passphrase, so the way back is unchanged.',
], 'info'),

h1('8. Open questions'),
table(['#', 'Question', 'Why it matters'], [
  ['1', 'Is the chart library a study resource coders may browse freely, or only a delivery mechanism for assigned work?', 'Determines whether step 4 should be built at all. This is a decision about training design, not about technology.'],
  ['2', 'Should managers see individual coders, or only aggregates?', 'Currently answered as individuals. If it changes to team-scoped, the application has no concept of teams and the work is substantially larger.'],
  ['3', 'Is there a period after migration when the application is reachable beyond the internal network?', 'Determines how much the interim stopgap in step 1 has to carry.'],
  ['4', 'Do historical results need reconciling to verified identities?', 'Existing rows carry self-declared names. Mixing verified and self-declared attribution in one analytics view, without marking which is which, is its own quiet trap.'],
], [600, 4200, 4560]),

    ]),
  }],
});

Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync('PracticeLab_Access_Control_Design.docx', buf);
  console.log('written', buf.length, 'bytes');
});
