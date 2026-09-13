"""Finite, source-bound planning restrictions. No personnel or schedule writes."""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import re
from briefing import digest

SCHEMA = 'shiftbrief.staffing-constraints.v1'
ISSUES = {'ambiguous_name', 'missing_time', 'missing_amount', 'unsupported', 'contradictory'}
TIME = re.compile(r'\b(?:([01]?\d|2[0-4]):([0-5]\d)\s*(am|pm)?|(1[0-2]|[1-9])\s*(am|pm))\b', re.I)
WEEKDAYS = [('Sunday','Sun'),('Monday','Mon'),('Tuesday','Tue'),('Wednesday','Wed'),('Thursday','Thu'),('Friday','Fri'),('Saturday','Sat')]
PLAIN = {'plan the selected week', 'plan this week', 'plan the week using saved availability'}
CONTEXT_SCHEMA = 'shiftbrief.staffing-constraints.selected-week.v2'
COMPOSED_SCHEMA = 'shiftbrief.staffing-constraints.followup.v2'
RESET = 'start a fresh plan for the selected week'

def is_reset(request):return request.strip().casefold().strip(' .!?') == RESET


# These conversational lead-ins carry no numeric or employee policy of their own.
# Consume at most one correction and one polite lead-in, in either order.
LEAD_INS=(re.compile(r'^(?:actually|instead|on second thought),?\s+',re.I),
          re.compile(r'^(?:please|can you|could you|would you|I want you to|I need you to)\s+',re.I))

def strip_lead_ins(value):
    rest=value;seen=set()
    for _ in range(2):
        found=False
        for i,pattern in enumerate(LEAD_INS):
            if i in seen:continue
            match=pattern.match(rest)
            if match:rest=rest[match.end():];seen.add(i);found=True;break
        if not found:break
    return rest

class RequestHeld(ValueError):
    pass

