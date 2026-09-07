"""Dated team shifts, breaks and exact coverage. All changes keep local history."""
from copy import deepcopy
from datetime import date,datetime,timedelta
import csv,io,json,re,uuid
from briefing import digest,now

TIME=r'(?:\d{1,2}(?::\d{2})?\s*(?:am|pm)|\d{1,2}:\d{2})'
RANGE=r'('+TIME+r')\s*(?:to|until|[-–])\s*('+TIME+r')'

def clock(value):
 if not isinstance(value,str):raise ValueError('Use an explicit time such as 09:00 or 9am.')
 match=re.fullmatch(r'\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*',value,re.I)
 if not match or (not match[3] and match[2] is None):raise ValueError('Use 09:00 or 9am so the time is unambiguous.')
 hour,minute=int(match[1]),int(match[2] or 0)
 if hour==24 and minute==0 and not match[3]:return 1440
 if minute>59 or hour>23:raise ValueError('That clock time is invalid.')
 if match[3]:
  if not 1<=hour<=12:raise ValueError('Use an hour from 1 to 12 with am/pm.')
  hour=hour%12+(12 if match[3].lower()=='pm' else 0)
 return hour*60+minute

def hm(value):return f'{value//60:02d}:{value%60:02d}'
def day_key(value):
 if not isinstance(value,str):raise ValueError('Choose a date as YYYY-MM-DD.')
 try:return date.fromisoformat(value).isoformat()
 except ValueError as exc:raise ValueError('Choose a valid date as YYYY-MM-DD.') from exc

def book(store):return store.data.setdefault('shift_schedules',{}).setdefault(store.production_id,{'selected_date':None,'days':{}})
def latest(store,key=None):
 data=book(store);key=key or data['selected_date'];day=data['days'].get(key)
 return deepcopy(day['revisions'][-1]) if day else None

def validate(plan):
 day_key(plan['date'])
 if not 0<=plan['open']<plan['close']<=1440:raise ValueError('Closing must be after opening on this date. Split overnight work across dated schedules.')
 minimum=plan['minimum']
 if isinstance(minimum,bool) or not isinstance(minimum,int) or not 1<=minimum<=100:raise ValueError('Choose a required coverage of 1–100 people.')
 if len(plan['shifts'])>100:raise ValueError('Use at most 100 shifts for one date.')
 for shift in plan['shifts']:
  if not isinstance(shift['employee'],str) or not 1<=len(shift['employee'].strip())<=100:raise ValueError('Give the employee a name of 1–100 characters.')
  if not 0<=shift['start']<shift['end']<=1440:raise ValueError('A shift must end after it starts on this date.')
  intervals=sorted((b['start'],b['end']) for b in shift['breaks'])
  for i,(start,end) in enumerate(intervals):
   if not shift['start']<=start<end<=shift['end']:raise ValueError('Each break must fit inside that employee’s shift.')
   if i and start<intervals[i-1][1]:raise ValueError('Two breaks for the same shift overlap.')
 return plan

def _save(store,plan,message,persist=True):
 validate(plan);data=book(store);key=plan['date'];day=data['days'].setdefault(key,{'revisions':[]});value={k:deepcopy(v) for k,v in plan.items() if k not in ('sha256','number','created','source_message')};value.update(number=len(day['revisions'])+1,created=now(),source_message=message);value['sha256']=digest(value);day['revisions'].append(value);data['selected_date']=key
 if persist:store.save()
 return deepcopy(value)

