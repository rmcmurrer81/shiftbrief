"""Customer hours, staffing buffers and owner-entered full-calendar-day closures.
Overnight windows are projected onto actual calendar dates. A closed date removes
all staffing bands on that date, including spillover from a neighboring day.
"""
from copy import deepcopy
from datetime import date,timedelta
import re,uuid
from briefing import digest,now
import shift_schedule as daily

DAY_NAMES=['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday']

def settings(store):
 import staffing
 cfg=staffing.book(store)['settings'];base={'mode':'hours','open':cfg['open'],'close':cfg['close'],'end_next_day':False,'before_minutes':0,'after_minutes':0}
 return deepcopy(cfg.get('operating_hours',{'weekdays':{str(i):deepcopy(base) for i in range(7)},'date_overrides':{},'closures':[]}))

def normalize_window(row):
 if not isinstance(row,dict):raise ValueError('Supply operating-hour details.')
 mode=row.get('mode','hours')
 if mode not in ('hours','24h','closed'):raise ValueError('Choose specific hours, open 24 hours, or closed.')
 before=row.get('before_minutes',0);after=row.get('after_minutes',0)
 if any(isinstance(n,bool) or not isinstance(n,int) or not 0<=n<=240 for n in (before,after)):raise ValueError('Use opening and closing staffing buffers from 0 to 240 minutes.')
 out={'mode':mode,'before_minutes':before,'after_minutes':after,'open':row.get('open','09:00'),'close':row.get('close','17:00'),'end_next_day':row.get('end_next_day',False)}
 if not isinstance(out['end_next_day'],bool):raise ValueError('End-next-day must be explicitly checked or unchecked.')
 if mode=='hours':
  a,b=daily.clock(out['open']),daily.clock(out['close'])
  if b==1440:b=0;out['end_next_day']=True
  b+=1440 if out['end_next_day'] else 0
  if not 0<=a<1440 or not 0<b-a<=1440:raise ValueError('Clarify AM/PM and whether closing is the next day. For continuous operation, choose Open 24 hours.')
  out['open']=daily.hm(a);out['close']=daily.hm(b%1440)
 return out

def validate(config):
 if not isinstance(config,dict):raise ValueError('Supply operating-hours settings.')
 if set(config.get('weekdays',{}))!={str(i) for i in range(7)}:raise ValueError('Provide all seven recurring weekdays, starting Sunday.')
 result={'weekdays':{k:normalize_window(v) for k,v in config['weekdays'].items()},'date_overrides':{},'closures':[]}
 for key,row in config.get('date_overrides',{}).items():result['date_overrides'][daily.day_key(key)]=normalize_window(row)
 for raw in config.get('closures',[]):
  kind=raw.get('kind');reason=raw.get('reason','')
  if not isinstance(reason,str) or not reason.strip() or len(reason)>400:raise ValueError('Give every closure a short owner-supplied reason.')
  entry={'id':raw.get('id') or uuid.uuid4().hex[:12],'kind':kind,'reason':reason.strip()}
  if kind=='date':entry['date']=daily.day_key(raw.get('date'))
  elif kind=='annual':
   month,day=raw.get('month'),raw.get('day')
   if isinstance(month,bool) or isinstance(day,bool) or not isinstance(month,int) or not isinstance(day,int):raise ValueError('Use an annual closure month and day.')
   try:date(2000,month,day)
   except ValueError as exc:raise ValueError('That recurring month/day does not exist.') from exc
   entry.update(month=month,day=day)
  else:raise ValueError('Choose a one-date or annual month/day closure.')
  result['closures'].append(entry)
 return result

def closure_reasons(config,key):
 day=date.fromisoformat(key);reasons=[x['reason'] for x in config['closures'] if (x['kind']=='date' and x['date']==key) or (x['kind']=='annual' and x['month']==day.month and x['day']==day.day)]
 row=config['date_overrides'].get(key,config['weekdays'][str((day.weekday()+1)%7)])
 if row['mode']=='closed':reasons.append('Owner-set closed date' if key in config['date_overrides'] else 'Closed every '+DAY_NAMES[(day.weekday()+1)%7])
 return reasons

