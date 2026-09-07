"""Transparent local staffing conversation. It never invents staff availability."""
from datetime import date,timedelta
import re
import staffing as staff
import shift_schedule as daily


def reply(text,kind='staffing',**extra):return {'answer':text,'kind':kind,**extra}
def draft(store,thread,name='',identity=None):
 e=staff.employee(store,identity) if identity else None
 thread['staffing_form']={'name':e['name'] if e else name,'id':e['id'] if e else None,'week_start':staff.book(store)['selected_week'],'start_date':e['start_date'] if e else date.today().isoformat()}
 thread['staffing_pending']=None
 return reply(('Let’s add '+name+'. ' if not e else 'I opened '+e['name']+'’s saved details. ')+ 'The seven dated rows are beside our conversation, starting Sunday '+staff.book(store)['selected_week']+'. Enter available hours, Off, or Not provided for each date. The start date shown is editable; roles and contact details are yours to supply. Save employee when the details are ready. No availability has been assumed.',kind='employee_form')
def named(store,text):
 matches=[e for e in staff.book(store)['employees'] if re.search(r'(?<!\w)'+re.escape(e['name'])+r'(?!\w)',text,re.I)]
 return matches[0] if len(matches)==1 else None

def converse(store,thread,message):
 import operating_hours
 operating=operating_hours.converse(store,thread,message)
 if operating:return operating
 text=message.strip();low=text.casefold().strip(' .!?');data=staff.book(store);pending=thread.get('staffing_pending');dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text);key=dates[0] if dates else daily.book(store)['selected_date'];person=named(store,text)
 if not dates:
  if re.search(r'\btoday\b',low):key=date.today().isoformat()
  elif re.search(r'\btomorrow\b',low):key=(date.today()+timedelta(days=1)).isoformat()
  elif re.search(r'\byesterday\b',low):key=(date.today()-timedelta(days=1)).isoformat()
  else:
   named_day=re.search(r'\b(next\s+)?(sunday|monday|tuesday|wednesday|thursday|friday|saturday)\b',low)
   if named_day:
    index=['sunday','monday','tuesday','wednesday','thursday','friday','saturday'].index(named_day[2])
    key=(date.today()+timedelta(days=((index-(date.today().weekday()+1)%7)%7 or 7))).isoformat() if named_day[1] else staff.days(data['selected_week'])[index]
 if low in ('cancel','never mind','nevermind') and (pending or thread.get('staffing_form')):
  thread['staffing_pending']=None;thread['staffing_form']=None;return reply('Closed the unfinished staff entry. Your saved employees and schedules are unchanged.')
 if pending:
  if pending['kind']=='hire_name':
   name=re.sub(r'^(?:(?:his|her|their) name is|(?:it is|it’s|it\'s)|(?:the name is))\s+','',text,flags=re.I).strip(' .')
   if re.search(r'\b(?:schedule|hours|help|what|where|employee|hired)\b',name,re.I) or len(name)>100 or not name:return reply('What is the new employee’s name? You can enter a first and last name, or say cancel.')
   return draft(store,thread,name)
  if pending['kind']=='end_date':
   if not dates:return reply('What is the first date '+pending['name']+' will no longer be available to work? Use YYYY-MM-DD. Earlier schedules and the employee record stay in history.')
   e=staff.end_employment(store,pending['employee_id'],dates[0],pending['reason']);thread['staffing_pending']=None;return reply(e['name']+' is recorded unavailable from '+e['end_date']+'. Earlier schedule revisions are preserved. Review any future shifts still showing this employee; I have not silently reassigned them.')
  if pending['kind']=='sick_date':
   if not dates:return reply('Which date is '+pending['name']+' unable to work? Use YYYY-MM-DD so I review the correct saved schedule.')
   person=staff.employee(store,pending['employee_id']);key=dates[0];low='reported sick';thread['staffing_pending']=None
  elif pending['kind']=='lunch_person':
   if not person:return reply('Which saved employee should I find lunch options for? Name one employee, or choose Lunch beside a dated shift.')
   low='lunch';thread['staffing_pending']=None
 if re.search(r'\b(?:hired|hire|new employee|add (?:an? )?(?:employee|staff member))\b',low):
  match=re.fullmatch(r'(?:i (?:just )?hired|hire|add (?:an? )?employee|new employee(?: named| called)?)\s+(?!a new employee|an employee|a staff member)([\w .’\'-]{1,100})',text,re.I)
  if match and match[1].casefold() not in ('a new employee','an employee','someone','a person'):return draft(store,thread,match[1].strip(' .'))
  thread['staffing_pending']={'kind':'hire_name'};return reply('What is the new employee’s name? After that, we’ll enter the actual dates and hours they are available in the seven-day form beside our conversation.')
 if re.search(r'\b(?:quit|quitting|terminated|terminate|left the (?:company|team)|no longer works)\b',low):
  if not person:return reply('Which saved employee is leaving? Name the employee so their history stays attached to the right person.')
  if not dates:
   thread['staffing_pending']={'kind':'end_date','employee_id':person['id'],'name':person['name'],'reason':text};return reply('What is the first date '+person['name']+' will no longer be available to work? Use YYYY-MM-DD. This preserves earlier schedules and the employee record.')
  e=staff.end_employment(store,person['id'],dates[0],text);return reply(e['name']+' is unavailable from '+e['end_date']+'. Earlier history is preserved; future schedules need review.')
 if re.search(r'\b(?:sick|called out|replacement|cover .*shift)\b',low):
  if not person:return reply('Which saved employee is unable to work? Name them and the date, or select a dated schedule first.')
  if not key:
   thread['staffing_pending']={'kind':'sick_date','employee_id':person['id'],'name':person['name']};return reply('Which date is '+person['name']+' unable to work? Use YYYY-MM-DD.')
  if re.search(daily.RANGE,text,re.I):return reply('Do you mean this employee’s whole saved shift, or only part of it? I can review the full saved shift and eligible 2–3 hour extensions. I have not treated the time range in your message as a whole-shift absence.')
  proposal=staff.suggest_sick(store,person['id'],key);thread['staffing_proposal_id']=proposal['id'];choices=proposal['payload']['choices']
  return reply('I reviewed '+person['name']+'’s saved shift on '+key+'. '+str(len(choices))+' eligible replacement or partial-extension options appear in the call list, ordered by least projected overtime. Only recorded availability and roles qualify. No employee has been contacted, and no schedule has changed. Select an option only after arranging it; a partial extension can leave a gap.',proposal_id=proposal['id'])
 if re.search(r'\b(?:lunch|break recommendation|break coverage)\b',low):
  if not key:return reply('Choose the saved date first so I can check real lunch coverage.')
  if not person:thread['staffing_pending']={'kind':'lunch_person'};return reply('Whose lunch should I plan on '+key+'? Name a saved employee.')
  plan=daily.latest(store,key);shifts=[s for s in (plan or {}).get('shifts',[]) if s.get('employee_id')==person['id']]
  if len(shifts)!=1:return reply('Select the exact shift beside '+person['name']+' in the dated schedule; there is not exactly one saved shift on '+key+'.')
  duration=re.search(r'\b(\d+)\s*(?:minute|min)\b',low);minutes=int(duration[1]) if duration else 30;time_text=re.sub(r'\bnoon\b','12pm',text,flags=re.I);window=re.search(daily.RANGE,time_text,re.I);at=re.search(r'\bat\s+('+daily.TIME+r')',time_text,re.I)
  if re.search(r'\bat\s+\d+\b',time_text,re.I) and not at:return reply('Please include AM/PM or a full 24-hour time for that lunch request, such as 12:30pm. I have not guessed which part of the day you mean.')
  start,end=(window[1],window[2]) if window else (at[1],daily.hm(daily.clock(at[1])+minutes)) if at else ('11:00','14:00')
  p=staff.suggest_lunch(store,shifts[0]['id'],key,minutes,start,end);thread['staffing_proposal_id']=p['id'];return reply('I checked '+person['name']+'’s lunch against the saved '+key+' coverage. Review the options beside our conversation; each shows any additional gap. Select and accept one to add it to the schedule.',proposal_id=p['id'])
 if re.search(r'\b(?:time off|vacation|unavailable)\b',low) and person:
  if not dates:return reply('Which dates are unavailable for '+person['name']+'? Include YYYY-MM-DD, or use the employee’s Time off form. I will preserve the reason in the employee record.')
  staff.time_off(store,person['id'],dates[0],dates[-1],text);return reply('Recorded '+person['name']+'’s time off from '+dates[0]+' through '+dates[-1]+'. Saved schedules are preserved and will show conflicts until reviewed.')
 if re.search(r'\b(?:availability|preferences|employee details|edit .*employee)\b',low):
  if person:return draft(store,thread,identity=person['id'])
  return reply('Choose an employee in the directory, or name them here. Their seven actual dates, availability, preferences and optional contact details will appear beside our conversation.')
 if re.search(r'\b(?:suggest|propose|build|make|plan)\b',low) and re.search(r'\b(?:week|schedule|roster)\b',low):
  if not data['employees']:return reply('Let’s add your team first. Say “I hired a new employee” or choose Add employee. I can propose the week once you record their dated availability and required roles.')
  week=dates[0] if dates else staff.next_sunday() if 'next week' in low else data['selected_week'];p=staff.suggest_week(store,week);thread['staffing_proposal_id']=p['id'];gaps=sum(staff.role_coverage(d)['role_missing_person_minutes'] for d in p['payload']['days']);return reply('I prepared a Sunday-to-Saturday proposal for '+week+'. The board shows proposed shifts and '+str(round(gaps/60,2))+' role-hours of unfilled coverage. Review the availability gaps, preferences and time-off requests. Lunch is still to be planned. Accept the reviewed week to save it, or edit the proposal first. Existing schedules are unchanged.',proposal_id=p['id'])
 if re.search(r'\b(?:show|open|revisit|select)\b',low) and re.search(r'\b(?:week|schedule|history|hours|coverage)\b',low):
  if dates:staff.select_day(store,dates[0])
  plan=daily.latest(store);return reply(daily.summary(plan) if plan else 'The current week is '+data['selected_week']+'. Add employees and their dated availability, then suggest a week. Nothing has been scheduled yet.')
 if low in ('yes','accept','accept the week','save the schedule') and thread.get('staffing_proposal_id'):
  return reply('Review the dated proposal beside our conversation, then use its Accept reviewed week or Accept selected option button. That confirms the exact displayed version and keeps later edits from being silently overwritten.')
 return None
