"""Transparent local staffing conversation. It never invents staff availability."""
from datetime import date,timedelta
import re
import staffing as staff
import staffing_constraints as rules
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

def planning_request(message):
 """Route requests only; the existing strict agent contract validates every clause."""
 text=message.strip().casefold().replace('’',"'")
 text=rules.strip_lead_ins(text)
 weekly=bool(re.search(r'\b(?:suggest|propose|build|make|plan)\b',text) and re.search(r'\b(?:week|schedule|roster)\b',text))
 simple=bool(re.fullmatch(r'(?:suggest|propose|build|make|plan)\s+(?:(?:the|this|selected|next)\s+)?(?:week|weekly schedule|schedule|roster)[.!? ]*',text))
 return bool(rules.is_reset(message) or re.match(r'^(?:remove|drop|clear|forget|undo)\b.+\b(?:cap|limit|restriction|exclusion)\b',text) or (weekly and not simple) or re.match(r"^(?:cap|limit|exclude|avoid scheduling|do not schedule|don't schedule|never schedule|no cap|do not cap|don't cap)\b",text) or re.match(r'^(?:keep|leave)\b.+\boff\b',text) or (re.search(r'\b(?:suggest|propose|build|make|plan)\b',text) and re.search(r'\b(?:week|schedule|roster)\b',text) and re.search(r"\b(?:cap|limit|off|exclude|at most|no more than|don't|do not)\b",text)))


def import_request(message):
 """Operational document requests, including questions; source questions stay reads."""
 text=re.sub(r'\s+',' ',message.strip().casefold().replace('’',"'"))
 return bool(re.match(r'^(?:(?:please\s+)?(?:import|scan|upload)\b|(?:can|could|would) you (?:please )?(?:help me )?(?:import|scan|upload)\b|how (?:do|can) (?:i|we) (?:import|scan|upload)\b|(?:i (?:want|need|would like) to )?(?:import|scan|upload)\b)',text) and re.search(r'\b(?:employees?|staff|roster|list|document)\b',text))

def employment_inquiry(text):
 """Questions, hypothetical and quoted statements never record an end date."""
 text=re.sub(r'\s+',' ',text.strip().casefold().replace('’',"'"))
 return bool('?' in text or re.search(r'\b(?:if|unless|whether|suppose|supposing|hypothetical|hypothetically|assuming)\b',text)
             or re.match(r'^(?:please\s+)?(?:did|does|do|is|are|was|were|has|have|had|when|why|what|who|how|can|could|would|should|will|tell|show|check|confirm|explain|find)\b',text)
             or re.match(r"^i (?:wonder|(?:want|need) to know|am asking|'m asking)\b",text)
             or re.search(r'["\x60“”]|(?:^|\s)\x27[^\x27]+\x27',text))


def employment_change(text,person):
 """A finite affirmative report or direct instruction about this exact person."""
 if person is None:return None
 name=re.escape(person['name'])
 ending=r'(?:quit|has quit|is quitting|terminated|was terminated|left the (?:company|team)|no longer works(?: here| for us| for this team)?)'
 statement=r'(?:(?:please )?record (?:that )?)?'+name+r'\s+'+ending
 instruction=r'(?:please )?terminate\s+'+name
 timing=r'(?:\s+(?:on|from|effective)\s+(?P<end_date>\d{4}-\d{2}-\d{2}))?'
 reason=r'(?:\s+because\s+[^?]+)?'
 return re.fullmatch(r'(?:'+statement+'|'+instruction+')'+timing+reason+r'[.! ]*',text.strip(),re.I)


def departure_review_reply(store,thread,person,message,proposed=''):
 """A bound UI draft, with no employee mutation and no bare-date auto-save."""
 thread['staffing_pending']=None
 return reply('I opened '+person['name']+'’s employment-ending review. Enter or review the first date they will no longer be available, then choose Record end date. Nothing changes until you save; earlier work and schedule history stay intact.',
  kind='employee_form',navigation={'screen':'employees','view':'employment_end','employee_id':person['id'],'team_id':store.production_id,'employee_revision':person.get('revision',1),'proposed_date':proposed,'reason':message})


