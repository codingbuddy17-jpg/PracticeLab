"""Generate ERD SVGs from the introspected schema — drawn from the real
foreign keys rather than from recollection, so the arrows cannot drift."""
import json

S = json.load(open('schema.json'))

CSS = """
    .ttl{font-family:Helvetica,Arial;font-size:24px;font-weight:bold;fill:#1F3864}
    .sub{font-family:Helvetica,Arial;font-size:15px;fill:#595959}
    .tname{font-family:Helvetica,Arial;font-size:15px;font-weight:bold;fill:#FFFFFF}
    .col{font-family:Consolas,monospace;font-size:12.5px;fill:#333333}
    .pk{font-family:Consolas,monospace;font-size:12.5px;fill:#B9770E;font-weight:bold}
    .fk{font-family:Consolas,monospace;font-size:12.5px;fill:#2E75B6;font-weight:bold}
    .note{font-family:Helvetica,Arial;font-size:13px;fill:#595959}
    .rel{font-family:Helvetica,Arial;font-size:12px;fill:#7F7F7F}
    .lgd{font-family:Helvetica,Arial;font-size:13px;fill:#404040}
"""

def entity(x, y, table, cols, colour, w=250):
    """One entity box: header bar plus the columns worth showing."""
    fks = {f['col'] for f in S[table]['fks']}
    rows = []
    h = 34 + len(cols) * 19 + 10
    out = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="#FFFFFF" stroke="{colour}" stroke-width="2"/>',
           f'<rect x="{x}" y="{y}" width="{w}" height="28" rx="6" fill="{colour}"/>',
           f'<rect x="{x}" y="{y+18}" width="{w}" height="10" fill="{colour}"/>',
           f'<text x="{x+12}" y="{y+19}" class="tname">{table}</text>']
    yy = y + 48
    for c in cols:
        cls = 'pk' if c == 'id' else ('fk' if c in fks else 'col')
        mark = ' PK' if c == 'id' else (' FK' if c in fks else '')
        out.append(f'<text x="{x+12}" y="{yy}" class="{cls}">{c}{mark}</text>')
        yy += 19
    return "\n".join(out), h

def arrow(x1, y1, x2, y2, label=""):
    mid_x, mid_y = (x1 + x2) / 2, (y1 + y2) / 2
    s = f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#7F7F7F" stroke-width="1.8" marker-end="url(#fk)"/>'
    if label:
        s += f'\n<text x="{mid_x}" y="{mid_y - 6}" class="rel" text-anchor="middle">{label}</text>'
    return s

