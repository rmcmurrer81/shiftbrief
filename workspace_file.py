"""Whole saved workspace backup, preview and explicit atomic replacement.

Only Store data is serialized. No source, environment, credential files, models,
or linked external files are read. Imported document text/history is retained.
"""
from copy import deepcopy
from pathlib import Path
import hashlib,json,math,os,re,threading,uuid
import briefing

SCHEMA='shiftbrief.workspace-file.v1'
MAX_BYTES=64_000_000
MAX_REQUEST_BYTES=MAX_BYTES*2+16_384
EXCLUDES=['application_source','launcher_and_runtime_settings','credentials_and_models','external_original_document_files']

def fail(message):raise ValueError('Workspace backup: '+message)
def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
def sha(raw):return hashlib.sha256(raw).hexdigest()
def digest(value):return sha(canonical(value))
def text(value,limit=2_000_000):
    if not isinstance(value,str) or len(value)>limit or '\x00' in value:fail('invalid or oversized text.')
    return value
def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',value):fail('invalid record identifier.')
    return value
def array(value):
    if not isinstance(value,list):fail('a saved record list is malformed.')
    return value
def mapping(value):
    if not isinstance(value,dict):fail('a saved record object is malformed.')
    return value
def bounded(value):
    count=0
    def walk(v,depth):
        nonlocal count
        count+=1
        if count>2_000_000 or depth>32:fail('structure exceeds the supported limit.')
        if isinstance(v,str):text(v)
        elif v is None or isinstance(v,bool):pass
        elif isinstance(v,(int,float)):
            if abs(v)>10**18 or not math.isfinite(v):fail('invalid numeric value.')
        elif isinstance(v,list):
            if len(v)>200_000:fail('too many entries in one list.')
            for x in v:walk(x,depth+1)
        elif isinstance(v,dict):
            if len(v)>200_000:fail('too many entries in one object.')
            for k,x in v.items():text(k,256);walk(x,depth+1)
        else:fail('unsupported data type.')
    walk(value,0)