def exact_keys(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise RequestHeld('The proposed interpretation has an unsupported or missing field. Please clarify the request.')

def integer(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise RequestHeld('Use a valid whole-minute '+label+'.')
    return value

def text(value):
    if not isinstance(value,str) or not value.strip() or len(value)>1500:
        raise RequestHeld('Enter the literal planning request in 1–1500 characters.')
    return value.strip()

def person_from_quote(people, identity, quote):
    selected=next((p for p in people if p['id']==identity),None)
    if not selected: raise RequestHeld('The request refers to an employee who is not saved in this team.')
    full=[]
    for p in people:
        name=p['name'].strip()
        for match in re.finditer(r'(?<!\w)'+re.escape(name)+r'(?!\w)',quote,re.I):full.append((p,name,match.span()))
    # The word Ada inside Ada North is one complete longer name, not two people.
    named=[(p,name) for p,name,span in full if not any(other[2][0]<=span[0] and other[2][1]>=span[1] and other[2]!=span for other in full)]
    if not named:
        for p in people:
            first=p['name'].split()[0]
            if re.search(r'(?<!\w)'+re.escape(first)+r'(?!\w)',quote,re.I): named.append((p,first))
    if len(named)!=1 or named[0][0]['id']!=identity:
        raise RequestHeld('The employee name is missing or ambiguous. Use the full saved name.')
    return selected, named[0][1]

def date_from_quote(week, quote):
    import staffing as staff
    dates=staff.days(week);found=set()
    for raw in re.findall(r'\b\d{4}-\d{2}-\d{2}\b',quote):
        if raw not in dates: raise RequestHeld('The requested date is outside the selected week.')
        found.add(raw)
    for i,names in enumerate(WEEKDAYS):
        if re.search(r'\b(?:'+ '|'.join(names)+r')\b',quote,re.I):found.add(dates[i])
    if len(found)!=1: raise RequestHeld('Give one exact date or weekday within the selected week for each exclusion.')
    return found.pop()

def times_from_quote(quote):
    values=[]
    for m in TIME.finditer(quote):
        h=int(m[1] or m[4]); minute=int(m[2] or 0); period=m[3] or m[5]
        if period:
            if not 1<=h<=12: raise RequestHeld('Use an unambiguous time with AM/PM or the 24-hour clock.')
            h=h%12+(12 if period.lower()=='pm' else 0)
        if h==24 and minute: raise RequestHeld('24:00 is the only supported end-of-day time.')
        values.append(h*60+minute)
    if len(values)!=2: raise RequestHeld('Give both exact times, for example 13:00–17:00 or 1pm–5pm. Afternoon alone is ambiguous.')
    if any(v%15 for v in values): raise RequestHeld('The first version uses exact 15-minute boundaries. Confirm a quarter-hour time; nothing was rounded.')
    if values[1]<=values[0]: raise RequestHeld('An overnight exclusion needs two explicit dated windows within this week.')
    return values

def cap_from_quote(quote, selected_week=False):
    if re.search(r'(?<!\w)[−-]\s*[0-9]',quote):
        raise RequestHeld('A weekly cap cannot be negative. Enter zero or a positive maximum in hours or minutes.')
    if re.search(r'\b(?:no|without)\s+(?:a\s+)?(?:cap|limit)\b',quote,re.I):
        raise RequestHeld('No cap does not set a maximum. Remove that restriction or give one weekly upper limit.')
    if TIME.search(quote):
        raise RequestHeld('A weekly cap cannot silently include a time window. State the weekly maximum and any dated exclusion as separate clauses.')
    if re.search(r"\b(?:do not|don't|don’t|not)\s+(?:cap|limit)|\b(?:least|minimum)\b",quote,re.I):
        raise RequestHeld('A negated cap or minimum is not an upper limit. Clarify the requested weekly maximum.')
    if (not selected_week and not re.search(r'\b(?:week|weekly)\b',quote,re.I)) or re.search(r'\b\d{4}-\d{2}-\d{2}\b|\b(?:'+'|'.join(n for pair in WEEKDAYS for n in pair)+r')\b',quote,re.I):
        raise RequestHeld('Confirm a weekly cap. Daily limits are not supported by this first version.')
    matches=re.findall(r'(?<![\w.])(\d+(?:\.\d+)?)\s*(hours?|hrs?|minutes?|mins?)\b',quote,re.I)
    if len(matches)!=1: raise RequestHeld('State one exact weekly cap with hours or minutes.')
    number,unit=matches[0]; minutes=Decimal(number)*(60 if unit.lower().startswith(('h','hr')) else 1)
    if minutes!=int(minutes) or not 0<=minutes<=10080 or int(minutes)%15:
        raise RequestHeld('Confirm a weekly cap in exact 15-minute units; nothing was rounded.')
    if not re.search(r'\b(cap|limit|at most|no more than|maximum|max)\b',quote,re.I):
        raise RequestHeld('Say at most or cap when giving a weekly upper limit. Fewer hours is not an exact cap.')
    return int(minutes)

def grammar_residue(quote, name, kind, selected_week=False):
    """An entire quoted clause must express one supported operation.

    Deliberately finite language: unknown syntax is a clarification, never a
    partially accepted command. Typed arguments still need separate value checks.
    """
    q=strip_lead_ins(' '.join(quote.strip().split()).rstrip('.!?'))
    who=re.escape(name)+r"(?:['’]s)?"
    polite='' # Shared finite lead-ins were consumed above; literal quote remains unchanged.
    if kind=='cap':
        amount=r'[0-9]+(?:\.[0-9]+)?\s*(?:hours?|hrs?|minutes?|mins?)'
        weekly=r'(?:(?:this|the selected)\s+week|weekly)'
        suffix=r'\s+(?:for\s+)?'+weekly
        if selected_week:suffix='(?:'+suffix+')?'
        body=(r'(?:(?:cap|limit)\s+'+who+r'\s+(?:at|to)\s+(?:no more than\s+)?'+amount+suffix+
              r'|give\s+'+who+r'\s+(?:no more than|at most)\s+'+amount+suffix+
              r'|'+who+r'\s+(?:should work\s+)?(?:no more than|at most)\s+'+amount+suffix+r')')
    else:
        day=r'(?:[0-9]{4}-[0-9]{2}-[0-9]{2}|'+ '|'.join(n for pair in WEEKDAYS for n in pair)+r')'
        clock_token=r'(?:(?:[01]?\d|2[0-4]):[0-5]\d\s*(?:am|pm)?|(?:1[0-2]|[1-9])\s*(?:am|pm))'
        span=day+r'\s+(?:(?:from|between)\s+)?'+clock_token+r'\s*(?:–|—|-|to|and)\s*'+clock_token
        body=(r'(?:keep\s+'+who+r'\s+off\s+(?:on\s+)?'+span+
              r'|exclude\s+'+who+r'\s+(?:on\s+)?'+span+
              r'|(?:do not schedule|don[’\x27]t schedule|avoid scheduling)\s+'+who+r'\s+(?:on\s+)?'+span+r')')
    if re.fullmatch(polite+body,q,re.I) is None:
        raise RequestHeld('This clause includes wording I cannot apply as one restriction. Use a weekly cap or an exact dated exclusion, and separate additional directions. No part was applied.')


def validate(store, week, request, envelope, expected_snapshot, *, selected_week=False):
    import staffing as staff
    request=text(request)
    exact_keys(envelope, {'snapshot_sha256','constraints','issues'})
    if envelope['snapshot_sha256']!=expected_snapshot: raise RequestHeld('The team/week snapshot changed. Read it again before planning.')
    if not isinstance(envelope['constraints'],list) or not isinstance(envelope['issues'],list): raise RequestHeld('Use a list of finite restrictions or clarification issues.')
    if len(envelope['constraints'])>12 or len(envelope['issues'])>12: raise RequestHeld('Use at most twelve restrictions in one reviewed request.')
    for issue in envelope['issues']:
        exact_keys(issue, {'quote','reason'})
        if not isinstance(issue['quote'],str) or issue['quote'] not in request or not issue['quote'].strip() or not isinstance(issue['reason'],str) or issue['reason'] not in ISSUES:
            raise RequestHeld('The clarification must refer to the literal request.')
    if envelope['issues']: raise RequestHeld('The request contains an ambiguous, contradictory or unsupported direction. Clarify it before creating a proposal.')
    rows=[];spans=[];caps={}
    for c in envelope['constraints']:
        kind=c.get('kind') if isinstance(c,dict) else None
        exact_keys(c, {'kind','employee_id','date','start','end','quote'} if kind=='exclude' else {'kind','employee_id','max_minutes','quote'} if kind=='cap' else set())
        if not isinstance(kind,str) or kind not in {'exclude','cap'}: raise RequestHeld('Only employee/date/time exclusions and weekly caps are supported.')
        quote=text(c['quote']);pos=request.find(quote)
        if pos<0: raise RequestHeld('Each interpretation must quote the actual request.')
        if any(pos<b and pos+len(quote)>a for a,b in spans): raise RequestHeld('Use a separate literal clause for each restriction; overlapping interpretations need clarification.')
        spans.append((pos,pos+len(quote)))
        person,matched_name=person_from_quote(staff.book(store)['employees'],c['employee_id'],quote)
        if kind=='exclude':
            key=date_from_quote(week,quote);a,b=times_from_quote(quote)
            if c['date']!=key or integer(c['start'],0,1439,'start time')!=a or integer(c['end'],1,1440,'end time')!=b:
                raise RequestHeld('The proposed date or times differ from the literal request.')
            label=f"{person['name']}: no proposed work {key}, {clock(a)}–{clock(b)}."
        else:
            amount=cap_from_quote(quote,selected_week)
            if integer(c['max_minutes'],0,10080,'weekly cap')!=amount: raise RequestHeld('The proposed cap differs from the literal request.')
            if person['id'] in caps: raise RequestHeld('More than one cap names the same employee. Confirm one weekly limit.')
            caps[person['id']]=amount;label=f"{person['name']}: at most {amount/60:g} planned hours this week."
        grammar_residue(quote,matched_name,kind,selected_week)
        rows.append({**deepcopy(c),'label':label})
    covered=set(range(len(request)-len(strip_lead_ins(request))))
    for a,b in spans:covered.update(range(a,b))
    residue=''.join(' ' if i in covered else char for i,char in enumerate(request))
    residue=' '.join(re.findall(r'[\w]+',residue.lower()))
    residue=re.sub(r'\b(?:and|also|please|then)\b','',residue).strip()
    if not rows:
        if request.lower().strip(' .!?') not in PLAIN and not (selected_week and is_reset(request)): raise RequestHeld('Give an exact exclusion or weekly cap, or ask to plan the selected week.')
    elif residue: raise RequestHeld('Part of the request was not interpreted. Clarify all directions before planning; no part was applied.')
    policy={'schema':SCHEMA,'team_id':store.production_id,'week_start':week,'request':request,'snapshot_sha256':expected_snapshot,'envelope':deepcopy(envelope),'constraints':rows}
    if selected_week:policy.update(schema=CONTEXT_SCHEMA,week_basis='explicit selected week')
    policy['sha256']=digest(policy)
    return policy

def clock(value): return f'{value//60:02d}:{value%60:02d}'

def allows(policy, identity, key, a, b, total):
    for c in policy['constraints']:
        if c['employee_id']!=identity: continue
        if c['kind']=='cap' and total+b-a>c['max_minutes']: return False
        if c['kind']=='exclude' and c['date']==key and a<c['end'] and c['start']<b:return False
    return True

def boundaries(policy,key):
    return {t for c in policy['constraints'] if c['kind']=='exclude' and c['date']==key for t in (c['start'],c['end'])}

def active_proposal(store,week):
    import staffing as staff
    latest=next((p for p in reversed(staff.book(store)['proposals']) if p['kind']=='week' and p['week_start']==week),None)
    return latest if latest and not latest.get('accepted_at') else None


def compose(previous, update, parent):
    """Only a new cap for the same person replaces a restriction. Exclusions persist."""
    if previous is None or is_reset(update['request']):return deepcopy(update)
    rows=deepcopy(previous['constraints'])
    for row in rows:row.setdefault('origin_policy_sha256',previous['sha256'])
    for item in update['constraints']:
        row={**deepcopy(item),'origin_policy_sha256':update['sha256']}
        if row['kind']=='cap':
            rows=[old for old in rows if not (old['kind']=='cap' and old['employee_id']==row['employee_id'])]
            rows.append(row)
        elif not any(all(old.get(k)==row[k] for k in ('kind','employee_id','date','start','end')) for old in rows):rows.append(row)
    history=deepcopy(previous.get('request_history') or [{'request':previous['request'],'policy_sha256':previous['sha256']}])
    history.append({'request':update['request'],'policy_sha256':update['sha256']})
    value={'schema':COMPOSED_SCHEMA,'team_id':update['team_id'],'week_start':update['week_start'],
           'request':update['request'],'snapshot_sha256':update['snapshot_sha256'],
           'parent_proposal':{'id':parent['id'],'sha256':parent['sha256'],'policy_sha256':previous['sha256']},
           'update':deepcopy(update),'request_history':history,'constraints':rows}
    value['sha256']=digest(value)
    return value


def verify_policy(store,week,policy,_seen=None):
    import staffing as staff
    if staff.book(store)['selected_week']!=week or store.production_id!=policy['team_id'] or policy['week_start']!=week: raise ValueError('The selected team or week changed. Reopen the intended week before reviewing.')
    if policy['schema']==COMPOSED_SCHEMA:
        seen=set() if _seen is None else set(_seen)
        if policy['sha256'] in seen:raise ValueError('The saved restriction history is cyclic. Reopen the saved proposal.')
        seen.add(policy['sha256'])
        ref=policy['parent_proposal'];parent=next((p for p in staff.book(store)['proposals'] if p['id']==ref['id']),None)
        if not parent or parent['kind']!='week' or parent['week_start']!=week or parent.get('accepted_at') or parent['sha256']!=ref['sha256'] or staff.stamp({k:v for k,v in parent.items() if k!='sha256'})!=ref['sha256']:
            raise ValueError('The earlier proposal or its restriction history changed. Reopen the current proposal; no restrictions were dropped.')
        previous=parent['payload'].get('constraints')
        if not previous or previous['sha256']!=ref['policy_sha256']:raise ValueError('The earlier restriction origin changed. Reopen the current proposal.')
        verify_policy(store,week,previous,seen)
        update=verify_policy(store,week,policy['update'],seen)
        canonical=compose(previous,update,parent)
    else:
        canonical=validate(store,week,policy['request'],policy['envelope'],policy['snapshot_sha256'],selected_week=policy['schema']==CONTEXT_SCHEMA)
    if canonical!=policy: raise ValueError('The saved request interpretation changed. Ask for a fresh proposal.')
    return canonical


def suggest_preserving(store,week):
    """Rules-only Suggest retains the latest unaccepted restrictions without any AI call."""
    import staffing as staff
    with store.lock:
        parent=active_proposal(store,week);policy=parent['payload'].get('constraints') if parent else None
        if policy:staff.check_proposal(store,parent['id'],parent['sha256'])
        return staff.suggest_week(store,week,constraints=deepcopy(policy))


def verify_shifts(store, week, policy, plans):
    import staffing as staff
    verify_policy(store,week,policy);totals={}
    for plan in plans:
        for s in plan['shifts']:
            person=staff.employee(store,s['employee_id'])
            if not staff.qualifies(person,s['role']) or not any(w['start']<=s['start'] and w['end']>=s['end'] for w in staff.available(person,plan['date'])):
                raise ValueError('A proposed shift conflicts with the saved employee role or availability.')
            total=totals.get(person['id'],0)
            if not allows(policy,person['id'],plan['date'],s['start'],s['end'],total): raise ValueError('A proposed shift violates the reviewed exclusion or weekly cap. Edit the proposal or start a new request.')
            totals[person['id']]=total+s['end']-s['start']

def changes(before, after):
    """Compare actual dated shifts by fields, ignoring generated IDs."""
    rows=[]
    def shifts(day):return {(s['employee_id'],s['employee'],s['role'],s['start'],s['end'],tuple((b['start'],b['end']) for b in s.get('breaks',[]))) for s in (day or {}).get('shifts',[])}
    for old,new in zip(before,after):
        a,b=shifts(old),shifts(new)
        for direction,items in [('Remove',a-b),('Add',b-a)]:
            for identity,name,role,start,end,breaks in sorted(items):
                rows.append({'date':new['date'],'employee_id':identity,'employee':name,'kind':direction.lower(),'role':role,'start':start,'end':end,'breaks':list(breaks),'label':f'{direction} {name} · {new["date"]} · {clock(start)}–{clock(end)} · {role}'+(' · includes recorded breaks' if breaks else '')})
    return rows

def held_response(store,week,request,reason):
    """Ground additional facts in saved records; model prose is not displayed as fact."""
    import staffing as staff
    facts=[]
    for person in staff.book(store)['employees']:
        try: person_from_quote(staff.book(store)['employees'],person['id'],request)
        except RequestHeld: continue
        try:key=date_from_quote(week,request)
        except RequestHeld:continue
        available=staff.available(person,key)
        status=person.get('availability',{}).get(key,{}).get('status','unknown')
        if not available and status=='unknown':facts.append(f"{person['name']}'s availability for {key} is not provided. Edit availability before considering an assignment.")
        elif not available:facts.append(f"{person['name']} has no recorded eligible work window on {key}.")
        else:facts.append(f"{person['name']}'s recorded eligible windows on {key}: "+', '.join(clock(w['start'])+'–'+clock(w['end']) for w in available)+'.')
    return {'kind':'constraint_clarification','answer':str(reason),'request':request,'facts':facts,'actions':['edit_request','edit_availability'],'proposal':None}
