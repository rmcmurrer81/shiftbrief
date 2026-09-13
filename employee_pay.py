"""Exact reviewed hourly-rate changes; historical rates are never overwritten."""
from copy import copy, deepcopy
from decimal import Decimal, InvalidOperation
import json
import re
import uuid
from briefing import digest, now
import staffing as staff
import shift_schedule as daily


def transaction(store, operation):
    """Validate/mutate a private copy and persist once; retain original on failure."""
    with store.lock:
        previous = store.data
        staged = copy(store); staged.data = deepcopy(previous); staged.save = lambda: None
        result = operation(staged)
        store.data = staged.data
        try:
            store.save()
        except BaseException:
            # A writer that raises after its atomic replace has already committed.
            # Recognize only exact full-state equality; never overwrite foreign edits.
            try:
                saved = json.loads((store.path/'state.json').read_text(encoding='utf-8'))
            except (OSError, ValueError): saved = None
            if saved == staged.data:
                return deepcopy(result)
            store.data = previous
            raise
        return deepcopy(result)


def money(amount, currency):
    if not isinstance(amount,str) or not re.fullmatch(r'\d{1,5}(?:\.\d{1,2})?',amount.strip()):
        raise ValueError('Enter an hourly amount with at most two decimal places, for example 18.50.')
    try: value = Decimal(amount.strip())
    except InvalidOperation: raise ValueError('Enter a valid hourly amount.')
    if not Decimal('0') <= value <= Decimal('10000'): raise ValueError('Use an hourly amount from 0 to 10000.')
    if not isinstance(currency,str) or not re.fullmatch(r'[A-Z]{3}',currency):
        raise ValueError('Choose an explicit three-letter currency, for example USD. No currency conversion is performed.')
    return int(value*100), currency


def rate_on(employee, day):
    candidates = [(i,r) for i,r in enumerate(employee.get('pay_history',[])) if r['effective_date'] <= day]
    if not candidates: return None
    _, row = max(candidates,key=lambda x:(x[1]['effective_date'],x[0]))
    return deepcopy(row)


def rate_fields(employee, amount, currency, effective_date, reason):
    minor,currency = money(amount,currency); day=daily.day_key(effective_date)
    if day < employee['start_date'] or (employee.get('end_date') and day >= employee['end_date']):
        raise ValueError('The hourly rate date must fall within this employee’s recorded employment dates.')
    currencies={r['currency'] for r in employee.get('pay_history',[])}
    if currencies and currency not in currencies: raise ValueError('Keep this employee’s recorded currency. Currency conversion is not supported.')
    if not isinstance(reason,str) or not 1<=len(reason.strip())<=500: raise ValueError('Give this pay entry a short reason, such as starting rate or annual raise.')
    return {'amount_minor':minor,'amount':format(Decimal(minor)/100,'.2f'),'currency':currency,
            'effective_date':day,'reason':reason.strip()}


def propose(store, values):
    if not isinstance(values,dict) or set(values)-{'employee_id','expected_revision','amount','currency','effective_date','reason'}:
        raise ValueError('Supply the employee, exact revision, amount, currency, effective date and reason.')
    def change(staged):
        e=staff.employee(staged,values.get('employee_id'))
        if values.get('expected_revision') != e.get('revision',1): raise ValueError('Employee details changed. Reopen the current record before proposing pay.')
        fields=rate_fields(e,values.get('amount'),values.get('currency'),values.get('effective_date'),values.get('reason'))
        before=rate_on(e,fields['effective_date'])
        p={'id':uuid.uuid4().hex[:12],'kind':'hourly_pay','team_id':staged.production_id,'created':now(),
           'employee_id':e['id'],'employee_name':e['name'],'employee_revision':e.get('revision',1),
           'employee_sha256':digest(e),'current_at_effective_date':before,'fields':fields,
           'change_minor':None if before is None else fields['amount_minor']-before['amount_minor']}
        p['sha256']=digest(p);p['status']='pending'
        staff.book(staged).setdefault('pay_proposals',[]).append(p)
        return p
    return transaction(store,change)


