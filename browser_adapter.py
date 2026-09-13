"""Browser adapter for the unchanged, tested ShiftBrief domain modules.
No HTTP listener, provider, device files, model, Strands simulation or outreach.
"""
from __future__ import annotations
import base64, binascii, io, json, secrets, time, zipfile
from copy import deepcopy
from datetime import date as RealDate
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import briefing, staffing, staffing_chat, operating_hours, shift_schedule, sarah_local, employee_pay, employee_import

ROOT = Path('/workspace/shiftbrief')
store = briefing.Store(ROOT)
TOKEN = secrets.token_urlsafe(24)
APP = 'ShiftBrief browser workspace'
MAX_ZIP = 50 * 1024 * 1024
MAX_JSON = 100 * 1024 * 1024
local_day = RealDate.today()

class BrowserDate(RealDate):
    @classmethod
    def today(cls):
        return cls(local_day.year, local_day.month, local_day.day)

for module in (staffing, staffing_chat, operating_hours, shift_schedule):
    module.date = BrowserDate

def calendar(payload):
    global local_day
    raw = payload.get('local_date')
    if raw:
        local_day = RealDate.fromisoformat(raw)
    if 'local_timestamp' in payload:
        # Keep an explicit offset in browser history rather than assuming WASM timezone.
        stamp = str(payload['local_timestamp'])
        if len(stamp) > 50 or not stamp.startswith(local_day.isoformat()):
            raise ValueError('The browser calendar could not be read. Reload this page.')
        for module in (briefing, staffing, staffing_chat, operating_hours, shift_schedule, sarah_local):
            if hasattr(module, 'now'):
                module.now = lambda value=stamp: value

def blank():
    return {'documents': [], 'briefings': [], 'watches': [], 'productions': [{'id':'main','title':'My first team'}], 'current_production':'main'}

def validate_data(data):
    if not isinstance(data, dict):
        raise ValueError('The workspace data must be an object.')
    for name in ('documents','briefings','watches','productions'):
        if not isinstance(data.get(name), list):
            raise ValueError('The workspace is missing its '+name+' list.')
    teams = data['productions']
    if not teams or len(teams) > 1000 or any(not isinstance(p,dict) or not isinstance(p.get('id'),str) or not p['id'] or not isinstance(p.get('title'),str) or not 1 <= len(p['title']) <= 100 for p in teams):
        raise ValueError('The workspace team records are invalid.')
    ids = [p['id'] for p in teams]
    if len(set(ids)) != len(ids) or data.get('current_production') not in ids:
        raise ValueError('The workspace team selection is invalid.')
    if data['watches']:
        raise ValueError('This browser copy cannot contain native file watchers. Import selected source files instead.')
    for name in ('assistant_threads','staffing','shift_schedules'):
        if name in data and not isinstance(data[name],dict):
            raise ValueError('The workspace '+name+' records are invalid.')
    for collection in ('documents','briefings'):
        if any(not isinstance(item,dict) or item.get('production_id','main') not in ids for item in data[collection]):
            raise ValueError('A source or handoff belongs to a missing team.')
    for doc in data['documents']:
        if not isinstance(doc.get('id'),str) or not isinstance(doc.get('title'),str) or not isinstance(doc.get('revisions'),list) or not doc['revisions']:
            raise ValueError('A source record is invalid.')
        for rev in doc['revisions']:
            if not isinstance(rev,dict) or not isinstance(rev.get('lines'),list) or not isinstance(rev.get('number'),int):
                raise ValueError('A source revision is invalid.')
            if any(not isinstance(line,dict) or not isinstance(line.get('text'),str) or not isinstance(line.get('line'),int) for line in rev['lines']):
                raise ValueError('A source line is invalid.')
    jobs = data.get('browser_jobs',[])
    if not isinstance(jobs,list) or any(not isinstance(job,dict) or job.get('production_id') not in ids or job.get('status') != 'complete' or not isinstance(job.get('id'),str) or not isinstance(job.get('trace'),list) for job in jobs):
        raise ValueError('The saved handoff jobs are invalid.')
    candidate = briefing.Store(ROOT)
    candidate.data = deepcopy(data)
    selected = candidate.production_id
    # Exercise every team's real view before replacing the current workspace.
    for team_id in ids:
        candidate.data['current_production'] = team_id
        candidate.view()
    candidate.data['current_production'] = selected
    return candidate

def snapshot():
    output = io.BytesIO()
    raw = json.dumps(store.data,ensure_ascii=False,separators=(',',':')).encode()
    if len(raw) > MAX_JSON:
        raise ValueError('This workspace copy exceeds the 100 MB data limit. Export individual weeks or handoffs.')
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('SHIFTBRIEF-WORKSPACE.json',json.dumps({'app':APP,'schema':1,'created':briefing.now()}))
        archive.writestr('state.json',raw)
    return {'snapshot':base64.b64encode(output.getvalue()).decode()}

