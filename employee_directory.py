"""Read-only answers and navigation from this team's saved employee records."""
from copy import deepcopy
import re
import staffing as staff
import shift_schedule as daily


def summary(store):
    day = staff.date.today().isoformat()
    team = next(p for p in store.data['productions'] if p['id'] == store.production_id)
    from employee_pay import rate_on
    rows = []
    for e in staff.book(store)['employees']:
        status = 'future' if e['start_date'] > day else 'former' if e.get('end_date') and e['end_date'] <= day else 'active'
        rows.append({**{k: deepcopy(e.get(k)) for k in ('id','name','start_date','end_date','phone','email','roles')},
                     'employment_status': status, 'revision': e.get('revision', 1),
                     'pay_current': rate_on(e, day), 'pay_history': deepcopy(e.get('pay_history', []))})
    rows.sort(key=lambda e: (e['name'].casefold(), e['id']))
    return {'team_id': store.production_id, 'team_name': team['title'], 'as_of_date': day,
            'total_records': len(rows), **{k+'_count':sum(e['employment_status']==k for e in rows) for k in ('active','former','future')},
            'employees': rows}


def hours(store, week=None):
    week = week or staff.book(store)['selected_week']; dates = staff.days(week)
    totals = staff.hours_by_employee(store, week)
    rows = [{'employee_id':e['id'], 'name':e['name'], 'minutes':totals.get(e['id'], 0),
             'hours':round(totals.get(e['id'], 0)/60, 4)} for e in staff.book(store)['employees']]
    rows.sort(key=lambda e: (-e['minutes'], e['name'].casefold(), e['employee_id']))
    previous = None; rank = 0
    for index, row in enumerate(rows):
        if row['minutes'] != previous: rank = index+1
        row['rank'] = rank; previous = row['minutes']
    return {'metric':'planned_net_hours', 'label':'Planned hours', 'week_start':week, 'week_end':dates[-1],
            'has_saved_schedule':any(daily.latest(store, d) is not None for d in dates),
            'attendance_available':False, 'breaks_subtracted':True, 'rows':rows}


def requested_hours_week(text, selected_week):
    """Resolve an explicit weekly scope without changing the open schedule."""
    matches=list(re.finditer(r'\bweek\s+(?:of|starting|beginning)\s+(\d{4}-\d{2}-\d{2})\b|\b(this|last|next|selected)\s+week\b', text))
    remaining=text
    for match in reversed(matches):
        remaining=remaining[:match.start()]+remaining[match.end():]
    # Never silently answer a day, month, range, or unparsed week as the open week.
    temporal=r'\b(?:today|yesterday|tomorrow|weeks?|months?|years?|days?|tonight|ever|all time|since|between|sunday|monday|tuesday|wednesday|thursday|friday|saturday|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|\b\d{4}\b|\b\d{1,2}/\d{1,2}\b'
    error='Which week should I compare? Say "this week", "last week", "next week", or "the week of YYYY-MM-DD". I compare saved planned hours from Sunday through Saturday; I have not substituted the open week for a different period.'
    if len(matches)>1 or re.search(temporal,remaining):
        return None,error
    if not matches:
        return selected_week,None
    match=matches[0]
    try:
        if match[1]:
            return staff.current_sunday(staff.date.fromisoformat(match[1])),None
        if match[2]=='selected':
            return selected_week,None
        sunday=staff.date.fromisoformat(staff.current_sunday())
        return (sunday+staff.timedelta(days={'this':0,'last':-7,'next':7}[match[2]])).isoformat(),None
    except (ValueError,OverflowError):
        return None,error