def accept(store, values):
    if values.get('confirmation')!='YES': raise ValueError('Review the exact hourly rate and type YES to save it.')
    def change(staged):
        p=next((p for p in staff.book(staged).get('pay_proposals',[]) if p['id']==values.get('id')),None)
        if not p or p.get('status')!='pending' or p['team_id']!=staged.production_id: raise ValueError('Choose a pending pay proposal from this team.')
        if p['sha256']!=values.get('sha256') or digest({k:v for k,v in p.items() if k not in ('sha256','status')})!=p['sha256']:
            raise ValueError('The reviewed pay proposal changed. Reopen and review it.')
        e=staff.employee(staged,p['employee_id'])
        if e.get('revision',1)!=p['employee_revision'] or digest(e)!=p['employee_sha256']:
            raise ValueError('Employee details changed after this proposal. Review a new pay proposal.')
        f=p['fields'];rate_fields(e,f['amount'],f['currency'],f['effective_date'],f['reason'])
        entry={**deepcopy(f),'id':uuid.uuid4().hex[:12],'recorded_at':now(),'proposal_id':p['id'],'proposal_sha256':p['sha256']}
        e.setdefault('pay_history',[]).append(entry);e['revision']=e.get('revision',1)+1
        e['history'].append({'at':now(),'operation':'hourly_rate_recorded','entry':deepcopy(entry)})
        p.update(status='accepted',accepted_at=now())
        staff.book(staged)['events'].append({'at':now(),'kind':'hourly_rate_recorded','employee_id':e['id'],'effective_date':f['effective_date']})
        return {'saved':True,'employee':e,'entry':entry,'answer':'Saved '+e['name']+'’s '+f['currency']+' '+f['amount']+' hourly rate from '+f['effective_date']+'. Earlier pay entries remain in history. This is a rate record, not a payroll calculation.'}
    return transaction(store,change)



_NON_HOURLY_RATE = re.compile(r'\b(?:salary|salaries|salaried|monthly|annually|yearly|weekly|daily)\b|\bannual\b(?!\s+(?:raise|review|increase)\b)|(?:\bper\s+|\ba\s+|/)(?:month|year|week|day)\b', re.I)


