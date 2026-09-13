"""Read-only team hourly-rate and calendar-tenure comparisons from saved records."""
from calendar import monthrange
from copy import deepcopy
from datetime import date, timedelta
import re
from briefing import digest
import staffing as staff


def _intent(message):
    text = re.sub(r'\s+', ' ', message.strip().casefold().replace('’', "'"))
    if not re.match(r'^(?:please\s+)?(?:who|which|how|what|compare|rank|show|list|tell me)\b', text):
        return None
    if re.search(r'\b(?:give|set|raise|lower|increase|decrease|record|save|change|update|delete|terminate|fire)\b', text):
        return None
    pay = bool(re.search(r'\b(?:pay|paid|wages?|hourly|rates?|money|makes?|earns?|earnings)\b', text)
               and re.search(r'\b(?:most|highest|best|compare|rank|everyone|everybody|each|all|team|employees|staff)\b', text))
    tenure = bool(re.search(r'\b(?:how long|how many (?:days|months|years)|tenure|length of service|longest|start(?:ed|ing)?|hire dates?)\b', text)
                  and (re.search(r'\b(?:everyone|everybody|each|all|team|employees|staff|people)\b', text)
                       or re.search(r'\b(?:who|which)\b.*\blongest\b', text)))
    if not (pay or tenure):
        return None
    return text, (['hourly_pay'] if pay else []) + (['tenure'] if tenure else [])


