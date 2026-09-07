from __future__ import annotations
import base64, difflib, hashlib, io, json, os, re, threading, time, uuid
from pathlib import Path
from copy import deepcopy

MAX_BYTES = 5_000_000

def read_selected_file(file):
    if file.stat().st_size > MAX_BYTES:
        raise ValueError('Choose a file smaller than 5 MB.')
    with file.open('rb') as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('The file grew beyond the 5 MB limit.')
    return raw

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

def now():
    return time.strftime('%Y-%m-%d %H:%M:%S')

def extract(filename, raw):
    if len(raw) > MAX_BYTES:
        raise ValueError('Choose a file smaller than 5 MB.')
    ext = Path(filename).suffix.lower()
    if ext == '.pdf':
        try: from pypdf import PdfReader
        except ImportError as exc: raise ValueError('PDF support is optional and not installed here. Paste the document text or use TXT/Markdown/CSV; the README explains how to enable PDF import.') from exc
        reader = PdfReader(io.BytesIO(raw))
        if len(reader.pages) > 80:
            raise ValueError('Choose a PDF excerpt of at most 80 pages.')
        lines = []
        for page, obj in enumerate(reader.pages, 1):
            for line in (obj.extract_text() or '').splitlines():
                if line.strip():
                    lines.append({'text': line.strip(), 'page': page})
    elif ext in ('.txt', '.md', '.csv'):
        try:
            lines = [{'text': x.strip(), 'page': None} for x in raw.decode('utf-8-sig').splitlines() if x.strip()]
        except UnicodeDecodeError:
            raise ValueError('Save the text file as UTF-8, or import a text PDF.')
    else:
        raise ValueError('Use a PDF, TXT, Markdown or CSV file.')
    if not lines:
        raise ValueError('No readable text found. A scanned PDF needs OCR first.')
    if sum(len(x['text']) for x in lines) > 120000:
        raise ValueError('Use a focused document excerpt under 120,000 characters.')
    return [dict(x, line=i) for i, x in enumerate(lines, 1)]

