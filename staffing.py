"""Staff directory and reviewable weekly scheduling over recorded availability.

No availability is invented. Proposals keep roster/schedule fingerprints and
must be accepted explicitly. Hours are planning measures, not payroll/legal rules.
"""
from copy import deepcopy
from datetime import date,timedelta
import re,uuid,json
from briefing import digest,now
import shift_schedule as daily
import operating_hours


def week_start(value):
 day=date.fromisoformat(daily.day_key(value))
 if day.weekday()!=6:raise ValueError('Choose a Sunday as the first day of this seven-day schedule.')
 return day.isoformat()
def days(week):return [(date.fromisoformat(week_start(week))+timedelta(days=i)).isoformat() for i in range(7)]
def current_sunday(today=None):
 today=today or date.today();return (today-timedelta(days=(today.weekday()+1)%7)).isoformat()
def next_sunday(today=None):return (date.fromisoformat(current_sunday(today))+timedelta(days=7)).isoformat()
def book(store):return store.data.setdefault('staffing',{}).setdefault(store.production_id,{'employees':[],'settings':{'hours_confirmed':False,'overtime_hours':40,'roles':{'Team':1},'open':'09:00','close':'17:00'},'selected_week':next_sunday(),'proposals':[],'events':[]})
def stamp(value):return digest(value)
def employee(store,identity):
 rows=[e for e in book(store)['employees'] if e['id']==identity or e['name'].casefold()==str(identity).strip().casefold()]
 if len(rows)!=1:raise ValueError('Choose one saved employee by name or from the employee list.')
 return rows[0]
def active(e,day):return e['start_date']<=day and (not e.get('end_date') or day<e['end_date'])
def available(e,day):
 if not active(e,day) or day in e.get('time_off',{}):return []
 row=e.get('availability',{}).get(day)
 if row and row.get('status')=='off':return []
 windows=[{'start':w['start'],'end':min(1440,w['end'])} for w in (row or {}).get('windows',[]) if row.get('status')=='available' and w['start']<1440]
 prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat();previous=e.get('availability',{}).get(prior,{})
 if previous.get('status')=='available' and active(e,prior) and prior not in e.get('time_off',{}):
  windows.extend({'start':0,'end':min(1440,w['end']-1440)} for w in previous['windows'] if w['end']>1440)
 merged=[]
 for w in sorted(windows,key=lambda w:w['start']):
  if merged and w['start']<=merged[-1]['end']:merged[-1]['end']=max(merged[-1]['end'],w['end'])
  else:merged.append(w)
 return merged
def qualifies(e,role):return role=='Team' or role.casefold() in {r.casefold() for r in e.get('roles',[])}
def roster_fingerprint(store):return stamp({'employees':book(store)['employees'],'settings':book(store)['settings']})
def schedule_fingerprint(store,week):return stamp([daily.latest(store,d) for d in days(week)])
def hours_by_employee(store,week):
 totals={e['id']:0 for e in book(store)['employees']}
 for key in days(week):
  plan=daily.latest(store,key)
  for shift in (plan or {}).get('shifts',[]):
   ident=shift.get('employee_id')
   if not ident:
    matches=[e for e in book(store)['employees'] if e['name'].casefold()==shift['employee'].casefold()]
    ident=matches[0]['id'] if len(matches)==1 else shift['employee']
   totals[ident]=totals.get(ident,0)+shift['end']-shift['start']-sum(b['end']-b['start'] for b in shift.get('breaks',[]))
 return totals