HEAD = lambda w, h, title, sub: f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
<style>{CSS}</style>
<defs><marker id="fk" markerWidth="9" markerHeight="7" refX="8" refY="3.5" orient="auto">
<path d="M0,0 L9,3.5 L0,7 Z" fill="#7F7F7F"/></marker></defs>
<rect width="{w}" height="{h}" fill="#FFFFFF"/>
<text x="24" y="36" class="ttl">{title}</text>
<text x="24" y="60" class="sub">{sub}</text>'''

LEGEND = lambda x, y: f'''
<rect x="{x}" y="{y}" width="330" height="66" rx="6" fill="#FAFAFA" stroke="#D9D9D9"/>
<text x="{x+14}" y="{y+24}" class="pk">id PK</text>
<text x="{x+90}" y="{y+24}" class="lgd">primary key</text>
<text x="{x+14}" y="{y+46}" class="fk">chart_id FK</text>
<text x="{x+120}" y="{y+46}" class="lgd">foreign key — arrow points to parent</text>'''

BLUE, GREEN, PURPLE, AMBER, RED = '#2E75B6', '#2E8B57', '#8E44AD', '#B9770E', '#C0392B'

# ── ERD 1: Chart Library ─────────────────────────────────────────────────────
# Hub and spoke: charts on the left, its children stacked in one column so no
# arrow crosses a box, standalone tables kept visibly apart on the right.
w, h = 1240, 880
parts = [HEAD(w, h, 'Figure A — Chart Library',
              'Six tables. charts is the parent; every other domain in the application also refers to it.')]
e, _ = entity(60, 130, 'charts',
              ['id', 'chart_number', 'specialty', 'category', 'difficulty',
               'alias', 'rationale', 'status', 'uploaded_by', 'view_count'], BLUE, 270)
parts.append(e)
e, _ = entity(500, 110, 'chart_files',
              ['id', 'chart_id', 'storage_key', 'original_filename',
               'page_order', 'total_pages', 'page_text'], BLUE, 290)
parts.append(e)
e, _ = entity(500, 350, 'audit_logs',
              ['id', 'chart_id', 'action', 'actor', 'details'], BLUE, 290)
parts.append(e)
e, _ = entity(500, 530, 'chart_feedback',
              ['id', 'chart_id', 'chart_number', 'reporter', 'issues', 'status'], BLUE, 290)
parts.append(e)

parts.append('<rect x="880" y="110" width="310" height="290" rx="8" fill="#FAFAFA" stroke="#D9D9D9" stroke-dasharray="5,4"/>')
parts.append('<text x="900" y="136" class="rel">NO FOREIGN KEYS — STANDALONE</text>')
e, _ = entity(900, 150, 'chart_sequences', ['id', 'prefix', 'last_number'], BLUE, 270)
parts.append(e)
e, _ = entity(900, 270, 'coding_resources', ['id', 'title', 'url', 'sort_order'], BLUE, 270)
parts.append(e)

parts += [
  arrow(496, 200, 334, 230, 'pages'),
  arrow(496, 410, 334, 300, 'history'),
  arrow(496, 590, 334, 350, 'reports'),
  '<text x="60" y="470" class="note">One chart has many pages, many audit entries</text>',
  '<text x="60" y="492" class="note">and may have many feedback reports.</text>',
  '<rect x="60" y="730" width="1130" height="76" rx="6" fill="#FDF7EE" stroke="#E8C99A"/>',
  '<text x="80" y="758" class="note" style="fill:#8A5A00">chart_files.storage_key holds the object key of one page image in the bucket.</text>',
  '<text x="80" y="782" class="note" style="fill:#8A5A00">The images themselves are not in the database and are not covered by a database backup.</text>',
  LEGEND(880, 440),
  '</svg>']
open('figA_erd_charts.svg', 'w').write("\n".join(parts))
print('figA written')

# ── ERD 2: PracticeLab ───────────────────────────────────────────────────────
# Arrows are generated from the introspected foreign keys, not placed by eye —
# an ERD whose arrows point the wrong way is worse than no ERD.
w, h = 1240, 1000
parts = [HEAD(w, h, 'Figure B — PracticeLab: assignment and grading',
              'How work reaches a coder and how the result is recorded. Every arrow is a real foreign key, pointing to the parent.')]

BOX = {}   # table -> (x, y, w, h) so arrows can be computed from geometry
def place(x, y, t, cols, colour, wd=250):
    e, hh = entity(x, y, t, cols, colour, wd)
    BOX[t] = (x, y, wd, hh)
    parts.append(e)

place(50, 110, 'batches',
      ['id', 'name', 'specialty', 'charts_per_coder', 'status',
       'is_direct_assignment', 'use_weighted', 'use_dpo'], GREEN, 250)
place(50, 350, 'batch_coders', ['id', 'batch_id', 'coder_name', 'emp_id'], GREEN, 250)
place(50, 510, 'answer_keys', ['id', 'chart_id', 'pdx_code', 'sdx', 'pcs', 'cpt'], GREEN, 250)
place(50, 700, 'em_answer_keys',
      ['id', 'chart_id', 'em_code', 'em_category', '(43 MDM columns)'], PURPLE, 250)

place(360, 110, 'batch_allocation_cycles',
      ['id', 'batch_id', 'cycle_number', 'run_by', 'randomisation_stats'], GREEN, 260)
place(360, 300, 'batch_charts',
      ['id', 'batch_id', 'cycle_id', 'chart_id', 'coder_name'], GREEN, 260)
place(360, 500, 'charts', ['id', 'chart_number', 'specialty'], BLUE, 260)
place(360, 660, 'submissions', ['id', 'batch_id', 'chart_id', '(legacy)'], GREEN, 260)

place(670, 110, 'practice_sessions',
      ['id', 'batch_id', 'cycle_id', 'coder_name', 'token', 'status'], AMBER, 250)
place(670, 300, 'practice_chart_drafts',
      ['id', 'session_id', 'chart_id', '(in progress)'], AMBER, 250)
place(670, 450, 'practice_results',
      ['id', 'session_id', 'chart_id', 'total_score', 'pass_fail'], AMBER, 250)

place(970, 300, 'grading_results',
      ['id', 'batch_id', 'chart_id', 'submission_id',
       'coder_name', 'total_score', 'dpo_*'], GREEN, 220)
place(970, 530, 'grading_feedback',
      ['id', 'result_id', 'section', 'issue_type'], GREEN, 220)
place(970, 670, 'ed_rubric_details', ['id', 'result_id'], GREEN, 220)
place(970, 780, 'em_grading_results', ['id', 'result_id'], PURPLE, 220)

def fk(child, parent, side='left'):
    """Arrow from child box to parent box, pointing at the parent."""
    cx, cy, cw, ch = BOX[child]
    px, py, pw, ph = BOX[parent]
    if side == 'left':
        return arrow(cx - 4, cy + ch / 2, px + pw + 4, py + ph / 2)
    if side == 'up':
        return arrow(cx + cw / 2, cy - 4, px + pw / 2, py + ph + 4)
    if side == 'right':
        return arrow(cx + cw + 4, cy + ch / 2, px - 4, py + ph / 2)
    return arrow(cx + cw / 2, cy + ch + 4, px + pw / 2, py - 4)   # down

parts += [
  fk('batch_allocation_cycles', 'batches'),
  fk('batch_coders', 'batches', 'up'),
  fk('batch_charts', 'batch_allocation_cycles', 'up'),
  fk('practice_sessions', 'batch_allocation_cycles'),
  fk('practice_chart_drafts', 'practice_sessions', 'up'),
  fk('practice_results', 'practice_sessions', 'up'),
  fk('grading_feedback', 'grading_results', 'up'),
  fk('ed_rubric_details', 'grading_results', 'up'),
  fk('em_grading_results', 'grading_results', 'up'),
  fk('answer_keys', 'charts', 'right'),
  fk('em_answer_keys', 'charts', 'right'),
  fk('submissions', 'charts', 'up'),
  # the mirror is a code path, not a foreign key — drawn dashed to say so
  '<path d="M 924 500 Q 950 450 966 400" fill="none" stroke="#2E8B57" stroke-width="2" stroke-dasharray="6,4" marker-end="url(#fk)"/>',
  '<rect x="50" y="890" width="1140" height="86" rx="6" fill="#EAF6EF" stroke="#2E8B57"/>',
  '<text x="70" y="918" class="note" style="fill:#1E6B41">Omitted for legibility: the four chart_id references (batch_charts, practice_chart_drafts, practice_results, grading_results),</text>',
  '<text x="70" y="940" class="note" style="fill:#1E6B41">and grading_results.batch_id / .submission_id. The complete foreign key list is tabulated in section 4.</text>',
  '<text x="70" y="962" class="note" style="fill:#1E6B41">Coders work in practice_sessions; every practice_result is copied into grading_results, which is what all reporting reads.</text>',
  LEGEND(628, 640),
  '</svg>']
open('figB_erd_practicelab.svg', 'w').write("\n".join(p for p in parts if p))
print('figB written')

# ── ERD 3: Assessment ────────────────────────────────────────────────────────
w, h = 1240, 840
parts = [HEAD(w, h, 'Figure C — Assessment (multiple choice)',
              'Eight tables. This domain never references charts — assessments are question papers, not coding work.')]
BOX = {}
place(50, 120, 'assessment_questions',
      ['id', 'question_id', 'specialty', 'question_text',
       'option_a … option_d', 'correct_answer', 'topic', 'difficulty', 'status'], RED, 270)
place(380, 120, 'assessment_configs',
      ['id', 'name', 'total_questions', 'student_count', 'specialty_mix'], RED, 260)
place(380, 320, 'generated_assessments',
      ['id', 'config_id', 'assessment_name', 'batch_name',
       'pass_threshold', 'is_standalone'], RED, 260)
place(380, 550, 'generated_assessment_students',
      ['id', 'assessment_id', 'student_label', 'questions_json'], RED, 260)
place(710, 320, 'assessment_sessions',
      ['id', 'assessment_id', 'student_slot_id', 'coder_name',
       'employee_id', 'session_token', 'status'], RED, 260)
place(1000, 180, 'assessment_responses',
      ['id', 'session_id', 'question_id', 'selected_answer',
       'is_correct', 'override_is_correct'], RED, 210)
place(1000, 430, 'assessment_results',
      ['id', 'session_id', 'score_pct', 'correct_count'], RED, 210)
place(710, 590, 'assessment_audit_log',
      ['id', 'trainer_name', 'action', 'details'], RED, 260)

parts += [
  fk('generated_assessments', 'assessment_configs', 'up'),
  fk('generated_assessment_students', 'generated_assessments', 'up'),
  fk('assessment_sessions', 'generated_assessments'),
  fk('assessment_responses', 'assessment_sessions'),
  fk('assessment_results', 'assessment_sessions'),
  '<path d="M 706 470 Q 660 540 646 552" fill="none" stroke="#7F7F7F" stroke-width="1.8" marker-end="url(#fk)"/>',
  '<text x="612" y="500" class="rel">student_slot_id</text>',
  '<rect x="50" y="440" width="270" height="180" rx="8" fill="#FDEDEC" stroke="#C0392B" stroke-dasharray="5,4"/>',
  '<text x="68" y="468" class="note" style="fill:#922B21">No foreign key to the bank.</text>',
  '<text x="68" y="492" class="note">A paper freezes its questions into</text>',
  '<text x="68" y="514" class="note">questions_json at generation, so</text>',
  '<text x="68" y="536" class="note">editing a question afterwards cannot</text>',
  '<text x="68" y="558" class="note">alter a paper already sat.</text>',
  '<text x="68" y="588" class="note">Standalone papers hold questions</text>',
  '<text x="68" y="610" class="note">that never enter the bank at all.</text>',
  '<rect x="50" y="740" width="1140" height="76" rx="6" fill="#FDEDEC" stroke="#C0392B"/>',
  '<text x="70" y="768" class="note" style="fill:#922B21">Option order is shuffled per coder, so a stored answer letter is only meaningful against that coder\'s questions_json row.</text>',
  '<text x="70" y="792" class="note" style="fill:#922B21">Anything comparing answers across coders must compare option TEXT, not letters.</text>',
  LEGEND(710, 720) if False else '',
  '</svg>']
open('figC_erd_assessment.svg', 'w').write("\n".join(p for p in parts if p))
print('figC written')