def change(store,operation,values,message='Edited in schedule workspace',expected_sha=None):
 with store.lock:
  if not isinstance(values,dict):raise ValueError('Supply schedule details.')
  key=day_key(values.get('date') or book(store)['selected_date']);plan=latest(store,key)
  if expected_sha and (not plan or plan['sha256']!=expected_sha):raise ValueError('The schedule changed. Review its latest version before saving.')
  if operation=='day':
   plan=plan or {'date':key,'open':540,'close':1020,'minimum':1,'shifts':[]}
   plan.update(open=clock(values['open']),close=clock(values['close']),minimum=values.get('minimum',1))
  elif not plan:raise ValueError('Create the dated schedule and its opening hours first.')
  elif operation=='shift':
   old=next((s for s in plan['shifts'] if s['id']==values.get('shift_id')),None)
   if values.get('shift_id') and old is None:raise ValueError('That shift is not in the selected date.')
   item=old or {'id':uuid.uuid4().hex[:12],'breaks':[]}
   item.update(employee=str(values.get('employee') or (old or {}).get('employee','')).strip(),role=str(values.get('role',(old or {}).get('role',''))).strip()[:100],start=clock(values['start']),end=clock(values['end']))
   if not old:plan['shifts'].append(item)
  elif operation in ('break','remove_break','remove_shift'):
   shift=next((s for s in plan['shifts'] if s['id']==values.get('shift_id')),None)
   if not shift:raise ValueError('Choose a shift in this date.')
   if operation=='remove_shift':plan['shifts'].remove(shift)
   else:
    old=next((b for b in shift['breaks'] if b['id']==values.get('break_id')),None)
    if values.get('break_id') and not old:raise ValueError('Choose a saved break.')
    if operation=='remove_break':
     if not old:raise ValueError('Choose the break to remove.')
     shift['breaks'].remove(old)
    else:
     item=old or {'id':uuid.uuid4().hex[:12]};item.update(label=str(values.get('label','Lunch')).strip()[:60] or 'Break',start=clock(values['start']),end=clock(values['end']))
     if not old:shift['breaks'].append(item)
  elif operation=='restore':
   day=book(store)['days'][key];old=next((p for p in day['revisions'] if p['number']==values.get('number')),None)
   if not old:raise ValueError('Choose an existing history revision.')
   plan=deepcopy(old)
  else:raise ValueError('Unknown schedule action.')
  return _save(store,plan,message)

def coverage(plan):
 if not plan:return None
 boundaries={plan['open'],plan['close']}
 for window in plan.get('coverage_windows',[]):boundaries.update((window['start'],window['end']))
 for shift in plan['shifts']:
  boundaries.update(x for x in (shift['start'],shift['end']) if plan['open']<x<plan['close'])
  for br in shift['breaks']:boundaries.update(x for x in (br['start'],br['end']) if plan['open']<x<plan['close'])
 points=sorted(boundaries);segments=[]
 for a,b in zip(points,points[1:]):
  active=[s for s in plan['shifts'] if s['start']<=a and s['end']>=b and not any(br['start']<b and br['end']>a for br in s['breaks'])]
  names=list(dict.fromkeys(s['employee'].casefold() for s in active));labels=list(dict.fromkeys(s['employee'] for s in active))
  required=plan['minimum'] if 'coverage_windows' not in plan or any(w['start']<=a and w['end']>=b for w in plan['coverage_windows']) else 0
  segments.append({'start':a,'end':b,'count':len(names),'employees':labels,'required':required,'missing':max(0,required-len(names))})
 gaps=[]
 for seg in segments:
  if seg['missing']:
   if gaps and gaps[-1]['end']==seg['start'] and gaps[-1]['missing']==seg['missing']:gaps[-1]['end']=seg['end']
   else:gaps.append({'start':seg['start'],'end':seg['end'],'missing':seg['missing']})
 overlaps=[]
 for i,a in enumerate(plan['shifts']):
  for b in plan['shifts'][i+1:]:
   start,end=max(a['start'],b['start']),min(a['end'],b['end'])
   if a['employee'].casefold()==b['employee'].casefold() and start<end:overlaps.append({'employee':a['employee'],'start':start,'end':end,'shift_ids':[a['id'],b['id']]})
 return {'segments':segments,'gaps':gaps,'overlaps':overlaps,'uncovered_minutes':sum(s['end']-s['start'] for s in gaps),'missing_person_minutes':sum((s['end']-s['start'])*s['missing'] for s in segments),'scheduled_work_minutes':sum(s['end']-s['start']-sum(b['end']-b['start'] for b in s['breaks']) for s in plan['shifts']),'employees':len({s['employee'].casefold() for s in plan['shifts']}),'break_minutes':sum(b['end']-b['start'] for s in plan['shifts'] for b in s['breaks']),'claim':'Planned coverage, not attendance, payroll or labor-law verification.'}