def validate_state(data):
    """Validate references used by normal reads without dropping other saved data."""
    bounded(data);mapping(data)
    if not {'productions','current_production','documents','briefings','watches'}<=set(data):fail('workspace sections are missing.')
    if set(data)&{'environment','credentials','api_keys','runtime','models','launcher_settings'}:fail('this file contains configuration rather than only saved workspace records.')
    teams={}
    for row in array(data['productions']):
        mapping(row);pid=identifier(row.get('id'));text(row.get('title'),100)
        if pid in teams:fail('duplicate team identifier.')
        teams[pid]=row
    if not 1<=len(teams)<=1000 or data['current_production'] not in teams:fail('selected team is missing.')
    def team(row):
        mapping(row);pid=row.get('production_id','main')
        if pid not in teams:fail('a saved record references a missing team.')
        return pid
    employees={pid:set() for pid in teams}
    for field in ('staffing','shift_schedules','assistant_threads'):
        for pid,record in mapping(data.get(field,{})).items():
            if pid not in teams:fail(field+' references a missing team.')
            mapping(record)
            if field=='staffing':
                for e in array(record.get('employees',[])):
                    mapping(e);eid=identifier(e.get('id'));text(e.get('name'),100)
                    if eid in employees[pid]:fail('duplicate employee identifier.')
                    employees[pid].add(eid)
                    for k in ('availability','time_off'):mapping(e.get(k,{}))
                    for k in ('history','pay_history'):array(e.get(k,[]))
                mapping(record.get('settings',{}));array(record.get('proposals',[]))
            elif field=='assistant_threads':
                for message in array(record.get('messages',[])):
                    mapping(message);text(message.get('role'),40);text(message.get('text',''))
    work_ids={}
    for pid,rows in mapping(data.get('work_records',{})).items():
        if pid not in teams:fail('work records reference a missing team.')
        for row in array(rows):
            mapping(row)
            required={'schema','id','employee_id','date','start','end','unpaid_minutes','note','source','recorded_at'}
            if not required<=set(row) or row.get('schema')!='shiftbrief.work-record.v1':fail('unsupported saved work-record structure.')
            rid=identifier(row.get('id'))
            if (pid,rid) in work_ids or row.get('employee_id') not in employees[pid]:fail('duplicate work record or missing employee reference.')
            from datetime import date
            if not isinstance(row['date'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row['date']):fail('invalid recorded-work date.')
            date.fromisoformat(row['date'])
            if any(type(row[k]) is not int for k in ('start','end','unpaid_minutes')):fail('work times must be whole minutes.')
            if not (0<=row['start']<1440 and row['start']<row['end']<=row['start']+1440 and 0<=row['unpaid_minutes']<row['end']-row['start']):fail('invalid saved work interval.')
            if 'scheduled_start' in row and (type(row['scheduled_start']) is not int or not 0<=row['scheduled_start']<1440):fail('invalid saved scheduled start.')
            for key,limit in (('note',1000),('source',200),('recorded_at',80)):text(row[key],limit)
            work_ids[(pid,rid)]=row
    operation_ids=set()
    for operation in array(data.get('work_record_operations',[])):
        mapping(operation);rid=identifier(operation.get('request_id'));result=mapping(operation.get('result'));row=mapping(result.get('record'))
        if rid in operation_ids or not re.fullmatch('[a-f0-9]{64}',str(operation.get('binding'))):fail('invalid saved-work replay identity.')
        operation_ids.add(rid)
        key=(result.get('team_id'),row.get('id'))
        if key not in work_ids or work_ids[key]!=row:fail('saved-work replay refers to a different team or missing time record.')
    docs={}
    for doc in array(data['documents']):
        pid=team(doc);did=identifier(doc.get('id'));text(doc.get('title'),160)
        if did in docs:fail('duplicate document identifier.')
        docs[did]=(pid,doc);revids=set()
        for index,rev in enumerate(array(doc.get('revisions')),1):
            mapping(rev);rid=identifier(rev.get('id'));lines=array(rev.get('lines'))
            if rid in revids or rev.get('number')!=index:fail('document revision order or identity changed.')
            revids.add(rid)
            if briefing.digest(lines)!=rev.get('sha256'):fail('document revision checksum changed.')
            for number,line in enumerate(lines,1):
                mapping(line);text(line.get('text'))
                if line.get('line')!=number:fail('document line numbering changed.')
    seen=set()
    for watch in array(data['watches']):
        pid=team(watch);wid=identifier(watch.get('id'));text(watch.get('path'),32768)
        if wid in seen:fail('duplicate linked-file identifier.')
        seen.add(wid)
        if watch.get('document_id') not in docs or docs[watch['document_id']][0]!=pid:fail('linked file references a missing or different-team document.')
        if not isinstance(watch.get('enabled'),bool):fail('invalid linked-file status.')
    seen=set()
    for brief in array(data['briefings']):
        team(brief);bid=identifier(brief.get('id'))
        if bid in seen:fail('duplicate briefing identifier.')
        seen.add(bid)
        for key in ('findings','decisions'):array(brief.get(key,[]))
    for pid,book in data.get('shift_schedules',{}).items():
        for day,record in mapping(book.get('days',{})).items():
            mapping(record)
            for number,rev in enumerate(array(record.get('revisions',[])),1):
                mapping(rev)
                if rev.get('date')!=day or rev.get('number')!=number:fail('saved schedule revision order changed.')
                if briefing.digest({k:v for k,v in rev.items() if k!='sha256'})!=rev.get('sha256'):fail('saved schedule checksum changed.')
                for shift in array(rev.get('shifts',[])):
                    mapping(shift);eid=shift.get('employee_id')
                    if eid is not None and eid not in employees[pid]:fail('saved shift references another or missing employee.')
    return data

def summary(data):
    return {'teams':len(data['productions']),'employees':sum(len(b.get('employees',[])) for b in data.get('staffing',{}).values()),
        'documents':len(data['documents']),'document_revisions':sum(len(d['revisions']) for d in data['documents']),
        'briefings':len(data['briefings']),'chat_messages':sum(len(t.get('messages',[])) for t in data.get('assistant_threads',{}).values()),
        'schedule_revisions':sum(len(day.get('revisions',[])) for book in data.get('shift_schedules',{}).values() for day in book.get('days',{}).values()),
        'linked_files':len(data['watches']),'sections':sorted(data),'selected_team_id':data['current_production']}

def encode(data):
    validate_state(data)
    value={'schema':SCHEMA,'created':briefing.now(),'data':data,'data_sha256':digest(data),'excludes':EXCLUDES}
    value['sha256']=digest(value)
    raw=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
    if len(raw)>MAX_BYTES:fail('the saved workspace exceeds the 64 MB backup limit; no data was omitted.')
    return raw
def pairs(items):
    result={}
    for k,v in items:
        if k in result:fail('duplicate JSON field.')
        result[k]=v
    return result
def decode(value):
    if not isinstance(value,str):fail('choose a UTF-8 workspace backup file.')
    if len(value)>MAX_BYTES:fail('choose a workspace backup no larger than 64 MB.')
    raw=value.encode('utf-8')
    if not raw or len(raw)>MAX_BYTES:fail('choose a workspace backup no larger than 64 MB.')
    try:doc=json.loads(value,object_pairs_hook=pairs,parse_constant=lambda _:fail('invalid JSON number.'))
    except (RecursionError,UnicodeError,json.JSONDecodeError) as exc:raise ValueError('Workspace backup: unreadable or malformed JSON.') from exc
    bounded(doc);mapping(doc)
    if set(doc)!={'schema','created','data','data_sha256','excludes','sha256'} or doc['schema']!=SCHEMA or doc['excludes']!=EXCLUDES:fail('unsupported backup version or scope.')
    if digest({k:v for k,v in doc.items() if k!='sha256'})!=doc['sha256'] or digest(doc['data'])!=doc['data_sha256']:fail('checksum mismatch; the original workspace was not changed.')
    text(doc['created'],80);validate_state(doc['data'])
    return doc,raw

def export_workspace(store):
    with store.lock:
        data=deepcopy(store.data);raw=encode(data)
        return {'filename':'ShiftBrief-workspace-'+briefing.now().replace(':','').replace(' ','-')+'.shiftbrief-workspace.json',
            'text':raw.decode(),'backup_sha256':sha(raw),'workspace_sha256':digest(data),'summary':summary(data),'max_bytes':MAX_BYTES,
            'note':'Includes every saved team and record. Original external files, application code, launcher settings and models are not stored in this backup.'}
def preview_workspace(store,value):
    doc,raw=decode(value)
    with store.lock:
        return {'backup_sha256':sha(raw),'expected_workspace_sha256':digest(store.data),'summary':summary(doc['data']),
            'current_summary':summary(store.data),'linked_files_disabled':len(doc['data']['watches']),
            'replace_required':True,'note':'Restore replaces all saved teams. A before-restore backup is kept automatically. Linked files stay off until you choose their paths again; no jobs restart.'}

def write_exclusive(path,raw):
    with path.open('xb') as out:out.write(raw);out.flush();os.fsync(out.fileno())
def atomic(path,raw):
    temp=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.pending')
    try:write_exclusive(temp,raw);os.replace(temp,path)
    finally:
        if temp.exists():temp.unlink()
def read_record(path):return json.loads(path.read_text('utf-8'))
def journal_bytes(record):
    value={k:v for k,v in record.items() if k!='receipt_sha256'}
    return canonical({**value,'receipt_sha256':digest(value)})
def secure_folder(store):
    root=store.path.resolve();folder=root/'workspace-restores'
    if folder.exists() and (folder.is_symlink() or folder.resolve().parent!=root):fail('restore storage is not a regular local folder.')
    folder.mkdir(exist_ok=True)
    return folder

def restore_workspace(store,payload):
    if not isinstance(payload,dict) or set(payload)!={'text','expected_backup_sha256','expected_workspace_sha256','request_id','confirm_replace'}:fail('restore request is incomplete.')
    if payload['confirm_replace'] is not True:fail('preview the backup and explicitly choose Restore all data.')
    request_id=payload['request_id']
    if not isinstance(request_id,str) or not re.fullmatch('[a-f0-9]{32}',request_id):fail('restore request identifier is invalid.')
    for key in ('expected_backup_sha256','expected_workspace_sha256'):
        if not re.fullmatch('[a-f0-9]{64}',str(payload[key])):fail('restore preview identity is invalid.')
    doc,raw=decode(payload['text'])
    if sha(raw)!=payload['expected_backup_sha256']:fail('selected backup changed after preview.')
    binding=digest({k:v for k,v in payload.items() if k!='text'})
    with store.lock:
        folder=secure_folder(store);journal=folder/(request_id+'.json')
        target=deepcopy(doc['data'])
        for watch in target['watches']:
            watch.update(enabled=False,restore_requires_relink=True,restore_previous_enabled=watch['enabled'],error='Choose this file again on this computer before enabling updates.')
        target_hash=digest(target);current=digest(store.data)
        if journal.exists():
            record=read_record(journal)
            if not isinstance(record,dict) or record.get('schema')!='shiftbrief.workspace-restore.v1' or record.get('receipt_sha256')!=digest({k:v for k,v in record.items() if k!='receipt_sha256'}):fail('saved restore intent checksum changed; preserved files were not applied.')
            backup=folder/(request_id+'-before.shiftbrief-workspace.json');incoming=folder/(request_id+'-incoming.shiftbrief-workspace.json')
            if sha(backup.read_bytes())!=record.get('result',{}).get('before_backup',{}).get('sha256') or sha(incoming.read_bytes())!=payload['expected_backup_sha256']:fail('preserved restore input or before-backup changed.')
            if record.get('binding_sha256')!=binding or record.get('target_sha256')!=target_hash:fail('request identifier was already used for a different restore.')
            if record.get('status')=='complete' or current==target_hash:
                if record.get('status')!='complete':record.update(status='complete');atomic(journal,journal_bytes(record))
                return {**deepcopy(record['result']),'replayed':True,'current_workspace_sha256':current,'current_matches_restored':current==target_hash}
            if current!=record['before_sha256']:fail('workspace changed after an interrupted restore; preserved files remain available.')
        else:
            if current!=payload['expected_workspace_sha256']:fail('workspace changed since preview; preview again before restoring.')
            before=encode(deepcopy(store.data));backup=folder/(request_id+'-before.shiftbrief-workspace.json');incoming=folder/(request_id+'-incoming.shiftbrief-workspace.json')
            write_exclusive(backup,before);write_exclusive(incoming,raw)
            result={'restored':True,'replayed':False,'request_id':request_id,'backup_sha256':sha(raw),'restored_workspace_sha256':target_hash,
                'summary':summary(target),'linked_files_disabled':len(target['watches']),
                'before_backup':{'filename':backup.name,'sha256':sha(before),'bytes':len(before)},'received_backup':incoming.name}
            record={'schema':'shiftbrief.workspace-restore.v1','binding_sha256':binding,'before_sha256':current,'target_sha256':target_hash,'status':'prepared','result':result}
            write_exclusive(journal,journal_bytes(record))
        before_memory=store.data
        try:
            # One filesystem commit; before-backup and intent are durable first.
            atomic(store.path/'state.json',json.dumps(target,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8'))
            saved=read_record(store.path/'state.json')
            if digest(saved)!=target_hash:raise OSError('Restored state could not be verified.')
            store.data=target
            record.update(status='complete');atomic(journal,journal_bytes(record))
        except BaseException:
            try:saved=read_record(store.path/'state.json')
            except (OSError,ValueError):saved=None
            # A lost response after the atomic commit must not undo a success.
            if saved is not None and digest(saved)==target_hash:
                store.data=target
                return {**deepcopy(record['result']),'receipt_pending':True,'current_workspace_sha256':target_hash,'current_matches_restored':True}
            store.data=before_memory
            raise
        return {**deepcopy(record['result']),'current_workspace_sha256':target_hash,'current_matches_restored':True}

def install_app(app):
    """Serialize POSTs and full watcher refreshes, preserving job->Store lock order."""
    app.workspace_lock=threading.RLock()
    original_refresh=app.store.refresh_watches;original_toggle=app.store.toggle_watch
    def refresh():
        with app.workspace_lock:return original_refresh()
    def toggle(watch_id,enabled):
        with app.workspace_lock,app.store.lock:
            row=next((w for w in app.store.data['watches'] if w['id']==watch_id and w.get('production_id','main')==app.store.production_id),None)
            if enabled and row and row.get('restore_requires_relink'):fail('choose this linked file again on this computer before enabling it.')
            return original_toggle(watch_id,enabled)
    app.store.refresh_watches=refresh;app.store.toggle_watch=toggle

def synchronize_handler(handler,app):
    original=handler.do_POST
    def post(self):
        with app.workspace_lock:return original(self)
    handler.do_POST=post
    return handler

def action(app,operation,payload):
    with app.workspace_lock,app.job_lock,app.store.lock:
        if operation=='export':return export_workspace(app.store)
        if operation=='preview':return preview_workspace(app.store,payload.get('text'))
        if operation=='restore':
            if any(j.get('status')=='running' for j in app.jobs.values()):fail('let the current planning job finish before restoring.')
            return restore_workspace(app.store,payload)
        if operation=='relink':
            if set(payload)!={'watch_id','path'}:fail('choose one linked file and its new path.')
            row=next((w for w in app.store.data['watches'] if w['id']==payload['watch_id'] and w.get('production_id','main')==app.store.production_id),None)
            if row is None or not row.get('restore_requires_relink'):fail('select a restored link that needs its file chosen again.')
            file=Path(text(payload['path'],32768)).expanduser().resolve(strict=True)
            if not file.is_file() or file.is_symlink():fail('choose a regular source file.')
            result=app.store.import_document('',file.name,briefing.read_selected_file(file),row['document_id'])
            row.update(path=str(file),enabled=True,error='',last_checked=briefing.now());row.pop('restore_requires_relink',None);row.pop('restore_previous_enabled',None);app.store.save()
            return {'relinked':True,'watch_id':row['id'],'document':result}
        fail('unknown action.')