def save_employee(store,values):
 with store.lock:
  data=book(store);existing=next((e for e in data['employees'] if e['id']==values.get('id')),None)
  if existing and values.get('expected_revision')!=existing.get('revision',1):raise ValueError('Employee details changed after this form opened. Reopen the employee to review current details before saving.')
  if values.get('id') and existing is None:raise ValueError('Employee not found in this team.')
  working=deepcopy(existing) if existing else {'id':uuid.uuid4().hex[:12],'availability':{},'time_off':{},'history':[],'end_date':None}
  name=values.get('name',working.get('name'))
  if not isinstance(name,str) or not 1<=len(name.strip())<=100:raise ValueError('Enter the employee’s name.')
  if any(e['id']!=working['id'] and e['name'].casefold()==name.strip().casefold() for e in data['employees']):raise ValueError('That name already exists. Add a distinguishing name or edit the existing employee.')
  working['name']=name.strip();working['start_date']=daily.day_key(values.get('start_date',working.get('start_date')))
  if 'end_date' in values:working['end_date']=daily.day_key(values['end_date']) if values['end_date'] else None
  if working['end_date'] and working['end_date']<working['start_date']:raise ValueError('The unavailable-from date cannot precede the hire date.')
  roles=values.get('roles',working.get('roles',[]))
  if not isinstance(roles,list) or len(roles)>12 or any(not isinstance(r,str) or not r.strip() or len(r)>60 for r in roles):raise ValueError('Use up to twelve recorded role names.')
  working['roles']=list(dict.fromkeys(r.strip() for r in roles))
  for field in ('phone','email','preferences'):
   value=values.get(field,working.get(field,''))
   if not isinstance(value,str) or len(value)>800:raise ValueError('Keep contact/preferences fields within 800 characters.')
   working[field]=value.strip()
  if 'week_start' in values:
   week=week_start(values['week_start']);weekdays=days(week);rows=values.get('availability')
   if not isinstance(rows,list) or len(rows)!=7 or any(not isinstance(r,dict) for r in rows) or {r.get('date') for r in rows}!=set(weekdays):raise ValueError('Supply one availability row for each of the seven displayed dates.')
   for row in rows:
    key=row['date'];status=row.get('status')
    if status not in ('unknown','off','available'):raise ValueError('Choose Available, Off or Not provided for each day.')
    windows=[]
    if status=='available':
     start,end=daily.clock(row.get('start')),daily.clock(row.get('end'));next_day=row.get('end_next_day',False)
     if not isinstance(next_day,bool):raise ValueError('Specify whether availability ends the next day.')
     if next_day:end+=1440
     if not 0<=start<1440 or not 0<end-start<=1440:raise ValueError('End must follow start, with next-day explicitly checked for overnight availability; use at most 24 hours.')
     windows=[{'start':start,'end':end}]
    preference=row.get('preference','')
    if not isinstance(preference,str) or len(preference)>200:raise ValueError('Keep each dated preference within 200 characters.')
    working['availability'][key]={'status':status,'windows':windows,'preference':preference.strip(),'end_next_day':bool(row.get('end_next_day'))}
   data['selected_week']=week
  working['revision']=working.get('revision',0)+1
  working['history'].append({'at':now(),'operation':'employee_details_saved','snapshot':{k:deepcopy(v) for k,v in working.items() if k!='history'}})
  if existing:existing.clear();existing.update(working)
  else:data['employees'].append(working)
  data['events'].append({'at':now(),'kind':'employee_saved','employee_id':working['id'],'name':working['name']});store.save();return deepcopy(working)

def end_employment(store,identity,effective_date,reason):
 with store.lock:
  e=employee(store,identity);end=daily.day_key(effective_date)
  if end<e['start_date']:raise ValueError('The effective end date precedes this employee’s start date.')
  e['end_date']=end;e['revision']=e.get('revision',1)+1;e['history'].append({'at':now(),'operation':'employment_ended','effective_date':end,'reason':str(reason)[:300]});book(store)['events'].append({'at':now(),'kind':'employment_ended','employee_id':e['id'],'effective_date':end});store.save();return deepcopy(e)

def time_off(store,identity,start,end,reason='Time off requested'):
 with store.lock:
  e=employee(store,identity);a=date.fromisoformat(daily.day_key(start));b=date.fromisoformat(daily.day_key(end))
  if not 0<=(b-a).days<=366:raise ValueError('Choose an ordered time-off range of at most 367 days.')
  for n in range((b-a).days+1):e['time_off'][(a+timedelta(days=n)).isoformat()]=str(reason)[:300]
  e['revision']=e.get('revision',1)+1
  e['history'].append({'at':now(),'operation':'time_off_recorded','start':a.isoformat(),'end':b.isoformat(),'reason':str(reason)[:300]});store.save();return deepcopy(e)

def settings(store,values):
 if not isinstance(values,dict) or set(values)-{'open','close','roles','overtime_hours'}:raise ValueError('Use coverage settings here; operating hours and closures require their reviewed proposal.')
 with store.lock:
  value=deepcopy(book(store)['settings']);value.update(values)
  if 'open' in values or 'close' in values:value['hours_confirmed']=True
  if daily.clock(value['open'])>=daily.clock(value['close']):raise ValueError('Closing must follow opening on a single date.')
  threshold=value['overtime_hours']
  if isinstance(threshold,bool) or not isinstance(threshold,(int,float)) or not 1<=threshold<=168:raise ValueError('Use a projected overtime threshold from 1 to 168 hours per week.')
  roles=value['roles']
  if not isinstance(roles,dict) or not 1<=len(roles)<=10 or any(not isinstance(k,str) or not k.strip() or isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=30 for k,v in roles.items()):raise ValueError('Specify one to ten roles and their required headcounts.')
  if any(k.casefold()=='team' for k in roles) and len(roles)>1:raise ValueError('Use Team for general headcount alone, or list distinct required roles without Team.')
  if len({k.casefold() for k in roles})!=len(roles):raise ValueError('Role names must be distinct.')
  book(store)['settings']=value;store.save();return deepcopy(value)