def reported_departure_review(store,thread,message):
 """Affirmative departures open the existing date review; never apply it in chat."""
 text=re.sub(r'\s+',' ',message.strip().replace('’',"'"))
 if not re.search(r'\b(?:fired|fire|firing|quit|quitting|terminate|terminated|left the (?:company|team)|no longer works)\b',text,re.I):return None
 person=named(store,text);pending=thread.get('staffing_pending')
 # A subsequent bare date must not apply an older employee's pending change.
 if pending and pending.get('kind')=='end_date':thread['staffing_pending']=None
 negated=re.search(r"\b(?:not|never|didn't|don't|doesn't|wasn't|weren't|isn't|hasn't|haven't|won't)\b",text,re.I)
 if negated:
  current=(' '+person['name']+' currently has a saved end date of '+person['end_date']+'. Review their employee details if that record needs correcting.') if person and person.get('end_date') else ''
  return reply('I have not changed any employee record. A denied departure does not open an employment-ending review. Any unfinished departure-date question is closed.'+current,kind='staffing_clarification')
 if employment_inquiry(text):
  if re.search(r'\b(?:fire|firing)\b',text,re.I):return reply('I can help review saved records, but I will not decide whether to fire someone. If you have already made that decision, report the departure with their full saved name. No employee record has changed.',kind='staffing_clarification')
  return employment_record_reply(store,thread,text,person)
 if person is None:
  return reply('Which one saved employee has already left? Use their full saved name. I have not opened a departure review or changed any employee record.',kind='staffing_clarification')
 name=re.escape(person['name'])
 actor=r'(?:i|we)(?: have|\x27ve)?(?: just| already)? (?:fired|terminated)\s+'
 passive=r'\s+(?:was|has been)(?: just| already)? fired'
 timing=r'(?:\s+(?:(?:on|from|effective)\s+)?(?P<date>\d{4}-\d{2}-\d{2}|today|yesterday))?'
 match=re.fullmatch(r'(?:'+actor+name+'|'+name+passive+')'+timing+r'(?:\s+because\s+[^?]+)?[.! ]*',text,re.I)
 legacy=employment_change(text,person)
 if match is None and legacy is None:
  return reply('I have not changed any employee record. To report an already-decided departure, say “'+person['name']+' quit” or “I fired '+person['name']+'”, then review the first unavailable date. No decision or date has been inferred.',kind='staffing_clarification')
 if pending and pending.get('kind')!='end_date':
  return reply('Finish or cancel the current staff entry before opening a departure review. Your saved employees are unchanged.',kind='staffing_clarification')
 proposed=(match.group('date') if match else legacy.group('end_date')) or ''
 if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',proposed):proposed=''
 return departure_review_reply(store,thread,person,message,proposed)


def employment_date_answer(text):
 """A pending change accepts one whole date answer, not any dated message."""
 match=re.fullmatch(r'(?:yes,?\s+)?(?:(?:on|from|effective)\s+|(?:the\s+)?(?:end date|first unavailable date)\s+(?:is\s+|:\s*)|record (?:the )?end date as\s+)?(\d{4}-\d{2}-\d{2})[.! ]*',text.strip(),re.I)
 return match[1] if match else None


def employment_read_context(thread,result):
 """A different employee's detail view closes an unfinished departure question."""
 pending=thread.get('staffing_pending');identity=(result.get('navigation') or {}).get('employee_id')
 if pending and pending.get('kind')=='end_date' and identity and identity!=pending['employee_id']:
  thread['staffing_pending']=None
  result['answer']+=' I closed the unfinished departure-date question for '+pending['name']+'. Their employee record is unchanged.'
 return result


def employment_record_reply(store,thread,text,person):
 matches=[e for e in staff.book(store)['employees'] if re.search(r'(?<!\w)'+re.escape(e['name'])+r'(?!\w)',text,re.I)]
 if len(matches)>1:return reply('Name one saved employee so I can read the right employment record. I have not changed any end date.',kind='staffing_clarification')
 if person is None:return reply('Which saved employee’s employment record should I check? Use their full saved name. I have not changed any end date.',kind='staffing_clarification')
 end=person.get('end_date')
 answer=person['name']+(' has a saved employment end date of '+end+'.' if end else ' has no saved employment end date.')
 record=next((h for h in reversed(person.get('history',[])) if h.get('operation')=='employment_ended' and h.get('effective_date')==end),None) if end else None
 if record and record.get('reason'):answer+=' Reported note: '+str(record['reason'])+'. This is a reported note, not verified evidence of why they left.'
 answer+=' I have not changed the employee record or schedule.'
 from employee_directory import employee_detail_reply
 result=employee_detail_reply(store,('tell me about '+person['name']).casefold().replace('’',"'"))
 if result:result['answer']=answer;return employment_read_context(thread,result)
 return reply(answer,kind='staffing_clarification')