def _day(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _as_of(text, today):
    explicit = list(re.finditer(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:today|yesterday|tomorrow)\b', text))
    remaining = text
    for match in reversed(explicit):
        remaining = remaining[:match.start()] + remaining[match.end():]
    remaining = re.sub(r'\bhow many (?:days|months|years)\b', '', remaining)
    ambiguous = re.search(r'\b(?:last|next|this|past)\s+(?:weeks?|months?|years?)\b|\b(?:between|since|before|after|until|during|ever|all time|spring|summer|autumn|winter|ytd|year.to.date)\b|\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|\d', remaining)
    if len(explicit) > 1 or ambiguous:
        return None, 'Choose one date: YYYY-MM-DD, today, yesterday or tomorrow. I have not substituted today for another period.'
    if re.search(r'\b(?:would|could|should|if|assuming|suppose|hypothetically)\b', text):
        return None, 'I can compare saved hourly rates and recorded time on the team for one date. A hypothetical change has not been applied.'
    if not explicit:
        return today, None
    value = explicit[0][0]
    result = today + timedelta(days={'today': 0, 'yesterday': -1, 'tomorrow': 1}[value]) if value in ('today','yesterday','tomorrow') else _day(value)
    return (result, None) if result else (None, 'That date is not valid. Use one YYYY-MM-DD date.')


def _span(start, end):
    """Calendar elapsed time, never attendance; clamp month anniversaries."""
    months = (end.year-start.year)*12 + end.month-start.month
    def anniversary(count):
        year, month0 = divmod(start.year*12 + start.month-1 + count, 12)
        return date(year, month0+1, min(start.day, monthrange(year, month0+1)[1]))
    anchor = anniversary(months)
    if anchor > end:
        months -= 1
        anchor = anniversary(months)
    years, months = divmod(months, 12)
    days = (end-anchor).days
    parts = [str(n)+' '+unit+('s' if n!=1 else '') for n,unit in ((years,'year'),(months,'month'),(days,'day')) if n]
    return ', '.join(parts) if parts else '0 days'


def _row(employee, as_of):
    start = _day(employee.get('start_date')); end_raw = employee.get('end_date'); end = _day(end_raw) if end_raw else None
    bad = not start or (end_raw and not end) or (end and end < start)
    status = 'unknown' if bad else 'future' if start > as_of else 'former' if end and end <= as_of else 'active'
    tenure = {'status':'unknown', 'days':None, 'through_date':None, 'label':'Start or end date unavailable'}
    if not bad:
        if status == 'future':
            tenure.update(status='not_started', label='Starts '+start.isoformat())
        else:
            through = min(as_of, end) if end else as_of
            tenure.update(status='elapsed', days=(through-start).days, through_date=through.isoformat(), label=_span(start, through))
    rate = None; rate_status = 'not_recorded'
    history = employee.get('pay_history', [])
    valid = isinstance(history, list)
    if valid:
        for item in history:
            if not isinstance(item, dict) or not _day(item.get('effective_date')) or not re.fullmatch(r'[A-Z]{3}', str(item.get('currency',''))):
                valid = False; break
            amount = item.get('amount_minor')
            if isinstance(amount, bool) or not isinstance(amount, int) or not 0 <= amount <= 1000000:
                valid = False; break
            expected = f'{amount//100}.{amount%100:02d}'
            if item.get('amount') != expected:
                valid = False; break
    if not valid:
        rate_status = 'invalid_saved_history'
    else:
        from employee_pay import rate_on
        saved = rate_on(employee, as_of.isoformat())
        if saved is not None:
            rate = {k:deepcopy(saved[k]) for k in ('amount_minor','amount','currency','effective_date')}
            rate_status = 'recorded'
    return {'employee_id':employee.get('id'), 'name':employee.get('name') or 'Unnamed saved employee',
            'expected_revision':employee.get('revision'), 'start_date':employee.get('start_date'),
            'end_date':end_raw, 'employment_status':status, 'rate':rate, 'rate_status':rate_status, 'tenure':tenure}


def respond(store, message):
    parsed = _intent(message)
    if parsed is None:
        return None
    text, requested = parsed
    pid = store.production_id
    source = deepcopy(store.data.get('staffing', {}).get(pid, {}).get('employees', []))
    named = [e for e in source if re.search(r'(?<!\w)'+re.escape(str(e.get('name','')).casefold())+r'(?!\w)', text)]
    if named and not re.search(r'\b(?:everyone|everybody|all|team|employees|staff|people)\b', text):
        return None
    team = next((p.get('title') for p in store.data.get('productions', []) if p.get('id')==pid), 'This team')
    today = staff.date.today(); as_of, error = _as_of(text, today)
    scope = {'team_id':pid, 'employees':[{k:deepcopy(e.get(k)) for k in ('id','name','revision','start_date','end_date','pay_history')} for e in source]}
    data = {'schema':'shiftbrief.employee-comparison.v1', 'status':'clarification' if error else 'ready',
            'team_id':pid, 'team_name':team, 'as_of_date':as_of.isoformat() if as_of else None,
            'requested':requested, 'request_text':message, 'scope_sha256':digest(scope), 'rows':[],
            'pay':{'metric':'saved_hourly_rate', 'scope':'active_employees_as_of_date', 'groups':[],
                   'missing_employee_ids':[], 'excluded_employee_ids':[], 'earnings_available':False},
            'tenure':{'metric':'calendar_days_since_recorded_start', 'leader_ids':[]}, 'clarification':error}
    summary = {'team_id':pid,'team_name':team,'as_of_date':data['as_of_date'],'total_records':len(source),
               'active_count':0,'former_count':0,'future_count':0,'unknown_count':0}
    response = {'kind':'employee_comparison','navigation':{'screen':'employees','view':'comparison','employee_id':None},
                'employee_summary':summary,'employee_comparison':data,'answer':error or ''}
    if error:
        return response
    rows = [_row(e, as_of) for e in source]
    rows.sort(key=lambda r:({'active':0,'former':1,'future':2,'unknown':3}[r['employment_status']],
                            -(r['tenure']['days'] if r['tenure']['days'] is not None else -1),r['name'].casefold(),str(r['employee_id'])))
    data['rows'] = rows
    for row in rows:
        summary[row['employment_status']+'_count'] += 1
    active = [r for r in rows if r['employment_status']=='active']
    currencies = sorted({r['rate']['currency'] for r in active if r['rate'] is not None})
    for currency in currencies:
        ranked = [{'employee_id':r['employee_id'],'name':r['name'],**r['rate']} for r in active if r['rate'] and r['rate']['currency']==currency]
        ranked.sort(key=lambda r:(-r['amount_minor'],r['name'].casefold(),str(r['employee_id'])))
        previous = None; rank = 0
        for index, row in enumerate(ranked):
            if row['amount_minor'] != previous:
                rank = index+1
            row['rank'] = rank; previous = row['amount_minor']
        data['pay']['groups'].append({'currency':currency,'rows':ranked,'leader_ids':[r['employee_id'] for r in ranked if r['rank']==1]})
    data['pay']['missing_employee_ids'] = [r['employee_id'] for r in active if r['rate'] is None]
    data['pay']['excluded_employee_ids'] = [r['employee_id'] for r in rows if r['employment_status']!='active']
    known = [r for r in active if r['tenure']['days'] is not None]
    if known:
        longest = max(r['tenure']['days'] for r in known)
        data['tenure']['leader_ids'] = [r['employee_id'] for r in known if r['tenure']['days']==longest]
    if not rows:
        response['answer'] = 'No employees are saved in '+team+'. Add an employee or review an employee import to start this comparison.'
        return response
    parts = []
    if 'hourly_pay' in requested:
        for group in data['pay']['groups']:
            leaders = [r for r in group['rows'] if r['rank']==1]
            parts.append(', '.join(r['name'] for r in leaders)+(' share' if len(leaders)>1 else ' has')+' the highest saved '+group['currency']+' hourly rate among active employees: '+leaders[0]['amount']+' / hour.')
        if not data['pay']['groups']:
            parts.append('No usable hourly rate is saved for an active employee on '+data['as_of_date']+'.')
        missing = len(data['pay']['missing_employee_ids'])
        if missing:
            parts.append(str(missing)+' active employee'+('s have' if missing!=1 else ' has')+' no usable rate recorded; missing is not zero.')
        if len(data['pay']['groups'])>1:
            parts.append('Different currencies are shown separately, without conversion.')
        parts.append('These are saved hourly rates, not earnings or take-home pay.')
    if 'tenure' in requested:
        parts.append('Time on the team as of '+data['as_of_date']+': '+ '; '.join(r['name']+' — '+r['tenure']['label']+(' (former)' if r['employment_status']=='former' else '') for r in rows[:6])+'.')
        if len(rows)>6:
            parts.append('All '+str(len(rows))+' saved employees are in the table.')
        parts.append('Time is measured from saved dates; former employees stop at their recorded unavailable-from date. It is not attendance.')
    response['answer'] = ' '.join(parts)
    return response