def role_coverage(plan):
 if not plan:return None
 base=daily.coverage(plan);requirements=plan.get('role_requirements',{'Team':plan['minimum']});rows=[]
 for segment in base['segments']:
  a,b=segment['start'],segment['end'];on=[s for s in plan['shifts'] if s['start']<=a and s['end']>=b and not any(x['start']<b and x['end']>a for x in s['breaks'])]
  counts={role:len({s.get('employee_id',s['employee'].casefold()) for s in on if role=='Team' or s.get('role','').casefold()==role.casefold()}) for role in requirements}
  rows.append({**segment,'roles':counts,'role_missing':{role:max(0,count-counts[role]) if segment.get('required',plan['minimum']) else 0 for role,count in requirements.items()}})
 base['segments']=rows;base['role_requirements']=requirements;base['role_missing_person_minutes']=sum((r['end']-r['start'])*sum(r['role_missing'].values()) for r in rows);return base

def _proposal(store,kind,week,payload):
 before=deepcopy(store.data) if payload.get('constraints') else None
 value={'id':uuid.uuid4().hex[:12],'kind':kind,'created':now(),'week_start':week,'roster_sha256':roster_fingerprint(store),'schedule_sha256':schedule_fingerprint(store,week),'payload':payload};value['sha256']=stamp(value)
 try:
  book(store)['proposals'].append(value);book(store)['selected_week']=week;store.save()
  if before is not None and json.loads((store.path/'state.json').read_text(encoding='utf-8'))!=store.data:raise OSError('The constrained proposal was not durably saved.')
 except Exception:
  if before is not None:store.data=before
  raise
 return deepcopy(value)

def calculate_week(store,week,*,constraints=None):
 with store.lock:
  week=week_start(week);data=book(store);cfg=data['settings']
  if constraints:
   import staffing_constraints as rule
   rule.verify_policy(store,week,constraints)
  if not cfg.get('hours_confirmed') and not cfg.get('operating_hours'):raise ValueError('Review your customer opening hours and opening/closing staffing buffers first. Say the hours and weekdays to Sarah, or open Customer hours in Settings. The displayed 9am–5pm starting values are not confirmed business facts.')
  totals={e['id']:0 for e in data['employees']};plans=[];unknown=[]
  for key in days(week):
   op=operating_hours.resolve(store,key);start,end=op['staffing_open'],op['staffing_close'];boundaries=set(range(start,end,15))|{end}|{t for w in op['coverage_windows'] for t in (w['start'],w['end'])};eligible=[e for e in data['employees'] if active(e,key)]
   if constraints:boundaries.update(t for t in rule.boundaries(constraints,key) if start<t<end)
   for e in eligible:
    if e['availability'].get(key,{}).get('status','unknown')=='unknown':unknown.append({'employee':e['name'],'date':key})
    for w in available(e,key):boundaries.update(x for x in (w['start'],w['end']) if start<x<end)
   slots=sorted(boundaries);runs=[];previous={}
   for a,b in zip(slots,slots[1:]):
    if not any(w['start']<=a and w['end']>=b for w in op['coverage_windows']):previous={};continue
    used=set();chosen={}
    for role,needed in cfg['roles'].items():
     candidates=[e for e in eligible if qualifies(e,role) and any(w['start']<=a and w['end']>=b for w in available(e,key))]
     if constraints:candidates=[e for e in candidates if rule.allows(constraints,e['id'],key,a,b,totals[e['id']])]
     candidates.sort(key=lambda e:(max(0,totals[e['id']]+b-a-cfg['overtime_hours']*60),0 if previous.get(e['id'])==role else 1,totals[e['id']],e['name'].casefold()))
     for e in [e for e in candidates if e['id'] not in used][:needed]:
      used.add(e['id']);chosen[e['id']]=role;totals[e['id']]+=b-a
      run=next((r for r in reversed(runs) if r['employee_id']==e['id'] and r['role']==role and r['end']==a),None)
      if run:run['end']=b
      else:runs.append({'id':uuid.uuid4().hex[:12],'employee_id':e['id'],'employee':e['name'],'role':role,'start':a,'end':b,'breaks':[]})
    previous=chosen
   plan={'date':key,'open':start,'close':end,'minimum':sum(cfg['roles'].values()),'role_requirements':deepcopy(cfg['roles']),'coverage_windows':deepcopy(op['coverage_windows']),'operating_hours':op,'shifts':runs};daily.validate(plan);plans.append(plan)
  payload={'days':plans,'hours':[{'employee_id':e['id'],'name':e['name'],'minutes':totals[e['id']],'projected_overtime_minutes':max(0,totals[e['id']]-cfg['overtime_hours']*60),'preferences':e['preferences']} for e in data['employees']],'unknown_availability':unknown,'time_off':[{'employee':e['name'],'date':d,'reason':why} for e in data['employees'] for d,why in e['time_off'].items() if d in days(week)],'preferences_need_review':True,'breaks_assigned':False,'note':'Proposal uses entered dated availability and recorded roles. Free-text preferences are surfaced for owner review; they are not silently treated as parsed constraints. Lunch breaks remain to be scheduled.'}
  return payload