class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        file = self.path / 'state.json'
        self.data = json.loads(file.read_text('utf-8')) if file.exists() else {'documents': [], 'briefings': [], 'watches': []}
        self.data.setdefault('productions', [{'id': 'main', 'title': 'My first team'}])
        self.data.setdefault('current_production', 'main')

    def save(self):
        dest = self.path / 'state.json'
        temp = dest.with_suffix('.tmp')
        temp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), 'utf-8')
        os.replace(temp, dest)

    @property
    def production_id(self):
        return self.data['current_production']

    def create_production(self, title):
        if not isinstance(title,str) or not title.strip() or len(title)>100:
            raise ValueError('Give this production a name of 1 to 100 characters.')
        with self.lock:
            item={'id':uuid.uuid4().hex[:10],'title':title.strip()}
            self.data['productions'].append(item)
            self.data['current_production']=item['id']
            self.save()
            return deepcopy(item)

    def select_production(self, production_id):
        with self.lock:
            if not any(x['id']==production_id for x in self.data['productions']):
                raise ValueError('Production not found.')
            self.data['current_production']=production_id
            self.save()

    def import_document(self, title, filename, raw, document_id=None):
        lines = extract(filename, raw)
        with self.lock:
            if document_id:
                doc = self.document(document_id)
            else:
                if not title.strip():
                    raise ValueError('Name this production document.')
                doc = {'id': uuid.uuid4().hex[:10], 'production_id': self.production_id, 'title': title.strip()[:160], 'revisions': []}
                self.data['documents'].append(doc)
            sha = digest(lines)
            if doc['revisions'] and doc['revisions'][-1]['sha256'] == sha:
                return {'document_id': doc['id'], 'unchanged': True}
            rev = {'id': uuid.uuid4().hex[:10], 'number': len(doc['revisions']) + 1,
                   'filename': Path(filename).name, 'created': now(), 'sha256': sha, 'lines': lines}
            doc['revisions'].append(rev)
            self.save()
            return {'document_id': doc['id'], 'revision_id': rev['id'], 'unchanged': False}

    def document(self, doc_id):
        for doc in self.data['documents']:
            if doc['id'] == doc_id and doc.get('production_id','main') == self.production_id:
                return doc
        raise ValueError('That document is no longer available.')

    def snapshot(self):
        with self.lock:
            docs = []
            for doc in self.data['documents']:
                if doc['revisions'] and doc.get('production_id','main') == self.production_id:
                    docs.append({'id': doc['id'], 'title': doc['title'], 'revisions': deepcopy(doc['revisions'][-2:])})
            return {'documents': docs, 'sha256': digest(docs)}

    def view(self):
        with self.lock:
            result = deepcopy(self.data)
            for field in ('documents','briefings','watches'):
                result[field] = [x for x in result[field] if x.get('production_id','main') == self.production_id]
            current = self.snapshot()['sha256']
            for brief in result['briefings']:
                brief['outdated'] = brief['snapshot_sha256'] != current
            for watch in result['watches']:
                watch['filename'] = Path(watch['path']).name
            result['assistant'] = deepcopy(result.pop('assistant_threads', {}).get(self.production_id, {'messages': [], 'pending': None}))
            import staffing
            result.pop('shift_schedules',None)
            result['staffing'] = staffing.view(self)
            result['comparisons'] = [update_packet(x) for x in self.snapshot()['documents']]
            return result

    def watch_file(self, path, title, document_id=None):
        file = Path(path).expanduser().resolve(strict=True)
        if not file.is_file() or file.is_symlink():
            raise ValueError('Choose one regular file, not a folder or shortcut.')
        result = self.import_document(title, file.name, read_selected_file(file), document_id)
        with self.lock:
            existing = next((x for x in self.data['watches'] if x['path'] == str(file) and x.get('production_id','main') == self.production_id), None)
            if existing:
                return existing
            item = {'id': uuid.uuid4().hex[:10], 'path': str(file), 'document_id': result['document_id'],
                    'production_id': self.production_id, 'enabled': True, 'last_checked': now(), 'error': ''}
            self.data['watches'].append(item)
            self.save()
            return deepcopy(item)

    def refresh_watches(self):
        with self.lock:
            watches = deepcopy([x for x in self.data['watches'] if x['enabled'] and x.get('production_id','main') == self.production_id])
        results = []
        for watch in watches:
            error = ''
            try:
                file = Path(watch['path'])
                result = self.import_document('', file.name, read_selected_file(file), watch['document_id'])
                results.append(result)
            except (OSError, ValueError) as exc:
                error = str(exc)[:300]
            with self.lock:
                target = next(x for x in self.data['watches'] if x['id'] == watch['id'])
                target.update(last_checked=now(), error=error)
                self.save()
        return results

    def toggle_watch(self, watch_id, enabled):
        with self.lock:
            watch = next((x for x in self.data['watches'] if x['id'] == watch_id and x.get('production_id','main') == self.production_id), None)
            if not watch:
                raise ValueError('Watch not found.')
            watch['enabled'] = bool(enabled)
            self.save()

    def save_briefing(self, snapshot, headline, findings, decisions, open_questions, trace, model="qwen3.5:9b", framework="Strands Agents SDK", interpretation=True):
        if not str(headline).strip() or len(headline) > 240:
            raise ValueError('A concise briefing headline is required.')
        if not isinstance(findings, list) or not 1 <= len(findings) <= 12:
            raise ValueError('Provide one to twelve cited findings.')
        if not isinstance(decisions, list) or len(decisions) > 12:
            raise ValueError('Provide at most twelve suggested decisions.')
        citations = citation_index(snapshot)
        def validate_rows(rows, decision=False):
            cleaned = []
            for row in rows:
                text = str(row.get('text', '')).strip()
                refs = row.get('evidence', [])
                if not text or len(text) > 1000 or not refs:
                    raise ValueError('Each finding and decision needs text and exact supporting evidence.')
                confirmed = []
                for ref in refs:
                    key, quote = ref.get('ref', ''), str(ref.get('quote', '')).strip()
                    if key not in citations or not quote or quote not in citations[key]['text']:
                        raise ValueError('Evidence must exactly quote a supplied source line: ' + str(key))
                    confirmed.append({'ref': key, 'quote': quote, **citations[key]})
                cleaned.append({'text': text, 'evidence': confirmed, **({'id': uuid.uuid4().hex[:10], 'done': False} if decision else {})})
            return cleaned
        record = {'id': uuid.uuid4().hex[:10], 'created': now(), 'headline': headline,
                  'findings': validate_rows(findings), 'decisions': validate_rows(decisions, True),
                  'open_questions': [str(x)[:500] for x in open_questions[:8]],
                  'snapshot_sha256': snapshot['sha256'], 'trace': deepcopy(trace),
                  'production_id': self.production_id, 'model': model, 'framework': framework, 'interpretation': interpretation}
        with self.lock:
            if self.snapshot()['sha256'] != snapshot['sha256']:
                raise ValueError('Documents changed while the agent was reading. Run the briefing again.')
            self.data['briefings'].append(record)
            self.save()
        return record

    def set_decision(self, brief_id, decision_id, done):
        with self.lock:
            brief = next((b for b in self.data['briefings'] if b['id'] == brief_id and b.get('production_id','main') == self.production_id), None)
            if not brief:
                raise ValueError('Briefing not found.')
            if brief['snapshot_sha256'] != self.snapshot()['sha256']:
                raise ValueError('This briefing is outdated. Create a current briefing before changing its checklist.')
            decision = next((d for d in brief['decisions'] if d['id'] == decision_id), None)
            if not decision:
                raise ValueError('Decision not found.')
            decision.update(done=bool(done), updated=now())
            self.save()

    def export(self, brief_id):
        brief = next((b for b in self.view()['briefings'] if b['id'] == brief_id and b.get('production_id','main') == self.production_id), None)
        if not brief:
            raise ValueError('Briefing not found.')
        lines = ['# ShiftBrief — ' + brief['headline'], '', 'Created: ' + brief['created'],
                 'Status: ' + ('OUTDATED — documents have changed.' if brief['outdated'] else 'Current saved source snapshot.'),
                 ('AI interpretation; source quotations were checked literally. Human judgment is still needed.' if brief.get('interpretation', True) else 'Local rule-based evidence comparison. Source quotations were checked literally; human approval is still needed.'), '', '## What changed']
        for group in ('findings', 'decisions'):
            if group == 'decisions':
                lines += ['', '## Suggested decisions — owner checklist']
            for row in brief[group]:
                if row.get('owner_edited'): lines.append('- Owner-edited checklist wording; supporting source evidence is unchanged.')
                lines.append(('- [x] ' if row.get('done') else '- [ ] ') + row['text'] if group == 'decisions' else '- ' + row['text'])
                for cite in row['evidence']:
                    lines += ['  - ' + cite['title'] + ' r' + str(cite['revision']) + ' line ' + str(cite['line']) + ': “' + cite['quote'] + '”']
        lines += ['', '## Still to resolve'] + ['- ' + x for x in brief['open_questions']]
        lines += ['', 'Source snapshot: ' + brief['snapshot_sha256'], 'Engine: ' + brief.get('framework', 'Strands Agents SDK') + ' / model: ' + brief['model'], 'No crew messages were sent.']
        return '\n'.join(lines) + '\n'