def requested_hourly_fields(message, employee):
    """Prefill one exact hourly amount; uncertain units/numbers stay unfilled."""
    fields = {'reason': message}
    current = employee.get('pay_current')
    if current: fields['currency'] = current['currency']
    issues = []
    # Annual describes the raise in "annual raise", not a yearly rate.
    unsupported = _NON_HOURLY_RATE.search(message)
    dates = list(re.finditer(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', message))
    if len(dates) == 1:
        try:
            day = daily.day_key(dates[0][0])
            if day < employee['start_date'] or (employee.get('end_date') and day >= employee['end_date']):
                raise ValueError('outside employment')
            fields['effective_date'] = day
        except ValueError:
            issues.append('Enter one valid effective date within the employee\'s recorded employment dates, using YYYY-MM-DD.')
    else:
        issues.append('Enter one unambiguous effective date using YYYY-MM-DD; I left the date blank.')
    if unsupported:
        issues.insert(0, 'This form records hourly rates only. Salary, monthly, annual and other non-hourly amounts are not converted; I left the amount blank. Enter an explicit hourly rate to continue.')
        return fields, issues
    # Mask exact dates first so "to 2026-10-01" can never become rate 2026.
    masked = re.sub(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', lambda m: ' '*len(m[0]), message)
    candidates = list(re.finditer(r'\b(?:to|at|rate(?: of)?)\s+(?:([A-Z]{3})\s+)?(\$?[+\-]?(?:\d|\.)\S*)', masked, re.I))
    if len(candidates) != 1:
        issues.insert(0, 'Enter one exact hourly amount, such as 22.50 or $22.50, with no grouping separators and at most two decimal places; I left the amount blank.')
        return fields, issues
    match = candidates[0]
    # Additional numerical alternatives in the same rate clause require review.
    tail = re.split(r'\b(?:starting|effective|beginning|from|as of|because|reason)\b', masked[match.end():], maxsplit=1, flags=re.I)[0]
    raw = match[2]
    if raw.endswith(('.', ',', ';', '?', '!')): raw = raw[:-1]
    valid = re.fullmatch(r'\$?(\d{1,5}(?:\.\d{1,2})?)', raw)
    if not valid or re.search(r'\d', tail) or not Decimal('0') <= Decimal(valid[1]) <= Decimal('10000'):
        issues.insert(0, 'Enter one exact hourly amount from 0 to 10000, with no grouping separators and at most two decimal places; I left the amount blank instead of shortening or choosing a number.')
        return fields, issues
    fields['amount'] = valid[1]
    if match[1]: fields['currency'] = match[1].upper()
    return fields, issues



def _read_pay(employee, message, today):
    """Read saved rate history only. No payroll inference or pay proposal."""
    low=message.casefold().replace('’',"'")
    history=deepcopy(employee.get('pay_history',[]))
    result={'employee_id':employee['id'],'expected_revision':employee['revision'],
            'kind':'rate','as_of_date':today,'history':history,'rate':None}
    def held(message):
        result.update(kind='clarification',message=message)
        return result
    if (re.search(r'\bpaid\b',low) and not re.search(r'\b(?:hourly|rate)\b',low)) or _NON_HOURLY_RATE.search(message) or re.search(r'\b(?:earn|earned|earnings|take.home|payroll|total pay|made|tax(?:es)?|net pay|overtime pay)\b',low):
        return held('I keep dated hourly rates, not salary or payroll totals. The saved history is beside our conversation; I have not converted amounts or calculated earnings.')
    dates=list(re.finditer(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)',low))
    relative=list(re.finditer(r'\b(?:today|yesterday|tomorrow)\b',low))
    remainder=low
    for m in sorted(dates+relative,key=lambda m:m.start(),reverse=True):remainder=remainder[:m.start()]+remainder[m.end():]
    remainder=re.sub(r'(?<!\w)'+re.escape(employee['name'].casefold())+r'(?!\w)','',remainder)
    if len(dates)+len(relative)>1 or re.search(r'\b(?:weeks?|months?|years?|between|since|before|after|until|monday|tuesday|wednesday|thursday|friday|saturday|sunday|jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|june?|july?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b|\d',remainder):
        return held('Which date should I check? Use one YYYY-MM-DD date, today, yesterday or tomorrow. I have not substituted today’s rate for another period.')
    try:
        day=daily.day_key(dates[0][0]) if dates else (staff.date.fromisoformat(today)+staff.timedelta(days={'today':0,'yesterday':-1,'tomorrow':1}[relative[0][0]])).isoformat() if relative else today
    except (ValueError,OverflowError):
        return held('That date is not valid. Use one YYYY-MM-DD date so I can check the saved rate on that day.')
    result['as_of_date']=day
    if re.search(r'\b(?:should|would|could|if)\b',low):
        return held('I can show the recorded rates and dates. To propose a change, give the new hourly amount, currency and effective date; it will wait for your review.')
    rows=sorted(enumerate(history),key=lambda pair:(pair[1]['effective_date'],pair[0]))
    eligible=[row for _,row in rows if row['effective_date']<=day]
    if re.search(r'\b(?:last|latest|most recent)\s+(?:pay\s+)?(?:raise|increase)\b',low):
        result['kind']='last_raise'
        if len({row['currency'] for row in eligible})>1:
            return held('This history contains different currencies. I have not compared them to identify a raise; each exact entry is shown separately.')
        raises=[]
        for prior,current in zip(eligible,eligible[1:]):
            if current['amount_minor']>prior['amount_minor']:raises.append((prior,current))
        if not raises:
            result['message']='No increase between recorded hourly rates is saved for '+employee['name']+' on or before '+day+'. A starting rate alone is not a recorded raise.'
        else:
            prior,current=raises[-1];result.update(rate=current,previous_rate=prior)
            result['message']=employee['name']+'’s latest recorded hourly increase on or before '+day+' took effect '+current['effective_date']+': '+current['currency']+' '+prior['amount']+' to '+current['amount']+' per hour. Reason: '+current['reason']+'.'
    elif re.search(r'\b(?:history|raises|previous rates|past rates)\b',low):
        result.update(kind='history',message=employee['name']+'’s saved hourly rate history is open, with each amount, currency, effective date and reason. No pay has been changed.')
    else:
        rate=rate_on(employee,day);result['rate']=rate
        result['message']=(employee['name']+' had '+rate['currency']+' '+rate['amount']+' per hour recorded for '+day+' (effective '+rate['effective_date']+').') if rate is not None else ('No hourly rate is recorded for '+employee['name']+' on '+day+'. This means no saved rate, not a zero rate.')
    return result

def converse(store, thread, message):
    from employee_comparison import respond as compare_employees
    comparison = compare_employees(store, message)
    if comparison is not None: return comparison
    low=message.casefold().replace('’',"'")
    previous=thread.get('messages',[])[-1] if thread.get('messages') else {}
    followup=re.fullmatch(r'(?:what about|and) (.+?)[?.! ]*',low.strip())
    prior=previous.get('pay_read') if previous.get('role')=='assistant' else None
    if followup and isinstance(prior,dict) and prior.get('kind') in ('rate','last_raise','history'):
        matches=[e for e in staff.book(store)['employees'] if e['name'].casefold().replace('’',"'")==followup[1]]
        if len(matches)!=1:
            return {'kind':'employee_pay','answer':'Use one full saved employee name for that pay-history follow-up. I have not reused the previous employee or changed pay.','navigation':{'screen':'employees','view':'pay','employee_id':None}}
        subject=matches[0]['name']
        message=('When was '+subject+"'s last raise" if prior['kind']=='last_raise' else 'Show '+subject+"'s pay history" if prior['kind']=='history' else 'What was '+subject+"'s hourly rate")+' on '+prior['as_of_date']+'?'
        low=message.casefold().replace('’',"'")
    if not re.search(r'\b(?:pay|paid|salary|salaries|wages?|raises?|hourly rates?|pay rates?|earn|earned|earnings|take.home)\b',low): return None
    if re.search(r'\b(?:invoice|supplier|vendor|bill|customer)\b',low): return None
    from employee_directory import summary
    data=summary(store)
    matches=[e for e in data['employees'] if re.search(r'(?<!\w)'+re.escape(e['name'].casefold())+r'(?!\w)',low)]
    employee=matches[0] if len(matches)==1 else None
    # Only an immediate, exact saved-person read may supply a pronoun for another read.
    previous=thread.get('messages',[])[-1] if thread.get('messages') else {}
    read_lead=bool(re.match(r'^(?:what|when|how much|show|list|tell me|did|has|was|is|should)\b',low.strip()))
    if not matches and read_lead and re.search(r"\b(?:his|her|their)\b",low):
        identity=(previous.get('navigation') or {}).get('employee_id') if previous.get('role')=='assistant' and previous.get('kind') in ('employee_directory','employee_pay') else None
        employee=next((e for e in data['employees'] if e['id']==identity),None)

    nav={'screen':'employees','view':'pay','employee_id':employee['id'] if employee else None}
    response={'kind':'employee_pay','navigation':nav,'employee_summary':data}
    if not data['employees']:
        response['answer']='You have 0 employees saved in '+data['team_name']+'. Add an employee or review an employee import first, then record an hourly rate.'
    elif not employee:
        response['answer']='Choose an employee in Pay, or name them here. I keep dated hourly rates and raise history. A rate changes only after you review its amount, currency and effective date and accept that exact proposal.'
    else:
        read_question=bool(re.match(r'^(?:what|when|how much|show|list|tell me|did|has|was|is|should)\b',low.strip()) or re.search(r'\b(?:pay history|raise history)\b',low))
        change=bool(re.search(r'\b(?:raise|change|set|increase|decrease|record|give|update)\b',low)) and not read_question
        if not change and not (not read_question and _NON_HOURLY_RATE.search(message)):
            read=_read_pay(employee,message,data['as_of_date'])
            response.update(pay_read=read,answer=read['message']+' The Pay view shows the saved entries; nothing has been changed.')
            return response
        rate=employee['pay_current']
        intro=employee['name']+(' has '+rate['currency']+' '+rate['amount']+' per hour recorded as of '+data['as_of_date']+'.' if rate else ' has no hourly rate effective as of '+data['as_of_date']+'.')
        form={'employee_id':employee['id'],'expected_revision':employee['revision']}
        issues=[]
        if change or _NON_HOURLY_RATE.search(message):
            fields,issues=requested_hourly_fields(message,employee)
            form.update(fields)
        thread['pay_form']=form
        response['pay_form']=deepcopy(form)
        response['answer']=intro+' The Pay view shows the dated history. '+(' '.join(issues)+' Nothing has been changed.' if issues else 'Review the proposed amount, explicit currency and effective date there; nothing has been changed.' if change else 'Choose Review rate change to record a starting rate or raise. No rate is guessed for a missing date.')
    return response