def suggest_week(store,week,*,agent_provenance=None,constraints=None):
 with store.lock:
  week=week_start(week);payload=calculate_week(store,week,constraints=constraints)
  if agent_provenance is not None:payload['agent_provenance']=deepcopy(agent_provenance)
  if constraints:
   import staffing_constraints as rule
   rule.verify_shifts(store,week,constraints,payload['days'])
   saved=[daily.latest(store,key) for key in days(week)]
   automatic=calculate_week(store,week)['days']
   payload['constraints']=deepcopy(constraints);payload['saved_before']=deepcopy(saved);payload['automatic_before']=automatic
   payload['changes_from_saved']=rule.changes(saved,payload['days']);payload['changes_from_automatic']=rule.changes(automatic,payload['days'])
   payload['note']='The literal request and interpreted exclusions/caps are shown for review. Saved availability and employment facts remain authoritative. Lunch breaks remain to be scheduled.'
  return _proposal(store,'week',week,payload)

def check_proposal(store,identity,expected):
 p=next((p for p in book(store)['proposals'] if p['id']==identity),None)
 if not p or p.get('accepted_at') or p['sha256']!=expected or stamp({k:v for k,v in p.items() if k!='sha256'})!=expected:raise ValueError('This proposal is no longer current. Request a fresh suggestion.')
 if next((x['id'] for x in reversed(book(store)['proposals']) if x['kind']==p['kind'] and x['week_start']==p['week_start']),None)!=identity:raise ValueError('A newer suggestion exists. Review the latest proposal.')
 if p['roster_sha256']!=roster_fingerprint(store) or p['schedule_sha256']!=schedule_fingerprint(store,p['week_start']):raise ValueError('Staff details or saved schedules changed. Request a fresh suggestion before accepting.')
 if p['payload'].get('constraints'):
  import staffing_constraints as rule
  rule.verify_shifts(store,p['week_start'],p['payload']['constraints'],p['payload']['days'])
 return p

def accept(store,identity,expected,choice=None):
 with store.lock:
  p=check_proposal(store,identity,expected)
  if p['kind']=='week':plans=p['payload']['days']
  elif p['kind']=='lunch':
   candidate=next((c for c in p['payload']['choices'] if c['id']==choice),None)
   if not candidate:raise ValueError('Select a lunch option to accept.')
   plan=daily.latest(store,p['payload']['date']);shift=next(s for s in plan['shifts'] if s['id']==p['payload']['shift_id']);shift['breaks'].append({'id':uuid.uuid4().hex[:12],'label':'Lunch','start':candidate['start'],'end':candidate['end']});plans=[plan]
  elif p['kind']=='sick':
   candidate=next((c for c in p['payload']['choices'] if c['id']==choice),None)
   if not candidate:raise ValueError('Select a replacement or partial extension to accept.')
   plan=daily.latest(store,p['payload']['date']);absent=next(s for s in plan['shifts'] if s['id']==p['payload']['absent_shift_id']);plan['shifts'].remove(absent)
   if candidate.get('extend_shift_id'):
    shift=next(s for s in plan['shifts'] if s['id']==candidate['extend_shift_id']);shift['start']=min(shift['start'],candidate['start']);shift['end']=max(shift['end'],candidate['end'])
   else:plan['shifts'].append({'id':uuid.uuid4().hex[:12],'employee_id':candidate['employee_id'],'employee':candidate['name'],'role':absent.get('role','Team'),'start':candidate['start'],'end':candidate['end'],'breaks':[]})
   plan.setdefault('absences',[]).append({'employee_id':p['payload']['absent_employee_id'],'name':absent['employee'],'reason':'Reported sick by owner','original_start':absent['start'],'original_end':absent['end']});plans=[plan]
  else:raise ValueError('Unknown staffing proposal.')
  for plan in plans:daily.validate(plan)
  before=deepcopy(store.data);selected=daily.book(store)['selected_date']
  try:
   for plan in plans:daily._save(store,plan,'Accepted '+p['kind']+' proposal '+p['id'],persist=False)
   daily.book(store)['selected_date']=selected if selected in days(p['week_start']) else p['week_start']
   p['accepted_at']=now();book(store).setdefault('week_reviews',{})[p['week_start']]={'at':now(),'roster_sha256':roster_fingerprint(store),'schedule_sha256':schedule_fingerprint(store,p['week_start'])};store.save()
   if p['payload'].get('constraints') and json.loads((store.path/'state.json').read_text(encoding='utf-8'))!=store.data:raise OSError('The accepted week was not durably saved.')
  except Exception:
   store.data=before;raise
  return {'saved':True,'dates':[plan['date'] for plan in plans]}


