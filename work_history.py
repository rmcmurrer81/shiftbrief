"""Recorded work and dated raise comparisons, separate from planned schedules."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import calendar,re,uuid
from briefing import digest,now
import staffing as staff
from employee_pay import transaction

SCHEMA='shiftbrief.work-record.v1'

def records(store):
    return store.data.get('work_records',{}).get(store.production_id,[])

def signature(store):
    return digest({'team':store.production_id,'records':records(store),'employees':staff.book(store)['employees']})

def validate_record(row,employees):
    required={'schema','id','employee_id','date','start','end','unpaid_minutes','note','source','recorded_at'}
    if not isinstance(row,dict) or set(row)-required-{'scheduled_start'} or not required<=set(row) or row['schema']!=SCHEMA:
        raise ValueError('Invalid recorded-work structure.')
    if row['employee_id'] not in employees:raise ValueError('Work record belongs to an unknown employee.')
    if not isinstance(row['id'],str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',row['id']):raise ValueError('Invalid work record ID.')
    if not isinstance(row['date'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',row['date']):raise ValueError('Use YYYY-MM-DD for the work date.')
    date.fromisoformat(row['date'])
    for key in ('start','end','unpaid_minutes'):
        if type(row[key]) is not int:raise ValueError('Work times must be whole minutes.')
    if not (0<=row['start']<1440 and row['start']<row['end']<=row['start']+1440 and 0<=row['unpaid_minutes']<row['end']-row['start']):
        raise ValueError('Check clock-in, clock-out and unpaid break minutes.')
    if 'scheduled_start' in row and (type(row['scheduled_start']) is not int or not 0<=row['scheduled_start']<1440):raise ValueError('Invalid scheduled-start reference.')
    for key,limit in (('note',1000),('source',200),('recorded_at',80)):
        if not isinstance(row[key],str) or len(row[key])>limit or '\x00' in row[key]:raise ValueError('Invalid work-record text.')
    employee=employees[row['employee_id']]
    if row['date']<employee['start_date'] or (employee.get('end_date') and row['date']>=employee['end_date']):raise ValueError('Work date falls outside the saved employment dates.')
    return row

_MONTHS={name.lower():i for i,name in enumerate(calendar.month_name) if name}
_MONTHS.update({name.lower():i for i,name in enumerate(calendar.month_abbr) if name})
_MONTH_PATTERN=r'\b('+'|'.join(_MONTHS)+r')\s+(\d{4})\b'
_PERIOD_ERROR='Which work dates should I compare? Use one YYYY-MM-DD date, a start and end date, a month and year, or last month. I have not substituted another period.'


def period(text,today):
    """Resolve one complete requested scope, rejecting unconsumed date clauses."""
    iso=list(re.finditer(r'\b\d{4}-\d{2}-\d{2}\b',text))
    months=list(re.finditer(_MONTH_PATTERN,text))
    relative=list(re.finditer(r'\b(?:yesterday|today|(?:last|this|selected) (?:week|month|year)|(?:past|last) \d{1,4} days)\b',text))
    groups=sum(bool(x) for x in (iso,months,relative))
    if groups>1 or len(iso)>2 or len(months)>2 or len(relative)>1:raise ValueError(_PERIOD_ERROR)
    matches=iso or months or relative; remaining=text
    for m in reversed(matches):remaining=remaining[:m.start()]+remaining[m.end():]
    # Missing years, additional dates/periods and unsupported calendars must not disappear.
    if re.search(r'\b(?:'+ '|'.join(_MONTHS) +r'|weeks?|months?|years?|days?|next|tomorrow|spring|summer|winter|autumn|tonight|ytd|quarter)\b|\d',remaining):raise ValueError(_PERIOD_ERROR)
    if not matches:
        if re.search(r'\b(?:before|after|between|since|until|through|during|from)\b',text):raise ValueError(_PERIOD_ERROR)
        return None,today.isoformat(),'All recorded work through '+today.isoformat()
    if len(matches)==2:
        between=text[matches[0].end():matches[1].start()].strip()
        if between not in ('to','through','until','–','-') and not (between=='and' and re.search(r'\bbetween\s*$',text[:matches[0].start()])):raise ValueError(_PERIOD_ERROR)
    if iso:
        values=[date.fromisoformat(m[0]) for m in iso]; start=values[0];end=values[-1]
    elif months:
        values=[date(int(m[2]),_MONTHS[m[1]],1) for m in months];start=values[0]
        end=values[-1].replace(day=calendar.monthrange(values[-1].year,values[-1].month)[1])
    else:
        value=relative[0][0]
        if value in ('today','yesterday'):start=end=today-timedelta(days=value=='yesterday')
        elif value.endswith('week'):
            if value=='selected week':raise ValueError('For recorded work, name the dates or say this week or last week.')
            start=today-timedelta(days=(today.weekday()+1)%7+(7 if value=='last week' else 0));end=start+timedelta(days=6)
        elif value.endswith('month'):
            start=today.replace(day=1)
            if value=='last month':start=(start-timedelta(days=1)).replace(day=1)
            end=start.replace(day=calendar.monthrange(start.year,start.month)[1])
        elif value.endswith('year'):
            year=today.year-(value=='last year');start=date(year,1,1);end=date(year,12,31)
        else:
            count=int(re.search(r'\d+',value)[0])
            if not 1<=count<=3660:raise ValueError('Choose from 1 to 3660 days.')
            start=today-timedelta(days=count-1);end=today
    if len(matches)==1:
        modifiers=re.findall(r'\b(?:before|after|since|from|through|until)\b',remaining)
        if len(modifiers)>1 or re.search(r'\bbetween\b',remaining):raise ValueError(_PERIOD_ERROR)
        modifier=modifiers[0] if modifiers else None
        if modifier=='before':
            end=min(start-timedelta(days=1),today)
            return None,end.isoformat(),'All recorded work through '+end.isoformat()
        if modifier in ('through','until'):
            end=min(end,today);return None,end.isoformat(),'All recorded work through '+end.isoformat()
        if modifier in ('since','from'):end=today
        if modifier=='after':start=end+timedelta(days=1);end=today
    if start>end:raise ValueError('The start date must come before the end date.')
    if start>today:raise ValueError('Those work dates are in the future. Actual completed work cannot be compared yet.')
    end=min(end,today)
    return start.isoformat(),end.isoformat(),start.isoformat()+' – '+end.isoformat()


def subject_ids(store,text):
    """Exact saved names only; partial, unknown or ambiguous people remain a question."""
    employees=staff.book(store)['employees']
    named=[e for e in employees if re.search(r'(?<!\w)'+re.escape(e['name'].casefold().replace('’',"'"))+r'(?!\w)',text)]
    subject=None
    for pattern in (
        r'^(?:show|list|tell me about) (.+?)(?:\x27s|\x27) (?:recorded |actual |completed )?(?:hours|work|attendance|late arrivals)',
        r'^how many hours (?:did|has|have) (.+?) (?:work|worked)\b',
        r'^did (.+?) work\b',
        r'^how (?:often|many times) (?:was|has|is|were) (.+?) (?:been )?late\b',
    ):
        match=re.search(pattern,text)
        if match:subject=match[1];break
    if subject:
        if subject in ('the team','our team','my team','all employees','everyone','everybody'):
            return []
        exact=[e for e in employees if e['name'].casefold().replace('’',"'")==subject]
        if len(exact)!=1:raise ValueError('Use one full saved employee name for this work-history question. I have not substituted the whole team or another person.')
        return [exact[0]['id']]
    if len({e['name'].casefold() for e in named})!=len(named):raise ValueError('More than one saved employee has that name. Select an exact employee record; I have not combined their work.')
    if named:return [e['id'] for e in named]
    if re.search(r'\b(?:he|she|his|her|their|they)\b',text):raise ValueError('Which employee do you mean? Use their full saved name so I can show the correct work records.')
    if not re.match(r'^(?:who|which|compare|rank)\b',text) and not re.search(r'\b(?:everyone|everybody|each|all|team|employees|people)\b',text) and not re.fullmatch(r'(?:show|list)(?: me)? (?:the )?(?:recorded |actual |completed )?(?:work history|hours|work|attendance|late arrivals)(?: (?:for|in|on|from|between|since|last|this|today|yesterday).*)?[?.! ]*',text):
        raise ValueError('Do you want the whole team or one employee’s recorded work? Name the employee or ask to compare the team.')
    return []

def base(store,kind,title):
    return {'kind':kind,'title':title,'team_id':store.production_id,'source_sha256':signature(store),'as_of_date':date.today().isoformat()}

def work_read(store,text,late=False,employee_ids=None):
    employees=staff.book(store)['employees']
    date_text=text
    for employee in employees:date_text=re.sub(r'(?<!\w)'+re.escape(employee['name'].casefold().replace('’',"'"))+r'(?!\w)','',date_text)
    start,end,label=period(date_text,date.today())
    employee_ids=subject_ids(store,text) if employee_ids is None else employee_ids
    if employee_ids:
        employees=[e for e in employees if e['id'] in employee_ids]
        if len(employees)!=len(employee_ids):raise ValueError('That employee selection is no longer available. Ask again with the current full name.')
    selected=[deepcopy(r) for r in records(store) if (not start or r['date']>=start) and r['date']<=end and (not employee_ids or r['employee_id'] in employee_ids)]
    rows=[]
    for employee in employees:
        own=[r for r in selected if r['employee_id']==employee['id']]
        comparable=[r for r in own if 'scheduled_start' in r]
        late_rows=[r for r in comparable if r['start']>r['scheduled_start']]
        rows.append({'employee_id':employee['id'],'name':employee['name'],'minutes':sum(r['end']-r['start']-r['unpaid_minutes'] for r in own) if own else None,
                     'record_count':len(own),'late_count':len(late_rows) if comparable else None,'comparable_starts':len(comparable),
                     'status':'future' if employee['start_date']>end else 'former' if employee.get('end_date') and employee['end_date']<=end else 'active'})
    key='late_count' if late else 'minutes';rows.sort(key=lambda r:(r[key] is None,-(r[key] or 0),r['name']))
    out=base(store,'attendance' if late else 'worked','Recorded attendance' if late else 'Hours actually worked')
    out.update(subject_employee_ids=employee_ids,rows=rows,records=selected,start_date=start,end_date=end,period=label,record_count=len(selected),
               first_recorded_date=min((r['date'] for r in selected),default=None),last_recorded_date=max((r['date'] for r in selected),default=None),
               total_minutes=sum(r['minutes'] or 0 for r in rows),date_basis='Shift start date; unpaid breaks deducted')
    known=[r for r in rows if r[key] is not None]
    if not known:
        answer=('I don’t have recorded clock-ins with scheduled-start references for those dates.' if late else 'I don’t have completed work records for those dates yet.')+' I opened the recorded-work view so you can add them.'
    else:
        highest=known[0][key];leaders=[r['name'] for r in known if r[key]==highest]
        if employee_ids and len(rows)==1:
            row=rows[0]
            answer=(row['name']+' has '+str(row['late_count'])+' recorded late arrivals out of '+str(row['comparable_starts'])+' comparable recorded starts.' if late else row['name']+' has '+format(row['minutes']/60,'.2f')+' recorded hours, with unpaid breaks deducted.')
        elif late and highest==0:answer='No late arrival is recorded among the comparable starts for these dates. Missing clock-ins are not counted as punctual attendance.'
        elif late:answer=', '.join(leaders)+(' tie for' if len(leaders)>1 else ' has')+' the most recorded late arrivals: '+str(highest)+'. The table shows how many recorded starts were available for each person.'
        else:answer=', '.join(leaders)+(' tie for' if len(leaders)>1 else ' has')+' the most recorded work: '+format(highest/60,'.2f')+' hours. That is from completed work records, with unpaid breaks deducted.'
    answer+=' Scope: '+label+'.'
    if selected:answer+=' The available records cover '+out['first_recorded_date']+' through '+out['last_recorded_date']+'.'
    if any(r[key] is None for r in rows):answer+=' People without records are marked “Not recorded,” rather than counted as zero.'
    out['summary']=answer
    return out

def raises_read(store,text):
    today=date.today();explicit=re.findall(r'\b\d{4}-\d{2}-\d{2}\b',text)
    ranged=bool(re.search(r'\b(?:before|after|since|from|between|through|until|during|(?:last|this|next) (?:week|month|year))\b|'+_MONTH_PATTERN,text))
    if ranged:
        start,end,label=period(text,today)
    else:
        if len(explicit)>1:raise ValueError('Choose one as-of date or an explicit date range for the raise comparison.')
        remaining=re.sub(r'\b\d{4}-\d{2}-\d{2}\b','',text)
        if re.search(r'\b(?:'+ '|'.join(_MONTHS)+r'|weeks?|months?|years?|tomorrow|yesterday)\b|\d',remaining):raise ValueError('Which date should I use for the raises? Use an as-of YYYY-MM-DD date or a complete work-date range.')
        if explicit:today=date.fromisoformat(explicit[0])
        if today>date.today():raise ValueError('That date is in the future. Ask for a past or current as-of date to compare recorded raises.')
        start=None;end=today.isoformat();label='As of '+end
    out=base(store,'raises','Everyone’s latest recorded raise');out['as_of_date']=end;rows=[]
    for employee in staff.book(store)['employees']:
        eligible=sorted(enumerate(employee.get('pay_history',[])),key=lambda p:(p[1]['effective_date'],p[0]))
        eligible=[r for _,r in eligible if r['effective_date']<=end]
        increases=[(a,b) for a,b in zip(eligible,eligible[1:]) if a['currency']==b['currency'] and b['amount_minor']>a['amount_minor'] and (not start or b['effective_date']>=start)]
        row={'employee_id':employee['id'],'name':employee['name'],'effective_date':None,'previous_rate':None,'rate':None,'days_since':None,'reason':'No recorded increase in this period','history':deepcopy(eligible)}
        if increases:
            a,b=increases[-1];row.update(effective_date=b['effective_date'],previous_rate=deepcopy(a),rate=deepcopy(b),days_since=(date.fromisoformat(end)-date.fromisoformat(b['effective_date'])).days,reason=b['reason'])
        rows.append(row)
    out.update(rows=rows,period=label,start_date=start,end_date=end)
    answer='Latest recorded raise for each person — '+label+': '
    answer+='; '.join(r['name']+' — '+(r['effective_date']+' ('+r['rate']['currency']+' '+r['previous_rate']['amount']+' → '+r['rate']['amount']+'/hr)' if r['rate'] else 'no recorded increase in this period') for r in rows)+'.' if rows else 'No employees are saved yet.'
    answer+=' Starting rates and changes after the selected end date are excluded. I compare increases only within the same currency.'
    out['summary']=answer;return out


def respond(store,thread,message):
    low=re.sub(r'\s+',' ',message.casefold().replace('’',"'")).strip()
    low=re.sub(r'^(?:please |(?:can|could|would) you (?:please )?)+','',low)
    question=bool(re.match(r'^(?:who|which|what|when|how|did|show|list|tell|compare|rank|give me)\b',low))
    all_people=bool(re.search(r'\b(?:everyone|everybody|each|all|team|employees|people)\b',low) or re.match(r'^(?:who|which employees)\b',low))
    raises=question and all_people and bool(re.search(r'\b(?:raise|raises|increase|increases)\b',low))
    late=question and bool(re.search(r'\b(?:late|lateness|tardy|attendance)\b',low))
    worked=question and not re.search(r'\b(?:longest|how long|how many (?:days|months|years))\b',low) and bool(re.search(r'\bworked\b|\bdid\b.+\bwork\b|\b(?:actual|recorded|completed|past|historical) (?:work|hours|shifts)\b|\b(?:work history|timesheets?|clock.ins?)\b',low))
    previous=thread.get('messages',[])[-1] if thread.get('messages') else {}
    previous_read=previous.get('work_history') if previous.get('role')=='assistant' else None
    context=previous_read if isinstance(previous_read,dict) and previous_read.get('team_id')==store.production_id and previous_read.get('kind') in ('worked','attendance','raises') else None
    time_only=re.sub(r'^(?:what about |and |show me )','',low).strip('?.! ')
    followup=bool(context and re.fullmatch(r'(?:last|this) (?:week|month|year)|yesterday|today|\d{4}-\d{2}-\d{2}(?: (?:to|through) \d{4}-\d{2}-\d{2})?|(?:'+ '|'.join(_MONTHS)+r') \d{4}',time_only))
    # Context must be the immediately preceding answer, never an old topic after a shift.
    thread.pop('work_history_context',None)
    if followup:worked=context['kind']=='worked';late=context['kind']=='attendance';raises=context['kind']=='raises'
    if not (raises or late or worked):return None
    if re.search(r'\b(?:if|hypothetically|suppose|would have)\b',low):return None
    try:
        if re.search(r'\b(?:except|excluding|exclude|without|versus|vs|overtime|average|per day|per week)\b',low):raise ValueError('That comparison adds a condition I have not applied. Ask for total recorded hours or late-arrival counts for the team or a full saved employee name and one date range.')
        read=raises_read(store,time_only if followup else low) if raises else work_read(store,time_only if followup else low,late,context.get('subject_employee_ids',[]) if followup else None)
    except (ValueError,OverflowError) as exc:
        return {'kind':'work_history','answer':str(exc),'navigation':{'screen':'comparison','view':'work_history'},'work_history':{**base(store,'clarification','Choose the work records'),'summary':str(exc),'rows':[]}}
    return {'kind':'work_history','answer':read['summary'],'navigation':{'screen':'comparison','view':'work_history'},'work_history':read}

def draft_record(store,payload):
    if payload.get('team_id')!=store.production_id:raise ValueError('The selected team changed.')
    employees={e['id']:e for e in staff.book(store)['employees']}
    row={k:payload.get(k) for k in ('employee_id','date','start','end','unpaid_minutes','note')}
    row.update(schema=SCHEMA,id='preview',source='Employer entered completed work',recorded_at='Pending save')
    if payload.get('scheduled_start') is not None:row['scheduled_start']=payload['scheduled_start']
    validate_record(row,employees)
    end=datetime.combine(date.fromisoformat(row['date']),datetime.min.time())+timedelta(minutes=row['end'])
    if end>datetime.now():raise ValueError('Only completed work can be recorded. Check the work date and clock-out time.')
    for prior in records(store):
        if prior['employee_id']!=row['employee_id']:continue
        anchor=datetime.combine(date.fromisoformat(prior['date']),datetime.min.time())
        a=anchor+timedelta(minutes=prior['start']);b=anchor+timedelta(minutes=prior['end'])
        start=end-timedelta(minutes=row['end']-row['start'])
        if start<b and a<end:raise ValueError('This overlaps an existing work record for that employee.')
    result={'team_id':store.production_id,'source_sha256':signature(store),'record':row,'employee_name':employees[row['employee_id']]['name'],'net_minutes':row['end']-row['start']-row['unpaid_minutes']}
    result['preview_sha256']=digest(result);return result

def save_record(store,payload):
    request_id=payload.get('request_id')
    if not isinstance(request_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',request_id):raise ValueError('A saved-work request ID is required.')
    binding=digest(payload)
    def commit(trial):
        prior=next((r for r in trial.data.get('work_record_operations',[]) if r['request_id']==request_id),None)
        if prior:
            if prior['binding']!=binding:raise ValueError('This request ID was already used for different work.')
            return prior['result']
        review=draft_record(trial,payload)
        if payload.get('expected_preview_sha256')!=review['preview_sha256']:raise ValueError('The work records changed. Review this entry again before saving.')
        row=review['record'];row.update(id=uuid.uuid4().hex,recorded_at=now())
        target=trial.data.setdefault('work_records',{}).setdefault(trial.production_id,[])
        if len(target)>=20000:raise ValueError('This team has reached the 20,000 work-record limit.')
        target.append(row);result={'saved':True,'record':deepcopy(row),'employee_name':review['employee_name'],'team_id':trial.production_id}
        trial.data.setdefault('work_record_operations',[]).append({'request_id':request_id,'binding':binding,'result':result})
        return result
    return transaction(store,commit)