def view(store,key=None,number=None):
 with store.lock:
  data=book(store);key=key or data['selected_date'];day=data['days'].get(key);plan=latest(store,key)
  if number is not None and day:plan=next((deepcopy(p) for p in day['revisions'] if p['number']==number),None)
  if number is not None and plan is None:raise ValueError('That schedule revision was not found.')
  return {'selected_date':key,'dates':sorted(data['days']),'plan':plan,'coverage':coverage(plan),'history':[{'number':p['number'],'created':p['created'],'source_message':p['source_message'],'sha256':p['sha256']} for p in (day or {}).get('revisions',[])],'read_only_history':bool(plan and day and plan['number']!=day['revisions'][-1]['number'])}

def summary(plan):
 if not plan:return 'Choose a date and its opening hours first. Then add the employees and their shifts; I will draw the coverage and break schedule from your entries.'
 c=coverage(plan);reply=f"{plan['date']}: {hm(plan['open'])}–{hm(plan['close'])}, minimum {plan['minimum']} on duty. {c['employees']} employees, {c['scheduled_work_minutes']/60:g} planned working hours after breaks."
 if c['gaps']:reply+='\nCoverage gaps:\n'+'\n'.join(f"{hm(g['start'])}–{hm(g['end'])}: need {g['missing']} more on duty." for g in c['gaps'])
 else:reply+='\nThe entered shifts cover the required headcount throughout the opening window.'
 if c['overlaps']:reply+='\nDuplicate employee overlaps: '+', '.join(f"{o['employee']} {hm(o['start'])}–{hm(o['end'])}" for o in c['overlaps'])+'. They are counted once for coverage.'
 return reply+'\nThis is the saved plan, not a confirmation that anyone attended or a labor-law check.'

def _employee(plan,text):
 wanted=text.strip().strip("’' ").casefold();matches=[s for s in plan['shifts'] if s['employee'].casefold()==wanted]
 if len(matches)!=1:raise ValueError('Name one employee with a single shift on this date, or select the exact shift in the schedule.')
 return matches[0]