def suggest_lunch(store,shift_id,key,duration=30,window_start='11:00',window_end='14:00'):
 with store.lock:
  plan=daily.latest(store,daily.day_key(key))
  if not plan:raise ValueError('Choose a saved dated schedule before asking for lunch coverage.')
  if operating_hours.resolve(store,key)['closed']:raise ValueError('This date is now closed. Review and replace its old schedule before planning lunch.')
  shift=next((s for s in plan['shifts'] if s['id']==shift_id),None)
  if not shift:raise ValueError('Choose the employee’s shift.')
  if isinstance(duration,bool) or not isinstance(duration,int) or not 10<=duration<=120:raise ValueError('Choose a lunch length of 10–120 minutes.')
  a=max(shift['start'],daily.clock(window_start));b=min(shift['end'],daily.clock(window_end));baseline=role_coverage(plan)['role_missing_person_minutes'];choices=[]
  for start in range(a,b-duration+1,15):
   end=start+duration
   if any(br['start']<end and br['end']>start for br in shift['breaks']):continue
   candidate=deepcopy(plan);target=next(s for s in candidate['shifts'] if s['id']==shift_id);target['breaks'].append({'id':'preview','label':'Lunch','start':start,'end':end});report=role_coverage(candidate)
   choices.append({'id':uuid.uuid4().hex[:12],'start':start,'end':end,'extra_missing_person_minutes':report['role_missing_person_minutes']-baseline,'gap_free':report['role_missing_person_minutes']==0})
  choices.sort(key=lambda c:(c['extra_missing_person_minutes'],c['start']));week=current_sunday(date.fromisoformat(key));return _proposal(store,'lunch',week,{'date':key,'shift_id':shift_id,'employee':shift['employee'],'choices':choices[:8],'note':'Ranked by additional role-coverage gaps. No break is applied until you select and accept an option.'})

def suggest_sick(store,identity,key):
 with store.lock:
  key=daily.day_key(key);person=employee(store,identity);plan=daily.latest(store,key)
  if not plan:raise ValueError('Choose a saved schedule for the date of the sickness report.')
  shifts=[s for s in plan['shifts'] if s.get('employee_id')==person['id'] or s['employee'].casefold()==person['name'].casefold()]
  if len(shifts)!=1:raise ValueError('Choose the exact absent shift; this employee has none or multiple shifts on the selected date.')
  absent=shifts[0];a,b=absent['start'],absent['end']
  if not any(w['start']<=a and w['end']>=b for w in operating_hours.resolve(store,key)['coverage_windows']):raise ValueError('The absent shift conflicts with current staffing hours or a closed date. Revise the dated schedule before arranging a replacement.')
  week=current_sunday(date.fromisoformat(key));totals=hours_by_employee(store,week);threshold=book(store)['settings']['overtime_hours']*60;choices=[];excluded=[]
  for e in book(store)['employees']:
   if e['id']==person['id']:continue
   role=absent.get('role','Team')
   if not active(e,key) or not qualifies(e,role) or not available(e,key):excluded.append({'name':e['name'],'reason':'Not active, no recorded role qualification, unavailable or time off.'});continue
   own=[s for s in plan['shifts'] if s.get('employee_id')==e['id'] or s['employee'].casefold()==e['name'].casefold()];options=[]
   if not any(s['start']<b and s['end']>a for s in own) and any(w['start']<=a and w['end']>=b for w in available(e,key)):options.append((a,b,None,'Full shift'))
   for s in own:
    if s.get('role','Team')!=role:continue
    # Adjacent 2–3 hour extensions only, within recorded availability.
    for start,end,label in [(max(a,s['start']-180),min(b,s['start']),'Come in earlier'),(max(a,s['end']),min(b,s['end']+180),'Stay later')]:
     if 120<=end-start<=180 and (end==s['start'] or start==s['end']) and any(w['start']<=start and w['end']>=end for w in available(e,key)) and not any(o['id']!=s['id'] and o['start']<end and o['end']>start for o in own):options.append((start,end,s['id'],label))
   for start,end,extend,label in options:
    projected=totals.get(e['id'],0)+end-start
    choices.append({'id':uuid.uuid4().hex[:12],'employee_id':e['id'],'name':e['name'],'start':start,'end':end,'extend_shift_id':extend,'kind':label,'covered_minutes':end-start,'remaining_absent_minutes':max(0,b-a-(end-start)),'current_week_minutes':totals.get(e['id'],0),'projected_week_minutes':projected,'projected_overtime_minutes':max(0,projected-threshold),'phone':e['phone'],'email':e['email'],'preferences':e['preferences']})
  choices.sort(key=lambda c:(c['projected_overtime_minutes'],c['projected_week_minutes'],-c['covered_minutes'],c['name'].casefold()))
  return _proposal(store,'sick',week,{'date':key,'absent_employee_id':person['id'],'absent_name':person['name'],'absent_shift_id':absent['id'],'start':a,'end':b,'choices':choices,'excluded':excluded,'overtime_hours':threshold/60,'note':'Ordered from least projected overtime, then least projected weekly hours. Partial extensions can leave coverage gaps. Contacts are a call list only; no person has been contacted or agreed to work.'})