def availability_reply(store, text):
    if not re.search(r'\b(?:available|availability)\b',text) or not re.match(r'^(?:who|which|is|are|show|check|what|tell me|can you (?:show|check|tell me))\b',text):
        return None
    data=summary(store)
    view={'team_id':store.production_id,'selected_week':staff.book(store)['selected_week'],
          'date':None,'rows':[],'employee_revisions':{e['id']:e['revision'] for e in data['employees']}}
    result={'kind':'employee_directory','navigation':{'screen':'employees','view':'availability','employee_id':None},
            'employee_summary':data,'availability_read':view}
    def held(message):
        view['clarification']=message;result['answer']=message
        return result
    dates=list(re.finditer(r'\b\d{4}-\d{2}-\d{2}\b',text))
    relative=list(re.finditer(r'\b(?:today|tomorrow|yesterday)\b',text))
    if len(dates)+len(relative)!=1:
        return held('Which date should I check? Say today, tomorrow, yesterday or one YYYY-MM-DD date. I can show the saved availability for that date; I have not assumed a time window or used another week.')
    try:
        day=daily.day_key(dates[0][0]) if dates else (staff.date.today()+staff.timedelta(days={'today':0,'tomorrow':1,'yesterday':-1}[relative[0][0]])).isoformat()
    except (ValueError,OverflowError):
        return held('That date is not valid. Use one YYYY-MM-DD date to see the recorded availability.')
    view['date']=day
    if not data['employees']:
        result['answer']='No employees are saved in '+data['team_name']+'. Add an employee or review an import, then enter their availability for '+day+'.'
        return result
    marker=re.sub(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:today|tomorrow|yesterday)\b','DATE',text)
    marker=re.sub(r'^(?:can you |could you |please )','',marker).strip(' .?!')
    all_staff=bool(re.fullmatch(r"(?:who (?:is|are|will be) available|which (?:employees|staff|team members) (?:are|will be) available|(?:show|check)(?: me)? (?:(?:the|employee|staff|team) )?availability)(?: (?:on|for))? DATE",marker))
    person=re.fullmatch(r"(?:is (.+?) available|(?:show|check)(?: me)? (.+?)(?:'s|') availability|what is (.+?)(?:'s|') availability)(?: (?:on|for))? DATE",marker)
    named=set()
    if person:
        requested=next(x for x in person.groups() if x is not None)
        named={e['id'] for e in data['employees'] if e['name'].casefold().replace('’',"'")==requested}
        if len(named)!=1:return held('I could not match one saved employee named '+requested+'. Use their full saved name, or ask who is available on '+day+'.')
    elif not all_staff:
        return held('I can show the saved availability for one date. Extra person, role or time-window conditions have not been applied. Ask “Who is available on '+day+'?” or “Is [full employee name] available on '+day+'?”.')
    selected=[e for e in staff.book(store)['employees'] if not named or e['id'] in named]
    for e in sorted(selected,key=lambda e:e['name'].casefold()):
        recorded=e.get('availability',{}).get(day,{})
        windows=staff.available(e,day)
        if not staff.active(e,day):label='Outside recorded employment dates'
        elif day in e.get('time_off',{}):label='Time off recorded'
        elif recorded.get('status')=='off':label='Off'
        elif windows:label='Available'
        else:label='Not provided'
        note=e.get('time_off',{}).get(day,'') if label=='Time off recorded' else ('Only these saved windows are known; no availability outside them is assumed.' if windows else 'No availability has been assumed.' if label=='Not provided' else '')
        view['rows'].append({'employee_id':e['id'],'name':e['name'],'revision':e.get('revision',1),
              'status':label,'recorded_status':recorded.get('status','unknown'),'windows':deepcopy(windows),'note':note})
    lines=[row['name']+': '+row['status']+(' '+', '.join(daily.hm(w['start'])+'–'+daily.hm(w['end']) for w in row['windows']) if row['windows'] else '') for row in view['rows']]
    result['answer']='Saved availability for '+day+':\n'+'\n'.join(lines[:8])+('\nThe Availability view shows the remaining employees.' if len(lines)>8 else '')+'\nThese are recorded availability windows, not assigned shifts or confirmed attendance. Missing entries remain Not provided. No schedule was changed.'
    return result