def resolve(store,key):
 key=daily.day_key(key);config=settings(store);target=date.fromisoformat(key);reasons=closure_reasons(config,key)
 if reasons:return {'date':key,'closed':True,'closure_reasons':reasons,'bands':[],'coverage_windows':[],'customer_windows':[],'staffing_open':0,'staffing_close':1440,'signature':digest(config)}
 raw=[]
 for offset in (-1,0,1):
  anchor=target+timedelta(days=offset);anchor_key=anchor.isoformat()
  if closure_reasons(config,anchor_key):continue
  row=config['date_overrides'].get(anchor_key,config['weekdays'][str((anchor.weekday()+1)%7)])
  if row['mode']=='24h':a,b=0,1440
  else:a=daily.clock(row['open']);b=daily.clock(row['close'])+(1440 if row['end_next_day'] else 0)
  for start,end,kind in [(a-row['before_minutes'],a,'Opening staff'),(a,b,'Customer hours'),(b,b+row['after_minutes'],'Closing staff')]:
   start+=offset*1440;end+=offset*1440;start=max(0,start);end=min(1440,end)
   if start<end:raw.append({'start':start,'end':end,'kind':kind,'business_date':anchor_key})
 boundaries=sorted({t for r in raw for t in (r['start'],r['end'])});bands=[]
 for a,b in zip(boundaries,boundaries[1:]):
  on=[r for r in raw if r['start']<=a and r['end']>=b]
  if not on:continue
  kind='Customer hours' if any(r['kind']=='Customer hours' for r in on) else 'Opening staff' if any(r['kind']=='Opening staff' for r in on) else 'Closing staff'
  if bands and bands[-1]['end']==a and bands[-1]['kind']==kind:bands[-1]['end']=b
  else:bands.append({'start':a,'end':b,'kind':kind})
 windows=[]
 for r in bands:
  if windows and windows[-1]['end']==r['start']:windows[-1]['end']=r['end']
  else:windows.append({'start':r['start'],'end':r['end']})
 return {'date':key,'closed':not bands,'closure_reasons':[],'bands':bands,'coverage_windows':windows,'customer_windows':[{'start':r['start'],'end':r['end']} for r in bands if r['kind']=='Customer hours'],'staffing_open':min((r['start'] for r in bands),default=0),'staffing_close':max((r['end'] for r in bands),default=1440),'signature':digest(config)}

def propose(store,config,message):
 import staffing
 with store.lock:
  config=validate(config);p={'id':uuid.uuid4().hex[:12],'created':now(),'config':config,'source_message':message,'before_sha256':digest(settings(store))};p['sha256']=digest(p);staffing.book(store).setdefault('operating_proposals',[]).append(p);store.save();return deepcopy(p)

def accept(store,identity,sha):
 import staffing
 with store.lock:
  p=next((p for p in staffing.book(store).get('operating_proposals',[]) if p['id']==identity),None)
  if not p or p.get('accepted_at') or p['sha256']!=sha or digest({k:v for k,v in p.items() if k!='sha256'})!=sha:raise ValueError('This operating-hours proposal is no longer current.')
  if staffing.book(store)['operating_proposals'][-1]['id']!=identity:raise ValueError('A newer operating-hours proposal exists. Review the latest one.')
  if p['before_sha256']!=digest(settings(store)):raise ValueError('Operating hours changed. Review a new proposal first.')
  staffing.book(store)['settings']['operating_hours']=validate(p['config']);staffing.book(store)['settings']['hours_confirmed']=True;p['accepted_at']=now();staffing.book(store)['events'].append({'at':now(),'kind':'operating_hours_accepted','proposal_id':p['id']});store.save();return {'saved':True,'answer':'Saved the reviewed operating hours and closures. Existing schedules remain in history and show any conflicts; request a fresh week proposal to revise them.'}

def describe(config):
 lines=[]
 for i,name in enumerate(DAY_NAMES):
  r=config['weekdays'][str(i)];lines.append(name+': '+('Closed' if r['mode']=='closed' else 'Open 24 hours' if r['mode']=='24h' else r['open']+' to '+r['close']+(' next day' if r['end_next_day'] else ''))+((' · opening staff '+str(r['before_minutes'])+' min early · closing staff '+str(r['after_minutes'])+' min later') if r['mode']!='closed' else ''))
 for key,r in sorted(config['date_overrides'].items()):lines.append(key+': '+r['mode']+' '+r['open']+' to '+r['close']+(' next day' if r['end_next_day'] else ''))
 for c in config['closures']:lines.append(('Every '+str(c['month']).zfill(2)+'-'+str(c['day']).zfill(2) if c['kind']=='annual' else c['date'])+': full day closed · '+c['reason'])
 return '\n'.join(lines)