def view(store,today=None):
 data=book(store);week=data['selected_week'];current=[daily.latest(store,d) for d in days(week)];staff=deepcopy(data['employees']);totals=hours_by_employee(store,week);today=today or date.today();nextweek=next_sunday(today)
 from employee_pay import rate_on
 for e in staff:e['pay_current']=rate_on(e,today.isoformat());e.setdefault('pay_history',[])
 review=data.get('week_reviews',{}).get(nextweek,{})
 needs_review=not all(daily.latest(store,d) for d in days(nextweek)) or review.get('roster_sha256')!=roster_fingerprint(store) or review.get('schedule_sha256')!=schedule_fingerprint(store,nextweek)
 reminder={'due':today.weekday() in (3,4,5,6) and needs_review,'week_start':nextweek,'message':'Next week needs review. Check employee availability, preferences and time off before accepting a new schedule.'}
 return {'employees':staff,'pay_proposals':deepcopy(data.get('pay_proposals',[])[-12:]),'employee_imports':deepcopy(data.get('employee_imports',[])[-8:]),'settings':deepcopy(data['settings']),'operating_hours':operating_hours.settings(store),'operating_proposals':deepcopy(data.get('operating_proposals',[])[-6:]),'selected_week':week,'selected_date':daily.book(store)['selected_date'],'days':[{'date':d,'plan':p,'coverage':role_coverage(p),'conflicts':conflicts(store,p),'history':[{'number':r['number'],'created':r['created'],'source_message':r['source_message']} for r in daily.book(store)['days'].get(d,{}).get('revisions',[])]} for d,p in zip(days(week),current)],'hours':[{'id':e['id'],'name':e['name'],'minutes':totals.get(e['id'],0),'projected_overtime_minutes':max(0,totals.get(e['id'],0)-data['settings']['overtime_hours']*60)} for e in staff],'proposals':deepcopy(data['proposals'][-8:]),'reminder':reminder,'events':deepcopy(data['events'][-30:])}

def select_week(store,week):
 with store.lock:
  week=week_start(week);book(store)['selected_week']=week
  if daily.book(store)['selected_date'] not in days(week):daily.book(store)['selected_date']=week
  store.save();return {'selected':week}

def select_day(store,key):
 with store.lock:
  key=daily.day_key(key);book(store)['selected_week']=current_sunday(date.fromisoformat(key));daily.book(store)['selected_date']=key;store.save();return daily.view(store,key)

