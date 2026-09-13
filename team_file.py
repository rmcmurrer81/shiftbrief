"""Portable team records: additive Open, empty New, and explicit Save copy.
No file paths, watchers, jobs, documents, executable imports, or live proposals.
"""
from copy import copy, deepcopy
from datetime import date
import hashlib,json,math,re,uuid
import briefing
import staffing as staff
import shift_schedule as daily
import operating_hours

SCHEMA='shiftbrief.team-file.v1'
SCHEMA_V2='shiftbrief.team-file.v2'
MAX_BYTES=5_000_000
MAX_EMPLOYEES=200
MAX_DAYS=3660
MAX_REVISIONS=50
INCLUDES=['employees','contacts','dated_availability','time_off','pay_history','employee_history','operating_settings','saved_planned_schedule_history']
EXCLUDES=['documents','chat','file_watchers','active_jobs','pending_proposals','review_approvals']

def fail(message):raise ValueError('Team file: '+message)
def fields(v,allowed,required=()):
 if not isinstance(v,dict) or set(v)-set(allowed) or not set(required)<=set(v):fail('unsupported or missing record fields.')
 return v
def string(v,limit=800,empty=False):
 if not isinstance(v,str) or len(v)>limit or (not empty and not v.strip()) or '\x00' in v:fail('invalid text field.')
 return v
def integer(v,low,high):
 if isinstance(v,bool) or not isinstance(v,int) or not low<=v<=high:fail('number is outside its supported range.')
 return v