def employee_detail_reply(store, text):
    """One exact saved employee, current record only; no facts from documents."""
    # Specialty requests keep their existing dated read or reviewed write route.
    if re.search(r"\b(?:pay|paid|salary|wages?|rates?|raises?|availability|available|hours?|shifts?|schedule|history|import|scan|upload|hire|hired|add|terminate|quit|change|update|set|edit|replace|remove|delete|save|correct)\b", text):
        return None
    prefix = r"(?:(?:can|could|would) you (?:please )?|please )?"
    match = re.fullmatch(prefix + r"(?:tell me about|who is|show(?: me)? (?:the )?(?:employee )?(?:details|profile|record) (?:for|of)|open (?:the )?(?:employee )?(?:details|profile|record) (?:for|of)) (.+)", text)
    possessive = re.fullmatch(prefix + r"show(?: me)? (.+?)(?:'s|') (?:employee )?(?:details|profile|record)", text)
    if not match and not possessive:
        return None
    requested = (match or possessive)[1].strip()
    if requested in {'yourself','you','sarah','the team','my team','our team','employees','staff','contacts','contact details'}:
        return None
    data = summary(store)
    # Navigation metadata contains no other employee's fields.
    result = {'kind':'employee_directory', 'employee_summary':{k:v for k,v in data.items() if k!='employees'},
              'navigation':{'screen':'employees','view':'directory','employee_id':None}}
    def normalize(name):
        return re.sub(r'\s+', ' ', str(name).casefold().replace('’', "'")).strip(' .?!')
    def held(message):
        result['answer']=message;result['employee_detail_error']=message
        return result
    named = [e for e in data['employees'] if normalize(e['name']) == requested]
    if not named and requested.endswith(', please'):
        requested=requested[:-8].strip()
        named=[e for e in data['employees'] if normalize(e['name'])==requested]
    if not named:
        if re.search(r"\b(?:on|as of|today|tomorrow|yesterday|last|next|week|month|year|since|before|after|between)\b|\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}\b", requested):
            return held('I can open one employee’s current saved details. A different date or period has not been applied. Ask for their dated availability or hourly pay separately, or say “Tell me about [full saved name]”.')
        partial=[e['name'] for e in data['employees'] if normalize(e['name']).startswith(requested+' ')]
        if partial:
            return held('Use one full saved employee name: '+', '.join(partial[:8])+'. I have not selected a person from a partial name.')
        return held('I could not find one employee named '+requested+' in '+data['team_name']+'. Use their full saved name or choose their record in Employees. No employee details have been inferred from documents.')
    if len(named)!=1:
        return held('More than one saved employee matches '+requested+'. Choose the exact record in Employees; I have not selected one automatically.')
    e=named[0]
    detail={k:deepcopy(e.get(k)) for k in ('id','name','start_date','end_date','phone','email','roles','employment_status')}
    detail.update(team_id=data['team_id'],expected_revision=e['revision'],as_of_date=data['as_of_date'])
    result['employee_detail']=detail
    result['navigation'].update(view='detail',employee_id=e['id'])
    status={'active':'Active','former':'Former','future':'Not started'}[e['employment_status']]
    lines=[e['name']+' — '+status+' as of '+data['as_of_date']+'.',
           'Recorded roles: '+(', '.join(e['roles'] or []) or 'Not provided')+'.',
           'Start date: '+e['start_date']+'.',
           'Unavailable from: '+(e['end_date'] or 'No end date recorded')+'.',
           'Phone: '+(e['phone'] or 'Not provided')+'.',
           'Email: '+(e['email'] or 'Not provided')+'.',
           'These are the current saved employee details. Ask for a date to check availability or hourly pay; no attendance or payroll has been inferred.']
    result['answer']='\n'.join(lines)
    return result