def edit_shift(store,values):
 """Explicit editor submission; reject unrecorded availability/role and overlaps."""
 with store.lock:
  key=daily.day_key(values.get('date'));plan=daily.latest(store,key)
  if not plan:raise ValueError('Accept or create a dated schedule first.')
  if values.get('expected_sha')!=plan['sha256']:raise ValueError('The saved schedule changed. Reload it before editing.')
  old=next((s for s in plan['shifts'] if s['id']==values.get('shift_id')),None)
  if values.get('shift_id') and old is None:raise ValueError('That shift is not in the current dated schedule.')
  if values.get('remove'):
   if not old:raise ValueError('Select a saved shift to remove.')
   plan['shifts'].remove(old)
  else:
   e=employee(store,values.get('employee_id'));start=daily.clock(values.get('start'));end=daily.clock(values.get('end'));role=values.get('role','Team')
   if values.get('end_next_day'):end+=1440
   if start>=end:raise ValueError('End must follow start on this calendar date.')
   op=operating_hours.resolve(store,key)
   if not any(w['start']<=start and w['end']>=end for w in op['coverage_windows']):raise ValueError('This shift is outside current staffing hours or a closed date. Overnight availability is projected into separate dated schedule rows.')
   if not any(w['start']<=start and w['end']>=end for w in available(e,key)):raise ValueError('This shift is outside the employee’s recorded availability, employment dates or time-off constraints. Edit the employee details first if those facts changed.')
   if not qualifies(e,role):raise ValueError('Record this employee’s role qualification before assigning that role.')
   if role not in plan.get('role_requirements',{'Team':plan['minimum']}):raise ValueError('Choose a required role in this dated schedule.')
   if any(s['id']!=values.get('shift_id') and s.get('employee_id')==e['id'] and s['start']<end and s['end']>start for s in plan['shifts']):raise ValueError('This employee already has overlapping work in this schedule.')
   item=old or {'id':uuid.uuid4().hex[:12],'breaks':[]};item.update(employee_id=e['id'],employee=e['name'],role=role,start=start,end=end)
   if not old:plan['shifts'].append(item)
  return daily._save(store,plan,'Owner edited a dated shift')

def conflicts(store,plan):
 result=[]
 if plan and plan.get('shifts'):
  op=operating_hours.resolve(store,plan['date'])
  for shift in plan['shifts']:
   if not any(w['start']<=shift['start'] and w['end']>=shift['end'] for w in op['coverage_windows']):result.append(shift['employee']+': saved work falls outside current staffing hours or on a closed date.')
 for s in (plan or {}).get('shifts',[]):
  try:
   e=employee(store,s.get('employee_id') or s['employee'])
   if not available(e,plan['date']) or not any(w['start']<=s['start'] and w['end']>=s['end'] for w in available(e,plan['date'])):result.append(s['employee']+': this saved shift conflicts with current availability, time off or employment dates.')
   if not qualifies(e,s.get('role','Team')):result.append(s['employee']+': current recorded role qualification does not match this saved shift.')
  except ValueError:result.append(s['employee']+': employee directory match is missing.')
 return result

def load_staff_example(store):
 """Explicit separate fictional team; never seed the owner's blank workspace."""
 with store.lock:
  existing=next((p for p in store.data['productions'] if p.get('staffing_sample')),None)
  if existing:store.select_production(existing['id']);return {'selected':True}
  team=store.create_production('Fictional store · scheduling example');next(p for p in store.data['productions'] if p['id']==team['id'])['staffing_sample']=True
  week='2026-09-13';select_week(store,week);settings(store,{'open':'09:00','close':'18:00','roles':{'Cashier':1,'Floor':1},'overtime_hours':40})
  for name,roles,pref,off in [('Adam',['Cashier'],'Prefers mornings; discuss before accepting.',6),('Lisa',['Cashier','Floor'],'Open to an earlier start when available.',2),('Maya',['Cashier'],'Prefers a consistent start time.',3),('Ben',['Floor'],'',4),('Noor',['Cashier','Floor'],'',5)]:
   save_employee(store,{'name':name,'start_date':'2026-09-01','roles':roles,'preferences':pref,'week_start':week,'availability':[{'date':d,'status':'off' if i==off else 'available','start':'09:00','end':'18:00'} for i,d in enumerate(days(week))]})
  time_off(store,'Maya','2026-09-18','2026-09-18','Fictional appointment, supplied in this example')
  store.save();return {'selected':True,'fictional':True}