def restore(encoded):
    global store
    if encoded is None:
        candidate = briefing.Store(ROOT)
        candidate.data = blank()
    else:
        if not isinstance(encoded,str) or len(encoded) > MAX_ZIP*4//3+8:
            raise ValueError('Choose a ShiftBrief browser workspace copy smaller than 50 MB.')
        try:
            raw = base64.b64decode(encoded,validate=True)
            if len(raw) > MAX_ZIP: raise ValueError('The workspace copy is too large.')
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                infos = archive.infolist()
                if len(infos) != 2 or set(archive.namelist()) != {'SHIFTBRIEF-WORKSPACE.json','state.json'}:
                    raise ValueError('Choose an intact ShiftBrief browser workspace copy.')
                if sum(x.file_size for x in infos) > MAX_JSON+4096 or any(x.flag_bits & 1 for x in infos):
                    raise ValueError('The workspace copy is encrypted or too large.')
                metadata = json.loads(archive.read('SHIFTBRIEF-WORKSPACE.json'))
                if not isinstance(metadata,dict) or metadata.get('app') != APP or metadata.get('schema') != 1:
                    raise ValueError('This file is not a supported ShiftBrief browser workspace.')
                data = json.loads(archive.read('state.json'))
            candidate = validate_data(data)
        except (ValueError,TypeError,KeyError,AttributeError,IndexError,OverflowError,RecursionError,zipfile.BadZipFile,binascii.Error) as exc:
            raise ValueError('The workspace copy could not be read: '+str(exc)[:220]) from exc
    store = candidate
    return {'restored':True}

def result(body,status=200,mime='application/json'):
    if isinstance(body,bytes):
        return {'status':status,'content_type':mime,'base64':base64.b64encode(body).decode()}
    return {'status':status,'content_type':mime,'body':body}