def converse(store,thread,message):
 import employee_directory, employee_pay
 import work_history
 history=work_history.respond(store,thread,message)
 if history:return history
 import employer_insights
 insight=employer_insights.respond(store,thread,message)
 if insight:return insight
 departure=reported_departure_review(store,thread,message)
 if departure:return departure
 directory=employee_directory.respond(store,message)
 if directory:return employment_read_context(thread,directory)
 pay=employee_pay.converse(store,thread,message)
 if pay:return pay
 if import_request(message):
  return reply('I opened Import employees. Choose a CSV, labeled text file or PDF with selectable text, then review the extracted details before saving. Photos and image-only scans are not read here; paste their text into the import form. Nothing has been added, and missing details stay blank.',kind='employee_import',navigation={'screen':'employees','view':'import','employee_id':None})
 import operating_hours
 operating=operating_hours.converse(store,thread,message)
 if operating:return operating
 if planning_request(message):
  week=staff.book(store)['selected_week']
  return reply('Your weekly restriction request is ready to check. No schedule has been changed.',kind='staffing_ai_request',staffing_request={'production_id':store.production_id,'week_start':week,'request':message})
 text=message.strip();low=text.casefold().replace('’',"'").strip(' .!?');data=staff.book(store);pending=thread.get('staffing_pending');dates=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text);key=dates[0] if dates else daily.book(store)['selected_date'];person=named(store,text)
 # A denial or correction is not authorization to record an employment end.
 employment_event=re.search(r'\b(?:quit|quitting|terminated|terminate|left the (?:company|team)|no longer works)\b',low)
 negated=re.search(r"\b(?:not|never|didn't|doesn't|don't|isn't|wasn't|hasn't|haven't|won't)\b",low.replace('’',"'"))
 time_off_event=bool(re.search(r'\b(?:time off|vacation|unavailable)\b',low))
 if time_off_event and (employment_inquiry(text) or negated):
  if negated and not employment_inquiry(text):return reply('I have not added or removed any time off. To correct an existing time-off entry, open that employee’s dated record and review the exact entry.',kind='staffing_clarification')
  if not person:return reply('Which saved employee and date should I check for time off? Use their full name and one YYYY-MM-DD date. No time off has been changed.',kind='staffing_clarification')
  if len(dates)!=1:return reply('Which one date should I check for '+person['name']+'? Use YYYY-MM-DD. I have not applied a range or changed time off.',kind='staffing_clarification')
  result=employee_directory.availability_reply(store,('is '+person['name']+' available on '+dates[0]).casefold().replace('’',"'"))
  result['answer']+=' This reads the saved availability and time-off entries; it does not infer a vacation, absence or employment change.'
  return employment_read_context(thread,result)
 employment_context=employment_event or (pending and pending.get('kind')=='end_date')
 if employment_context and employment_inquiry(text):return employment_record_reply(store,thread,text,person)
 denial=negated or re.search(r'^(?:actually[, ]+)?no\b',low) or (pending and pending.get('kind')=='end_date' and re.search(r'\b(?:staying|still works|still working)\b',low))
 if employment_context and denial:
  if pending and pending.get('kind')=='end_date':thread['staffing_pending']=None
  current=(' '+person['name']+' currently has a saved end date of '+person['end_date']+'. Review their employee details if that record needs correcting.') if person and person.get('end_date') else ''
  return reply('Your message denies an employment change. I have not changed any employee end date or schedule, and any unfinished end-date question is closed.'+current,kind='staffing_clarification')
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
   if employment_inquiry(text) or re.match(r'^(?:tell|show|write|give|explain|compare|list|sing)\b',name,re.I) or re.search(r'\b(?:schedule|hours|help|what|where|employee|hired)\b',name,re.I) or len(name)>100 or not name:return reply('What is the new employee’s name? You can enter a first and last name, or say cancel.')
   return draft(store,thread,name)
  if pending['kind']=='end_date':
   end_date=employment_date_answer(text)
   if end_date is None:return reply('To record '+pending['name']+'’s previously reported departure, reply with only the first unavailable date as YYYY-MM-DD, or say cancel. I have not changed the employee record.',kind='staffing_clarification')
   person=staff.employee(store,pending['employee_id'])
   return departure_review_reply(store,thread,person,pending['reason'],end_date)
  if pending['kind']=='sick_date':
   if not dates:return reply('Which date is '+pending['name']+' unable to work? Use YYYY-MM-DD so I review the correct saved schedule.')
   person=staff.employee(store,pending['employee_id']);key=dates[0];low='reported sick';thread['staffing_pending']=None
  elif pending['kind']=='lunch_person':
   if not person:return reply('Which saved employee should I find lunch options for? Name one employee, or choose Lunch beside a dated shift.')
   low='lunch';thread['staffing_pending']=None
 if re.search(r'\b(?:hired|hire|new employee|add (?:an? )?(?:employee|staff member))\b',low):
  if employment_inquiry(text) and not re.match(r'^(?:can|could|would) you (?:please )?(?:add|hire)\b',low):return reply('Add employee opens a draft where you enter the person’s name, start date and actual dated availability. Review those details and use Save employee to add them. I have not opened a hiring entry from this question.',kind='staffing_clarification')
  match=re.fullmatch(r'(?:i (?:just )?hired|hire|add (?:an? )?employee|new employee(?: named| called)?)\s+(?!a new employee|an employee|a staff member)([\w .’\'-]{1,100})',text,re.I)
  if match and match[1].casefold() not in ('a new employee','an employee','someone','a person'):return draft(store,thread,match[1].strip(' .'))
  thread['staffing_pending']={'kind':'hire_name'};return reply('What is the new employee’s name? After that, we’ll enter the actual dates and hours they are available in the seven-day form beside our conversation.')
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
  name=re.escape(person['name'])
  affirmative=re.fullmatch(r'(?:(?:please )?(?:record|save) (?:that )?)?'+name+r' (?:is|will be) (?:unavailable|on vacation|taking time off)(?: (?:on|from))? (?P<start>\d{4}-\d{2}-\d{2})(?: (?:through|to|until) (?P<end>\d{4}-\d{2}-\d{2}))?(?: because [^?]+)?[.! ]*',text,re.I)
  instruction=re.fullmatch(r'(?:please )?(?:record|save|add) (?:time off|vacation) for '+name+r'(?: (?:on|from))? (?P<start>\d{4}-\d{2}-\d{2})(?: (?:through|to|until) (?P<end>\d{4}-\d{2}-\d{2}))?(?: because [^?]+)?[.! ]*',text,re.I)
  if not (affirmative or instruction):return reply('I have not changed time off. State that '+person['name']+' is unavailable on an exact date, or use the Time off form to review the dates and reason.',kind='staffing_clarification')
  if not dates:return reply('Which dates are unavailable for '+person['name']+'? Include YYYY-MM-DD, or use the employee’s Time off form. I will preserve the reason in the employee record.')
  change=affirmative or instruction;start=change.group('start');end=change.group('end') or start
  staff.time_off(store,person['id'],start,end,text);return reply('Recorded '+person['name']+'’s time off from '+start+' through '+end+'. Saved schedules are preserved and will show conflicts until reviewed.')
 if re.search(r'\b(?:availability|preferences|employee details|edit .*employee)\b',low):
  if person:return draft(store,thread,identity=person['id'])
  return reply('Choose an employee in the directory, or name them here. Their seven actual dates, availability, preferences and optional contact details will appear beside our conversation.')
 if re.search(r'\b(?:suggest|propose|build|make|plan)\b',low) and re.search(r'\b(?:week|schedule|roster)\b',low):
  if not data['employees']:return reply('Let’s add your team first. Say “I hired a new employee” or choose Add employee. I can propose the week once you record their dated availability and required roles.')
  week=dates[0] if dates else staff.next_sunday() if 'next week' in low else data['selected_week'];p=rules.suggest_preserving(store,week);thread['staffing_proposal_id']=p['id'];gaps=sum(staff.role_coverage(d)['role_missing_person_minutes'] for d in p['payload']['days']);return reply('Using the saved-availability rules and retaining any current unaccepted restrictions, I prepared a Sunday-to-Saturday proposal for '+week+'. The board shows proposed shifts and '+str(round(gaps/60,2))+' role-hours of unfilled coverage. Review the availability gaps, preferences and time-off requests. Lunch is still to be planned. Accept the reviewed week to save it, or edit the proposal first. Existing schedules are unchanged.',proposal_id=p['id'],staffing_proposal=p,kind='staffing_rules_proposal')
 if re.search(r'\b(?:show|open|revisit|select)\b',low) and re.search(r'\b(?:week|schedule|history|hours|coverage)\b',low):
  if dates:staff.select_day(store,dates[0])
  plan=daily.latest(store);return reply(daily.summary(plan) if plan else 'The current week is '+data['selected_week']+'. Add employees and their dated availability, then suggest a week. Nothing has been scheduled yet.')
 if low in ('yes','accept','accept the week','save the schedule') and thread.get('staffing_proposal_id'):
  return reply('Review the dated proposal beside our conversation, then use its Accept reviewed week or Accept selected option button. That confirms the exact displayed version and keeps later edits from being silently overwritten.')
 return None