def respond(store, message):
    text = re.sub(r'\s+', ' ', message.strip().casefold().replace('’', "'"))
    text = text.strip(' .?!')
    if re.search(r'\b(?:sources?|documents?|evidence|handbooks?|polic(?:y|ies)|citations?)\b',text): return None
    from employee_comparison import respond as compare_employees
    comparison = compare_employees(store, message)
    if comparison is not None: return comparison
    detail=employee_detail_reply(store,text)
    if detail:return detail
    if re.search(r'\b(?:import|scan|upload|hire|hired|add|terminate|quit|raise|change|update|set|edit|replace|remove|delete|save|record|correct)\b',text): return None
    availability=availability_reply(store,text)
    if availability:return availability
    employees = re.search(r'\b(?:employees?|staff|team members?|workers?|people on (?:my|the) team)\b', text)
    contact = re.search(r'\b(?:contacts?|contact information|phone(?: numbers?)?|email(?: addresses?)?)\b', text)
    count = bool(employees and re.search(r'\b(?:how many|number of|count|total)\b', text))
    roster = bool(employees and re.search(r'\b(?:open|show|list|all|who|where|directory|names)\b', text))
    ranking = bool(re.search(r'\b(?:who|you|which (?:employee|person|staff member))\s+(?:(?:has|have|had|is)\s+)?(?:worked|works?|working|scheduled)\s+(?:the\s+)?most\b|\b(?:most|compare|rank|show|graph|chart)\b.*\b(?:employee |staff |planned |work(?:ed)? )?hours\b|\b(?:hours|workload)\s+(?:graph|chart|ranking)\b', text))
    # A short noun request is a read, but a contact fact or mutation is not.
    bare = re.fullmatch(r'(?:(?:my|our|the)\s+)?(?:employees?|staff|team members?|workers?|contacts?|contact (?:information|details)|phone(?: numbers?)?|email(?: addresses?)?)', text)
    short_contact = re.fullmatch(r"(.+?)(?:'s|')?\s+(?:phone(?: number)?|email(?: address)?|contact(?: information| details)?|contacts?)", text) if contact else None
    data = None; named_short = []
    if short_contact:
        data = summary(store)
        name = short_contact[1].strip()
        named_short = [e for e in data['employees'] if e['name'].casefold().replace('’', "'") == name]
    if not (bare or named_short or count or roster or ranking or (contact and (employees or re.search(r'\b(?:open|where|show|list|find|what)\b',text)))):
        return None
    # Questions are read-only, even while an unrelated hire/end-date form waits.
    data = data if data is not None else summary(store); n = data['total_records']; view = 'hours' if ranking else 'contacts' if contact else 'directory'
    nav = {'screen':'employees', 'view':view, 'employee_id':None}
    result = {'kind':'employee_directory', 'navigation':nav, 'employee_summary':data}
    if ranking:
        week, error = requested_hours_week(text, staff.book(store)['selected_week'])
        if error:
            result.update(answer=error, hours_period_error=error)
            return result
        chart = hours(store, week); result['hours_chart'] = chart; data['hours_chart'] = chart
        if not n:
            answer = 'You have 0 employees saved in '+data['team_name']+'. Add an employee or import an employee list before comparing hours.'
        elif not chart['has_saved_schedule'] or not any(r['minutes'] for r in chart['rows']):
            answer = 'There are no positive planned hours in the saved schedules for '+chart['week_start']+' through '+chart['week_end']+'. The graph includes all '+str(n)+' employees at 0 planned hours.'
        else:
            top = chart['rows'][0]['minutes']; leaders = [r['name'] for r in chart['rows'] if r['minutes']==top]
            answer = ', '.join(leaders)+(' are tied for' if len(leaders)>1 else ' has')+' the most planned hours: '+format(top/60,'.2f')+' hours for '+chart['week_start']+' through '+chart['week_end']+'. The graph includes all '+str(n)+' saved employees, with breaks subtracted.'
        result['answer'] = answer+' These are planned shifts, separate from completed work records. Ask who worked the most to compare recorded work instead.'
        return result
    if n == 0:
        result['answer'] = 'You have 0 employees saved in '+data['team_name']+'. Choose Add employee, or Import employees to review a CSV, text file or text PDF. A document attached as a source does not become an employee until you review and save the import.'
        return result
    status = f"{n} employee{'s' if n!=1 else ''} saved in {data['team_name']} ({data['active_count']} current, {data['former_count']} former, {data['future_count']} not started as of {data['as_of_date']})"
    if contact:
        rows = data['employees']
        named = named_short or [e for e in rows if re.search(r'(?<!\w)'+re.escape(e['name'].casefold())+r'(?!\w)',text)]
        if len(named)==1: rows=named; nav['employee_id']=rows[0]['id']
        lines = [e['name']+': '+('; '.join(x for x in [('Phone '+e['phone']) if e['phone'] else '', ('Email '+e['email']) if e['email'] else ''] if x) or 'no phone or email saved') for e in rows[:8]]
        result['answer'] = 'Contacts are saved with each employee. '+status+'.\n'+'\n'.join(lines)+('\nThe Contacts view contains all remaining employees.' if len(rows)>8 else '')+'\nChoose an employee to add or edit their details. Nobody has been contacted.'
    else:
        result['answer'] = 'You have '+status+'.'+('' if count else '\n'+', '.join(e['name'] for e in data['employees'][:20])+('. The Employees view contains the rest.' if n>20 else '.'))+' The Employees view is open.'
    return result