def citation_index(snapshot):
    result = {}
    for doc in snapshot['documents']:
        for rev in doc['revisions']:
            for line in rev['lines']:
                ref = f"{doc['id']}:r{rev['number']}:L{line['line']}"
                result[ref] = {**line, 'document_id': doc['id'], 'title': doc['title'], 'revision': rev['number']}
    return result


def update_packet(doc):
    before = doc['revisions'][-2] if len(doc['revisions']) > 1 else None
    after = doc['revisions'][-1]
    a = [x['text'] for x in before['lines']] if before else []
    b = [x['text'] for x in after['lines']]
    changes = []
    for tag, i, j, k, l in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == 'equal':
            continue
        changes.append({'kind': tag, 'before': a[i:j], 'after': b[k:l], 'before_start': i + 1, 'after_start': k + 1})
    revisions = []
    for rev in doc['revisions']:
        revisions.append({'revision': rev['number'], 'filename': rev['filename'], 'lines': [dict(x, ref=f"{doc['id']}:r{rev['number']}:L{x['line']}") for x in rev['lines']]})
    return {'document_id': doc['id'], 'title': doc['title'], 'changes': changes, 'revisions': revisions}


def load_sample(store):
    if any(x['title'].endswith('[fictional sample]') and x.get('production_id','main')==store.production_id for x in store.data['documents']):
        return
    samples = [('Harbor shoot call sheet', 'Production: Harbor, day 3\nCrew call: 07:00\nExterior pier scene: 09:00\nLocation: East Pier\nTransport coordinator: Lena\n',
        'Production: Harbor, day 3\nCrew call: 08:30\nInterior warehouse scene: 10:00\nLocation: Warehouse B\nTransport coordinator: Lena\nReason: heavy rain forecast\n'),
        ('Transport note', 'Van pickup: 06:15 at Unit Base\nDestination: East Pier\nDriver: Sam\n', 'Van pickup: 06:15 at Unit Base\nDestination: East Pier\nDriver: Sam\nTransport has not received a revised pickup time or destination.\n')]
    for title, old, new in samples:
        first = store.import_document(title + ' [fictional sample]', 'sample-v1.txt', old.encode())
        store.import_document('', 'sample-v2.txt', new.encode(), first['document_id'])