def converse(store,message):
 """Return None for evidence chat; schedule requests return a saved, traced reply."""
 text=message.strip();low=text.casefold();data=book(store);selected=latest(store);date_match=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',text);key=date_match[1] if date_match else data['selected_date']
 time_range=re.search(RANGE,text,re.I)
 opening=bool(re.search(r'\b(?:open|opening|hours)\b',low))
 if opening and (re.search(r'\b(?:schedule|store|office|team|we|open)\b',low)):
  if not key:return {'answer':'Which date is this schedule for? Use YYYY-MM-DD so we save and revisit the right day. Include opening and closing times, for example 09:00 to 17:00.','kind':'schedule_clarification'}
  if not time_range:return {'answer':'What are the opening and closing times? Use 09:00 to 17:00 or 9am to 5pm.','kind':'schedule_clarification'}
  need=re.search(r'\b(?:need|minimum|at least)\s+(\d+)\s*(?:people|employees|staff|on duty)?',low);minimum=int(need[1]) if need else ((selected or {}).get('minimum',1))
  plan=change(store,'day',{'date':key,'open':time_range[1],'close':time_range[2],'minimum':minimum},message);return {'answer':'Saved the dated opening hours. '+('Required coverage is shown as 1 person; change it if your team needs more.\n' if not need and minimum==1 else '\n')+summary(plan),'kind':'schedule_saved'}
 if re.fullmatch(r'(?:show|open|revisit)\s+(?:the\s+)?(?:schedule\s+(?:for\s+)?)?\d{4}-\d{2}-\d{2}[.!]?',low):
  key=day_key(key)
  if key not in data['days']:return {'answer':'There is no saved schedule for '+key+'. Tell me its opening hours to start one.','kind':'schedule_clarification'}
  data['selected_date']=key;store.save();return {'answer':summary(latest(store,key)),'kind':'schedule_shown'}
 need=re.fullmatch(r'(?:we\s+)?(?:need|minimum|require)\s+(\d+)\s+(?:people|employees|staff)(?:\s+(?:on duty|all day))?[.!]?',low)
 if need:
  if not selected:return {'answer':summary(None),'kind':'schedule_clarification'}
  plan=change(store,'day',{'date':key,'open':hm(selected['open']),'close':hm(selected['close']),'minimum':int(need[1])},message);return {'answer':'Updated required coverage for the full opening window.\n'+summary(plan),'kind':'schedule_saved'}
 if re.search(r'\b(?:coverage|covers|uncovered|gaps|lunch cover|schedule history)\b',low) and not time_range:return {'answer':summary(selected),'kind':'schedule_answer'}
 # Match only complete supported edits. Unknown trailing details are never dropped.
 shift=re.fullmatch(r'(?:add|schedule)\s+(.+?)\s+(?:from\s+)?'+RANGE+r'(?:\s+as\s+(.+?))?[.!]?',text,re.I)
 works=re.fullmatch(r'(.+?)\s+works\s+(?:from\s+)?'+RANGE+r'(?:\s+as\s+(.+?))?[.!]?',text,re.I)
 revise=re.fullmatch(r'(?:change|move)\s+(.+?)(?:[’\']s)?\s+shift\s+(?:to\s+)?'+RANGE+r'[.!]?',text,re.I)
 br=re.fullmatch(r'(?:give|add|move|change)\s+(.+?)(?:[’\']s)?\s+(lunch|break)\s+(?:from\s+|to\s+)?'+RANGE+r'[.!]?',text,re.I)
 if shift or works or revise or br:
  if not selected:return {'answer':summary(None),'kind':'schedule_clarification'}
  match=shift or works or revise or br
  if br:
   employee=_employee(selected,br[1]);existing=[b for b in employee['breaks'] if b['label'].casefold()==br[2].casefold()];moving=low.startswith(('move','change'))
   if moving and len(existing)!=1:raise ValueError('Choose one existing '+br[2]+' to move in the schedule.')
   plan=change(store,'break',{'date':key,'shift_id':employee['id'],'break_id':existing[0]['id'] if moving else None,'label':br[2].title(),'start':br[3],'end':br[4]},message)
  else:
   employee=_employee(selected,revise[1]) if revise else None
   plan=change(store,'shift',{'date':key,'shift_id':employee['id'] if employee else None,'employee':employee['employee'] if employee else match[1],'start':match[2],'end':match[3],'role':(employee or {}).get('role','') if revise else (match[4] or '')},message)
  return {'answer':'Saved this schedule change. Earlier versions remain in date history.\n'+summary(plan),'kind':'schedule_saved'}
 if re.search(r'\b(?:schedule|shift|lunch|break|employee|staff)\b',low) and not re.search(r'\b(?:document|source|quote|handoff|decision)\b',low):
  return {'answer':'I can save dated team shifts and lunch breaks, then show who is on duty and where coverage is missing. Start with “Open 09:00 to 17:00 on 2026-09-08, need 2 people.” Then “Add Morgan from 09:00 to 17:00” and “Give Morgan lunch from 12:00 to 12:30.” Use your real date, names and times. Ambiguous or extra details need clarification before a schedule is changed.','kind':'schedule_clarification'}
 return None

def export_csv(plan):
 if not plan:raise ValueError('Choose a saved schedule first.')
 buf=io.StringIO(newline='');writer=csv.writer(buf);writer.writerow(['Date','Revision','Employee','Role','Type','Start','End','Minutes'])
 def cell(text):return "'"+text if text and text[0] in '=+-@\t\r' else text
 for shift in plan['shifts']:
  writer.writerow([plan['date'],plan['number'],cell(shift['employee']),cell(shift['role']),'Shift',hm(shift['start']),hm(shift['end']),shift['end']-shift['start']])
  for br in shift['breaks']:writer.writerow([plan['date'],plan['number'],cell(shift['employee']),cell(shift['role']),cell(br['label']),hm(br['start']),hm(br['end']),br['end']-br['start']])
 return buf.getvalue()