def revise_week(store,identity,expected,plans):
 with store.lock:
  p=check_proposal(store,identity,expected)
  if p['kind']!='week' or not isinstance(plans,list) or len(plans)!=7 or [d.get('date') for d in plans]!=days(p['week_start']):raise ValueError('Edit the exact seven dates in this weekly proposal.')
  originals={d['date']:d for d in p['payload']['days']};clean=[]
  for raw in plans:
   original=originals[raw['date']];plan={k:deepcopy(original[k]) for k in ('date','open','close','minimum','role_requirements','coverage_windows','operating_hours')};plan['shifts']=[]
   for row in raw.get('shifts',[]):
    e=employee(store,row.get('employee_id'));a=daily.clock(row.get('start'));b=daily.clock(row.get('end'))+(1440 if row.get('end_next_day') else 0);role=row.get('role')
    if not any(w['start']<=a and w['end']>=b for w in plan['coverage_windows']):raise ValueError('A proposed shift cannot cross a closed date or sit outside staffing hours.')
    if role not in plan['role_requirements'] or not qualifies(e,role):raise ValueError('A proposed employee must have the recorded role required by this schedule.')
    if not any(w['start']<=a and w['end']>=b for w in available(e,plan['date'])):raise ValueError(e['name']+' is outside recorded availability on '+plan['date']+'.')
    if any(s['employee_id']==e['id'] and s['start']<b and s['end']>a for s in plan['shifts']):raise ValueError('Proposed shifts for the same employee overlap.')
    plan['shifts'].append({'id':uuid.uuid4().hex[:12],'employee_id':e['id'],'employee':e['name'],'role':role,'start':a,'end':b,'breaks':[]})
   daily.validate(plan);clean.append(plan)
  payload=deepcopy(p['payload']);payload['days']=clean;payload['revised_from']=p['id'];totals={e['id']:0 for e in book(store)['employees']}
  for plan in clean:
   for shift in plan['shifts']:totals[shift['employee_id']]+=shift['end']-shift['start']
  for row in payload['hours']:row['minutes']=totals[row['employee_id']];row['projected_overtime_minutes']=max(0,row['minutes']-book(store)['settings']['overtime_hours']*60)
  if payload.get('constraints'):
   import staffing_constraints as rule
   rule.verify_shifts(store,p['week_start'],payload['constraints'],clean)
   payload['changes_from_saved']=rule.changes(payload['saved_before'],clean);payload['changes_from_automatic']=rule.changes(payload['automatic_before'],clean)
  return _proposal(store,'week',p['week_start'],payload)


def restore_schedule(store,values):
 with store.lock:
  key=daily.day_key(values.get('date'));current=daily.latest(store,key)
  if not current or values.get('expected_sha')!=current['sha256']:raise ValueError('Review the current dated schedule before restoring history.')
  old=daily.view(store,key,values.get('number'))['plan'];issues=conflicts(store,old)
  if issues:raise ValueError('This history conflicts with current staff details or operating hours. Review those facts before restoring. '+issues[0])
  return daily.change(store,'restore',values,'Owner restored an earlier revision',values['expected_sha'])


def cancel_time_off(store,identity,key,expected_revision):
 with store.lock:
  e=employee(store,identity);key=daily.day_key(key)
  if expected_revision!=e.get('revision',1):raise ValueError('Employee details changed. Reopen this request before cancelling it.')
  if key not in e['time_off']:raise ValueError('This employee has no saved time-off request on that date.')
  reason=e['time_off'].pop(key);e['revision']=e.get('revision',1)+1;e['history'].append({'at':now(),'operation':'time_off_cancelled','date':key,'original_reason':reason});store.save();return {'saved':True}


def export_week(store,week):
 import csv,io,json,zipfile
 with store.lock:
  week=week_start(week);plans=[daily.latest(store,key) for key in days(week)]
  if not any(plans):raise ValueError('Save at least one dated schedule in this week before exporting.')
  summary=io.StringIO(newline='');writer=csv.writer(summary);writer.writerow(['Date','Revision','Employee','Role','Type','Start','End','Minutes'])
  cover=io.StringIO(newline='');cw=csv.writer(cover);cw.writerow(['Date','Revision','Start','End','On duty','Required role','Missing people'])
  for plan in plans:
   if not plan:continue
   for row in list(csv.reader(io.StringIO(daily.export_csv(plan))))[1:]:writer.writerow(row)
   for interval in role_coverage(plan)['segments']:
    for role,missing in interval['role_missing'].items():cw.writerow([plan['date'],plan['number'],daily.hm(interval['start']),daily.hm(interval['end']),interval['count'],role,missing])
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w',zipfile.ZIP_DEFLATED) as z:
   z.writestr('weekly-shifts.csv',summary.getvalue());z.writestr('coverage-intervals.csv',cover.getvalue());z.writestr('dated-schedules.json',json.dumps({'week_start':week,'exported':now(),'days':plans,'current_conflicts':[{'date':p['date'],'issues':conflicts(store,p)} for p in plans if p and conflicts(store,p)]},ensure_ascii=False,indent=2));z.writestr('README.txt','ShiftBrief selected-week export. These are saved plans and their revision numbers, not attendance, payroll, legal compliance or employee agreement. CSV break rows are separate from gross shift rows. Net planned work subtracts breaks. Dates with no saved plan are null in JSON. Midnight endpoints are 24:00 on the shown calendar date; overnight work is projected into separate calendar-date rows. See current_conflicts in JSON before relying on older plans. No contacts, unrelated teams or full employee directory are included.')
  return buf.getvalue()