def request(payload):
    route = urlsplit(payload.get('path',''))
    path = route.path
    query = parse_qs(route.query)
    body = payload.get('body',{})
    method = payload.get('method','GET').upper()
    if not isinstance(body,dict): raise ValueError('Supply an object for this action.')
    if method == 'GET':
        if path == '/api/state':
            current_view = store.view()
            current_view.pop('browser_jobs',None)
            return result({'app':'ShiftBrief','state':current_view,'token':TOKEN,'runtime':{'mode':'sarah_local','label':'Sarah browser evidence','model':'none','url':'saved in this browser','optional_strands_available':False},'jobs':[x for x in store.data.get('browser_jobs',[]) if x['production_id']==store.production_id],'browser_calendar':{'today':local_day.isoformat(),'timezone':payload.get('timezone','')}})
        if path == '/api/export': return result(store.export(query.get('id',[''])[0]),mime='text/markdown')
        if path == '/api/staff/export-week': return result(staffing.export_week(store,query.get('week',[staffing.book(store)['selected_week']])[0]),mime='application/zip')
        if path == '/api/schedule/export': return result(shift_schedule.export_csv(shift_schedule.latest(store,query.get('date',[None])[0])),mime='text/csv')
        if path == '/api/schedule/history':
            value = shift_schedule.view(store,query.get('date',[None])[0],int(query['number'][0]) if query.get('number') else None)
            value['coverage'] = staffing.role_coverage(value['plan'])
            return result(value)
        if path == '/api/voice/status': return result({'available':False,'ready':False,'message':'Written Sarah replies work in this browser. The optional local voice pack belongs to the Desktop edition.'})
        return result({'error':'This browser action was not found.'},404)
    if method != 'POST': return result({'error':'Unsupported browser action.'},405)
    if payload.get('token') != TOKEN: raise ValueError('Reload the workspace before making this change.')
    if path not in ('/api/production/create','/api/production/select') and payload.get('expected_team') != store.production_id:
        raise ValueError('Another tab changed the selected team. Refresh this tab and review the team before saving.')
    if path == '/api/production/create': return result(store.create_production(body['title']))
    if path == '/api/production/select': store.select_production(body['id']); return result({'selected':True})
    if path.startswith('/api/staff/'):
        action = path.rsplit('/',1)[-1]
        routes = {
          'pay-propose':lambda:employee_pay.propose(store,body),
          'pay-accept':lambda:employee_pay.accept(store,body),
          'employee-import-prepare':lambda:employee_import.prepare(store,body),
          'employee-import-accept':lambda:employee_import.accept(store,body),
          'hours-propose':lambda:operating_hours.propose(store,body['config'],'Owner reviewed operating-hours form'),
          'hours-accept':lambda:operating_hours.accept(store,body['id'],body['sha256']),
          'employee':lambda:staffing.save_employee(store,body),
          'end':lambda:staffing.end_employment(store,body['employee_id'],body['date'],body.get('reason','Owner recorded employment end')),
          'timeoff':lambda:staffing.time_off(store,body['employee_id'],body['start'],body['end'],body.get('reason','Time off requested')),
          'timeoff-cancel':lambda:staffing.cancel_time_off(store,body['employee_id'],body['date'],body['expected_revision']),
          'settings':lambda:staffing.settings(store,body),
          'week':lambda:staffing.select_week(store,body['week_start']),
          'day':lambda:staffing.select_day(store,body['date']),
          'suggest':lambda:staffing.suggest_week(store,body['week_start']),
          'revise':lambda:staffing.revise_week(store,body['id'],body['sha256'],body['days']),
          'lunch':lambda:staffing.suggest_lunch(store,body['shift_id'],body['date'],body.get('duration',30)),
          'sick':lambda:staffing.suggest_sick(store,body['employee_id'],body['date']),
          'accept':lambda:staffing.accept(store,body['id'],body['sha256'],body.get('choice')),
          'shift':lambda:staffing.edit_shift(store,body),
          'restore':lambda:staffing.restore_schedule(store,body),
          'example':lambda:staffing.load_staff_example(store),
        }
        if action not in routes: raise ValueError('Unknown staffing action.')
        value = routes[action]()
        if action == 'employee':
            thread = store.data.setdefault('assistant_threads',{}).setdefault(store.production_id,{'messages':[],'pending':None})
            thread['staffing_form'] = None
            thread['messages'].append({'role':'assistant','text':'Saved '+value['name']+' and the availability you entered for '+staffing.book(store)['selected_week']+'. I can now suggest the week using these recorded details.','kind':'employee_saved','created':briefing.now()})
            store.save()
        return result(value)
    if path == '/api/import':
        raw = base64.b64decode(body['base64'],validate=True) if 'base64' in body else body.get('text','').encode()
        return result(store.import_document(body.get('title',''),body.get('filename','pasted.txt'),raw,body.get('document_id')))
    if path == '/api/sample':
        existing = next((p for p in store.data['productions'] if p.get('sample')),None)
        if existing: store.select_production(existing['id'])
        else:
            example=store.create_production('Fictional shoot example')
            next(p for p in store.data['productions'] if p['id']==example['id'])['sample']=True
        briefing.load_sample(store)
        return result({'added':True})
    if path == '/api/assistant/message': return result(sarah_local.ask(store,body.get('message'),body.get('briefing_id')))
    if path == '/api/assistant/confirm': return result(sarah_local.confirm(store,body.get('proposal_id'),body.get('proposal_sha'),body.get('confirmation')))
    if path == '/api/brief':
        if body.get('mode','sarah_local') != 'sarah_local':
            raise ValueError('This browser edition uses the free source-backed Sarah engine. Actual Strands/Ollama runs are available separately in the Desktop edition.')
        job = {'id':secrets.token_hex(6),'production_id':store.production_id,'started':time.time(),'trace':[]}
        value = sarah_local.run_local(store,body.get('request','Prepare the next-shift handoff.'),progress=lambda trace:job.update(trace=list(trace)))
        job.update(status='complete',briefing_id=value['id'],elapsed_seconds=value['elapsed_seconds'])
        store.data.setdefault('browser_jobs',[]).append(job)
        store.data['browser_jobs'] = store.data['browser_jobs'][-100:]
        store.save()
        return result(job)
    if path == '/api/decision':
        store.set_decision(body['briefing_id'],body['decision_id'],body['done'])
        return result({'saved':True})
    if path.startswith('/api/watch') or path.startswith('/api/voice'):
        raise ValueError('This browser edition uses selected source uploads and written Sarah replies. Native file watching and the optional voice pack are Desktop features.')
    return result({'error':'This browser action was not found.'},404)

def dispatch(payload):
    calendar(payload)
    operation = payload.get('operation')
    if operation == 'snapshot': return snapshot()
    if operation == 'restore': return restore(payload.get('snapshot'))
    if operation != 'request': raise ValueError('Unknown browser operation.')
    before = deepcopy(store.data)
    try:
        value = request(payload)
        if value['status'] >= 400:
            store.data = before
            value['changed'] = False
        else:
            value['changed'] = store.data != before
        return value
    except (ValueError,KeyError,TypeError,AttributeError,IndexError,OSError,OverflowError,RecursionError,binascii.Error) as exc:
        store.data = before
        return {'status':400,'body':{'error':str(exc)[:700]},'content_type':'application/json','changed':False}