def day(v):
 if not isinstance(v,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',v):fail('use exact YYYY-MM-DD dates.')
 try:date.fromisoformat(v)
 except ValueError:fail('invalid calendar date.')
 return v
def identity(v):
 if not isinstance(v,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',v):fail('invalid record identifier.')
 return v
def sequence(v,limit):
 if not isinstance(v,list) or len(v)>limit:fail('too many or invalid records.')
 return v
def envelope_digest(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def bounded_tree(value):
 nodes=0
 def walk(v,depth=0):
  nonlocal nodes
  nodes+=1
  if nodes>250000 or depth>16:fail('file structure exceeds its limit.')
  if v is None or isinstance(v,bool):return
  if isinstance(v,str):string(v,20000,True);return
  if isinstance(v,(int,float)):
   if not math.isfinite(v) or abs(v)>10**12:fail('invalid numeric value.')
   return
  if isinstance(v,list):
   if len(v)>20000:fail('list exceeds its limit.')
   for x in v:walk(x,depth+1)
   return
  if isinstance(v,dict):
   if len(v)>MAX_DAYS:fail('object exceeds its limit.')
   for k,x in v.items():string(k,120);walk(x,depth+1)
   return
  fail('unsupported JSON value.')
 walk(value)

def rate(row):
 fields(row,{'amount_minor','amount','currency','effective_date','reason','id','recorded_at','proposal_id','proposal_sha256','import_id','source_sha256'},('amount_minor','amount','currency','effective_date','reason','id','recorded_at'))
 minor=integer(row['amount_minor'],0,1000000)
 if row['amount']!=f'{minor//100}.{minor%100:02d}' or not re.fullmatch('[A-Z]{3}',str(row['currency'])):fail('hourly rate units/amount are invalid.')
 day(row['effective_date']);string(row['reason'],500);identity(row['id']);string(row['recorded_at'],80)
 for key in ('proposal_id','import_id'):
  if key in row:identity(row[key])
 for key in ('proposal_sha256','source_sha256'):
  if key in row and not re.fullmatch('[0-9a-f]{64}',str(row[key])):fail('invalid historical source digest.')

IMPORT_FIELDS={'name','phone','email','roles','start_date','hourly_rate','currency'}
def import_source(value):
 fields(value,{'import_id','candidate_id','filename','source_sha256','evidence','extracted_fields','reviewed_fields'},('import_id','candidate_id','filename','source_sha256','evidence','extracted_fields','reviewed_fields'))
 identity(value['import_id']);identity(value['candidate_id']);string(value['filename'],200)
 if '/' in value['filename'] or '\\' in value['filename']:fail('source filenames cannot contain paths.')
 if not re.fullmatch('[0-9a-f]{64}',str(value['source_sha256'])):fail('invalid import source digest.')
 for key in ('evidence','extracted_fields','reviewed_fields'):
  fields(value[key],IMPORT_FIELDS)
  for k,v in value[key].items():
   if isinstance(v,list):
    if k!='roles':fail('invalid archived import field.')
    for role in sequence(v,12):string(role,60)
   else:string(v,2000,True)

EMPLOYEE_FIELDS={'id','name','start_date','end_date','roles','phone','email','preferences','availability','time_off','history','revision','pay_history','import_source'}
def employee(value,snapshot=False):
 fields(value,EMPLOYEE_FIELDS-({'history'} if snapshot else set()),('id','name','start_date','end_date','roles','availability','time_off','revision'))
 identity(value['id']);string(value['name'],100);day(value['start_date']);integer(value['revision'],1,1000000)
 if value['end_date'] is not None and day(value['end_date'])<value['start_date']:fail('end date precedes start.')
 for role in sequence(value['roles'],12):string(role,60)
 for k in ('phone','email','preferences'):
  if k in value:string(value[k],800,True)
 availability=value['availability'];timeoff=value['time_off']
 if not isinstance(availability,dict) or len(availability)>MAX_DAYS or not isinstance(timeoff,dict) or len(timeoff)>MAX_DAYS:fail('too many dated employee records.')
 for key,row in availability.items():
  day(key);fields(row,{'status','windows','preference','end_next_day'},('status','windows'))
  if row['status'] not in {'available','off','unknown'}:fail('invalid availability status.')
  if 'end_next_day' in row and not isinstance(row['end_next_day'],bool):fail('invalid overnight flag.')
  string(row.get('preference',''),200,True)
  windows=sequence(row['windows'],8)
  if row['status']!='available' and windows:fail('unknown/off availability cannot contain hours.')
  for window in windows:
   fields(window,{'start','end'},('start','end'));a=integer(window['start'],0,1439);b=integer(window['end'],1,2879)
   if not 0<b-a<=1440:fail('invalid availability interval.')
 for key,reason in timeoff.items():day(key);string(reason,300,True)
 for row in sequence(value.get('pay_history',[]),1000):rate(row)
 if 'import_source' in value:import_source(value['import_source'])
 if snapshot:return
 for row in sequence(value.get('history',[]),1000):
  fields(row,{'at','operation','snapshot','effective_date','reason','start','end','date','original_reason','entry','source'},('at','operation'))
  string(row['at'],80)
  operation=row['operation']
  if operation=='employee_details_saved':
   employee(row.get('snapshot'),True)
   if row['snapshot']['id']!=value['id']:fail('employee history references another employee.')
  elif operation=='hourly_rate_recorded':rate(row.get('entry'))
  elif operation=='employee_import_reviewed':import_source(row.get('source'))
  elif operation=='employment_ended':day(row.get('effective_date'));string(row.get('reason'),300,True)
  elif operation=='time_off_recorded':
   if day(row.get('start'))>day(row.get('end')):fail('invalid historical time-off range.')
   string(row.get('reason'),300,True)
  elif operation=='time_off_cancelled':day(row.get('date'));string(row.get('original_reason'),300,True)
  else:fail('unsupported employee history operation.')

def settings(value):
 fields(value,{'hours_confirmed','overtime_hours','roles','open','close','operating_hours'},('hours_confirmed','overtime_hours','roles','open','close'))
 if not isinstance(value['hours_confirmed'],bool):fail('invalid operating-hours confirmation.')
 n=value['overtime_hours']
 if isinstance(n,bool) or not isinstance(n,(int,float)) or not math.isfinite(n) or not 1<=n<=168:fail('invalid overtime planning threshold.')
 roles=value['roles']
 if not isinstance(roles,dict) or not 1<=len(roles)<=10:fail('invalid required roles.')
 for k,v in roles.items():string(k,60);integer(v,1,30)
 if not daily.clock(value['open'])<daily.clock(value['close']):fail('invalid default business hours.')
 if 'operating_hours' in value and operating_hours.validate(value['operating_hours'])!=value['operating_hours']:fail('unsupported operating-hours fields.')

def plan(value,key,employees,number):
 fields(value,{'date','open','close','minimum','shifts','role_requirements','coverage_windows','operating_hours','absences','number','created','source_message','sha256'},('date','open','close','minimum','shifts','number','created','source_message','sha256'))
 integer(value['number'],1,MAX_REVISIONS)
 if value['date']!=key or value['number']!=number:fail('schedule date/revision sequence mismatch.')
 integer(value['open'],0,1439);integer(value['close'],1,1440);integer(value['minimum'],1,100)
 string(value['created'],80);string(value['source_message'],2000,True)
 if briefing.digest({k:v for k,v in value.items() if k!='sha256'})!=value['sha256']:fail('saved schedule digest changed.')
 ids=set()
 for shift in sequence(value['shifts'],100):
  fields(shift,{'id','employee_id','employee','role','start','end','breaks'},('id','employee','start','end','breaks'))
  sid=identity(shift['id'])
  if sid in ids:fail('duplicate shift identifier.')
  ids.add(sid);string(shift['employee'],100);string(shift.get('role',''),100,True)
  eid=shift.get('employee_id')
  if eid is not None:
   if eid not in employees:fail('shift references an employee outside this team.')
  # Legacy name-only shifts are bounded saved labels, not employee bindings.
  # Keep the original label and digest even after a rename or roster change.
  integer(shift['start'],0,1439);integer(shift['end'],1,1440)
  breaks=set()
  for b in sequence(shift['breaks'],24):
   fields(b,{'id','label','start','end'},('id','label','start','end'))
   identity(b['id']);string(b['label'],60);integer(b['start'],0,1439);integer(b['end'],1,1440)
   if b['id'] in breaks:fail('duplicate break identifier.')
   breaks.add(b['id'])
 if 'role_requirements' in value:
  roles=value['role_requirements']
  if not isinstance(roles,dict) or len(roles)>12:fail('invalid schedule roles.')
  for k,v in roles.items():string(k,100);integer(v,1,100)
 for window in value.get('coverage_windows',[]):
  fields(window,{'start','end'},('start','end'));a=integer(window['start'],0,1439);b=integer(window['end'],1,1440)
  if b<=a:fail('invalid coverage interval.')
 if 'operating_hours' in value:
  op=value['operating_hours']
  fields(op,{'date','closed','closure_reasons','bands','coverage_windows','customer_windows','staffing_open','staffing_close','signature'},('date','closed','closure_reasons','bands','coverage_windows','customer_windows','staffing_open','staffing_close','signature'))
  if op['date']!=key or not isinstance(op['closed'],bool):fail('invalid saved operating date.')
  for reason in sequence(op['closure_reasons'],100):string(reason,400)
  for band in sequence(op['bands'],100):
   fields(band,{'start','end','kind'},('start','end','kind'));integer(band['start'],0,1439);integer(band['end'],1,1440);string(band['kind'],100)
  for field in ('coverage_windows','customer_windows'):
   for w in sequence(op[field],100):
    fields(w,{'start','end'},('start','end'));integer(w['start'],0,1439);integer(w['end'],1,1440)
  integer(op['staffing_open'],0,1440);integer(op['staffing_close'],0,1440)
  if not re.fullmatch('[0-9a-f]{64}',str(op['signature'])):fail('invalid operating signature.')
 for absence in sequence(value.get('absences',[]),100):
  fields(absence,{'employee_id','name','reason','original_start','original_end'},('employee_id','name','reason','original_start','original_end'))
  if absence['employee_id'] not in employees:fail('absence references another team.')
  string(absence['name'],100);string(absence['reason'],300);integer(absence['original_start'],0,1439);integer(absence['original_end'],1,1440)
 daily.validate(value)

def _validate(value):
 bounded_tree(value)
 fields(value,{'schema','created','hours_basis','includes','excludes','team','staffing','schedules','sha256','work_records'},('schema','created','hours_basis','includes','excludes','team','staffing','schedules','sha256'))
 modern=value['schema']==SCHEMA_V2
 if value['schema'] not in (SCHEMA,SCHEMA_V2) or value['hours_basis']!=('separate_planned_and_recorded_work' if modern else 'planned_not_timesheets') or value['includes']!=(INCLUDES+['recorded_work'] if modern else INCLUDES) or value['excludes']!=EXCLUDES:fail('unsupported file type or content scope.')
 if not modern and 'work_records' in value:fail('work records require the v2 team format.')
 if envelope_digest({k:v for k,v in value.items() if k!='sha256'})!=value['sha256']:fail('file content digest changed.')
 string(value['created'],80);fields(value['team'],{'title','fictional_example'},('title','fictional_example'));string(value['team']['title'],100)
 if not isinstance(value['team']['fictional_example'],bool):fail('invalid example marker.')
 data=fields(value['staffing'],{'employees','settings','selected_week','events'},('employees','settings','selected_week','events'))
 employees={};names=set()
 for e in sequence(data['employees'],MAX_EMPLOYEES):
  employee(e)
  if e['id'] in employees or e['name'].casefold() in names:fail('duplicate employee identity/name.')
  employees[e['id']]=e;names.add(e['name'].casefold())
 if modern:
  from work_history import validate_record
  ids=set()
  for row in sequence(value.get('work_records'),20000):
   validate_record(row,employees)
   if row['id'] in ids:fail('duplicate work record.')
   ids.add(row['id'])
 settings(data['settings']);staff.week_start(data['selected_week'])
 for event in sequence(data['events'],20000):
  fields(event,{'at','kind','employee_id','name','effective_date','proposal_id'},('at','kind'));string(event['at'],80);string(event['kind'],80)
  if 'employee_id' in event and event['employee_id'] not in employees:fail('event references another team.')
  if 'effective_date' in event:day(event['effective_date'])
  if 'name' in event:string(event['name'],100)
  if 'proposal_id' in event:identity(event['proposal_id'])
 schedules=fields(value['schedules'],{'selected_date','days'},('selected_date','days'))
 if schedules['selected_date'] is not None:day(schedules['selected_date'])
 if not isinstance(schedules['days'],dict) or len(schedules['days'])>MAX_DAYS:fail('too many schedule dates.')
 total=0
 for key,entry in schedules['days'].items():
  day(key);fields(entry,{'revisions'},('revisions',));rows=sequence(entry['revisions'],MAX_REVISIONS)
  if not rows:fail('empty saved schedule history.')
  total+=len(rows)
  if total>10000:fail('too many schedule revisions.')
  for i,row in enumerate(rows,1):plan(row,key,employees,i)
 return value

def validate(value):
 try:return _validate(value)
 except (TypeError,KeyError,IndexError,OverflowError,RecursionError) as exc:
  raise ValueError('Team file has an invalid record structure; nothing was opened.') from exc

def decode(text):
 if not isinstance(text,str) or len(text)>MAX_BYTES:fail('choose a team JSON file smaller than 5 MB.')
 raw=text.encode('utf-8')
 if len(raw)>MAX_BYTES:fail('choose a team JSON file smaller than 5 MB.')
 def pairs(rows):
  value={}
  for k,v in rows:
   if k in value:fail('duplicate JSON field.')
   value[k]=v
  return value
 try:value=json.loads(text,object_pairs_hook=pairs,parse_constant=lambda _:fail('non-finite JSON number.'))
 except (ValueError,RecursionError,UnicodeError) as exc:raise ValueError('Team file could not be read: '+str(exc)[:160]) from exc
 return validate(value)

def summary(value):
 keys=sorted(value['schedules']['days'])
 return {'title':value['team']['title'],'fictional_example':value['team']['fictional_example'],'employees':len(value['staffing']['employees']),'schedule_dates':len(keys),'first_schedule_date':keys[0] if keys else None,'last_schedule_date':keys[-1] if keys else None,'hours_basis':value['hours_basis'],'work_records':len(value.get('work_records',[])),'includes':value['includes'][:],'excludes':EXCLUDES[:]}

def export_team(store,expected_team_id):
 with store.lock:
  if store.production_id!=expected_team_id:fail('selected team changed before Save copy.')
  # Copy first: the existing default initializers may modify only this detached view.
  trial=copy(store);trial.data=deepcopy(store.data);trial.save=lambda:None
  item=next((p for p in trial.data['productions'] if p['id']==expected_team_id),None)
  if item is None:fail('selected team is missing.')
  book=staff.book(trial);schedules=daily.book(trial)
  value={'schema':SCHEMA,'created':briefing.now(),'hours_basis':'planned_not_timesheets','includes':INCLUDES[:],'excludes':EXCLUDES[:],'team':{'title':item['title'],'fictional_example':bool(item.get('fictional_example',False))},'staffing':{k:deepcopy(book[k]) for k in ('employees','settings','selected_week','events')},'schedules':deepcopy(schedules)}
  value.update(schema=SCHEMA_V2,hours_basis='separate_planned_and_recorded_work',includes=INCLUDES+['recorded_work'],work_records=deepcopy(trial.data.get('work_records',{}).get(expected_team_id,[])))
  value['sha256']=envelope_digest(value);validate(value)
  text=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
  if len(text.encode('utf-8'))>MAX_BYTES:fail('team exceeds the 5 MB portable-file limit.')
  name=re.sub(r'[^\w .-]','_',item['title']).strip(' .')[:70] or 'ShiftBrief-team'
  return {'filename':name+'.shiftbrief.json','content_type':'application/json','text':text,'sha256':hashlib.sha256(text.encode()).hexdigest(),'summary':summary(value)}

def _change(store,expected_team_id,request_id,request,operation):
 identity(request_id);binding=envelope_digest({'expected_team_id':expected_team_id,'request':request})
 with store.lock:
  operations=store.data.get('team_file_operations',[])
  prior=next((r for r in operations if r['request_id']==request_id),None)
  if prior:
   if prior['binding_sha256']!=binding:fail('request identifier was reused for different file input.')
   if not any(p['id']==prior['result']['team_id'] for p in store.data['productions']):fail('previously opened team is no longer present.')
   return {**deepcopy(prior['result']),'replayed':True}
  if store.production_id!=expected_team_id:fail('selected team changed before this action.')
  for field in ('browser_jobs','remote_planning_jobs'):
   if any(j.get('status')=='running' for j in store.data.get(field,[])):fail('wait for the current planning job before opening a team.')
  if len(operations)>=1000:fail('portable action history is full; no action was repeated.')
  previous=store.data;trial=copy(store);trial.data=deepcopy(previous);trial.save=lambda:None
  result=operation(trial)
  trial.data.setdefault('team_file_operations',[]).append({'request_id':request_id,'binding_sha256':binding,'result':deepcopy(result)})
  store.data=trial.data
  try:
   store.save()
   saved=json.loads((store.path/'state.json').read_text(encoding='utf-8'))
   if saved!=trial.data:raise OSError('Team file change was not durably saved.')
  except BaseException:
   try:saved=json.loads((store.path/'state.json').read_text(encoding='utf-8'))
   except (OSError,ValueError):saved=None
   if saved==trial.data:return deepcopy(result)
   store.data=previous
   raise
  return deepcopy(result)

def _append(trial,title,content=None):
 if len(trial.data['productions'])>=1000:fail('workspace already has 1000 teams.')
 pid=uuid.uuid4().hex[:20]
 while any(p['id']==pid for p in trial.data['productions']):pid=uuid.uuid4().hex[:20]
 item={'id':pid,'title':title}
 if content:item.update(fictional_example=content['team']['fictional_example'],imported_team_file_sha256=content['sha256'])
 trial.data['productions'].append(item);trial.data['current_production']=pid
 if content:
  trial.data.setdefault('staffing',{})[pid]={**deepcopy(content['staffing']),'proposals':[]}
  trial.data.setdefault('shift_schedules',{})[pid]=deepcopy(content['schedules'])
  trial.data.setdefault('work_records',{})[pid]=deepcopy(content.get('work_records',[]))
 else:staff.book(trial);daily.book(trial)
 # No approval, actionable proposal, job, watcher or assistant context is imported.
 return {'created':True,'team_id':pid,'title':title,'replayed':False,'summary':summary(content) if content else {'title':title,'employees':0,'schedule_dates':0,'hours_basis':'planned_not_timesheets'}}

def new_team(store,title,expected_team_id,request_id):
 string(title,100);title=title.strip()
 return _change(store,expected_team_id,request_id,{'operation':'new','title':title},lambda s:_append(s,title))

def open_team(store,text,expected_team_id,request_id):
 value=decode(text)
 return _change(store,expected_team_id,request_id,{'operation':'open','file_sha256':hashlib.sha256(text.encode()).hexdigest()},lambda s:_append(s,value['team']['title'],value))