def converse(store,thread,message,today=None):
 text=message.strip();low=text.casefold();today=today or date.today();config=settings(store);dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
 pending=thread.get('operating_pending')
 if pending and re.search(r'\b(?:every day|daily|sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b',low):
  text=pending['message']+' '+text;low=text.casefold();thread['operating_pending']=None
 if not re.search(r'\b(?:closed|closure|opening|closing|open|operating hours|24[ -]hours?|openers|closers)\b',low):return None
 if re.search(r'\b(?:document|source|quote|handoff|decision|lunch)\b',low):return None
 if re.search(r'\b(?:show|what are|review)\b',low) and not re.search(r'\b(?:closed|close on)\b',low):return {'kind':'operating_hours','answer':describe(config)+'\nUse Settings to review customer hours and opening/closing staff buffers.'}
 if re.search(r'\bclosed\b',low):
  reason=text
  if 'christmas' in low:
   closure={'kind':'annual','month':12,'day':25,'reason':reason};resolved='every December 25 (including '+str(today.year)+'-12-25 and '+str(today.year+1)+'-12-25)'
  elif dates:closure={'kind':'date','date':daily.day_key(dates[0]),'reason':reason};resolved=closure['date']
  else:
   if re.search(r'\bweekends\b',low):
    for k in ('0','6'):config['weekdays'][k]['mode']='closed'
    p=propose(store,config,text);thread['operating_proposal_id']=p['id'];return {'kind':'operating_proposal','answer':'Review recurring full-day closures every Saturday and Sunday. No staff, buffers or overnight spillover are allowed on those dates. Existing schedules stay unchanged until reviewed.','operating_proposal_id':p['id']}
   day_match=re.search(r'\b(next |every |on )?(sunday|monday|tuesday|wednesday|thursday|friday|saturday)s?\b',low)
   if not day_match:return {'kind':'operating_clarification','answer':'Which exact date or recurring day is closed? Say YYYY-MM-DD, “every Sunday”, or an annual month/day. I will show the resolved closure for review before saving it.'}
   weekday=DAY_NAMES.index(day_match[2].title())
   if day_match[1]=='next ':
    delta=(weekday-(today.weekday()+1)%7)%7 or 7;key=(today+timedelta(days=delta)).isoformat();closure={'kind':'date','date':key,'reason':reason};resolved=key+' ('+day_match[2].title()+')'
   else:
    config['weekdays'][str(weekday)]['mode']='closed';closure=None;resolved='every '+day_match[2].title()
  if closure:config['closures'].append(closure)
  p=propose(store,config,text);thread['operating_proposal_id']=p['id'];return {'kind':'operating_proposal','answer':'Review full-day closure for '+resolved+'. Reason: '+reason+'. No employees will be scheduled on closed dates, including opening/closing staff or overnight spillover. Existing accepted schedules stay unchanged and will need review. Use Review operating hours, then Accept to save this exact closure.','operating_proposal_id':p['id']}
 # Explicit daily/weekday hours. Bare times require AM/PM clarification.
 rng=re.search(daily.RANGE,text,re.I) or re.search(r'open\s+(?:at\s+)?('+daily.TIME+r').*?clos(?:e|ing)\s+(?:at\s+)?('+daily.TIME+r')',text,re.I);duration24=bool(re.search(r'\b24[ -]hours?\b',low));before=re.search(r'(?:openers?|opening staff).*?(\d+)\s*(hours?|minutes?)\s*(?:early|before)',low);after=re.search(r'(?:closers?|closing staff).*?(\d+)\s*(hours?|minutes?)\s*(?:late|later|after)',low)
 if not rng and not duration24 and not before and not after:return {'kind':'operating_clarification','answer':'What are the customer opening and closing times? Include AM/PM (9am to 5pm) or 24-hour clock times, and say “next day” for an overnight closing. You can also specify opening staff 1–2 hours early and closing staff 1–2 hours later.'}
 targets=[str(DAY_NAMES.index(name.title())) for name in re.findall(r'\b(sunday|monday|tuesday|wednesday|thursday|friday|saturday)s?\b',low)]
 if re.search(r'\bweekdays\b',low):targets=['1','2','3','4','5']
 if re.search(r'\bweekends\b',low):targets=['0','6']
 if not targets and not dates and not re.search(r'\b(?:every day|daily|all week|seven days|7 days)\b',low):
  thread['operating_pending']={'message':text};return {'kind':'operating_clarification','answer':'Which weekdays does that apply to, or is it every day? I kept the hours you gave. Say “every day” or list the weekdays so I can show a precise proposal.'}
 weekday_range=re.search(r'\b(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\s*(?:through|to|[-–])\s*(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b',low)
 if weekday_range:
  first,last=[DAY_NAMES.index(x.title()) for x in weekday_range.groups()];targets=[str((first+i)%7) for i in range((last-first)%7+1)]
 targets=targets or [str(i) for i in range(7)]
 for target in dates or targets:
  row=deepcopy(config['date_overrides'].get(target,config['weekdays'][str((date.fromisoformat(target).weekday()+1)%7)])) if dates else deepcopy(config['weekdays'][target])
  if duration24:row['mode']='24h'
  elif rng:row.update(mode='hours',open=rng[1],close=rng[2],end_next_day=bool(re.search(r'\b(?:next day|overnight|following day)\b',low)))
  if before:row['before_minutes']=int(before[1])*(60 if before[2].startswith('hour') else 1)
  if after:row['after_minutes']=int(after[1])*(60 if after[2].startswith('hour') else 1)
  row=normalize_window(row)
  if dates:config['date_overrides'][target]=row
  else:config['weekdays'][target]=row
 p=propose(store,config,text);thread['operating_proposal_id']=p['id'];return {'kind':'operating_proposal','answer':'I prepared customer hours and staffing buffers for review. '+describe(config)+'\nUse Review operating hours, then Accept to save. Current schedules will remain unchanged until you review a fresh schedule proposal.','operating_proposal_id':p['id']}
