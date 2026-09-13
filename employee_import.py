"""Reviewable employee import from selected CSV or labeled text; no inferred facts/OCR."""
from copy import deepcopy
import base64
import csv
import hashlib
import io
from pathlib import Path
import re
import uuid
import briefing
from briefing import digest, now
import staffing as staff
from employee_pay import transaction, rate_fields

FIELDS={'name','phone','email','roles','start_date','hourly_rate','currency'}
ALIASES={'employee':'name','employee name':'name','full name':'name','name':'name','phone':'phone','phone number':'phone',
    'email':'email','email address':'email','roles':'roles','role':'roles','job title':'roles','start date':'start_date',
    'hire date':'start_date','start_date':'start_date','hourly rate':'hourly_rate','hourly pay':'hourly_rate',
    'hourly_rate':'hourly_rate','currency':'currency'}

def field_name(name): return ALIASES.get(re.sub(r'\s+',' ',name.strip().casefold()))

def parse(filename, raw):
    ext=Path(filename).suffix.casefold()
    if ext not in ('.csv','.txt','.md','.pdf'):
        raise ValueError('Choose a CSV, UTF-8 text file or text PDF. Photos and scanned documents need OCR first; this edition cannot read their employee details.')
    lines=briefing.extract(filename,raw)
    text='\n'.join(row['text'] for row in lines)
    parsed=[];warnings=[]
    if ext=='.csv':
        reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
        if not reader.fieldnames or len(reader.fieldnames)>30: raise ValueError('Use a CSV with named columns, including Name.')
        mapped=[field_name(h) for h in reader.fieldnames]
        if 'name' not in mapped: raise ValueError('Include a Name column; I will not guess employee identities from unrelated text.')
        if len([m for m in mapped if m])!=len(set(m for m in mapped if m)): raise ValueError('Use only one column for each employee field.')
        unknown=[h for h,m in zip(reader.fieldnames,mapped) if not m]
        if unknown: warnings.append('Unimported columns: '+', '.join(unknown)+'. No availability or schedule is inferred from these columns.')
        for item in reader:
            if None in item: raise ValueError('A CSV row has more cells than its headers. Correct the CSV before importing.')
            fields={};evidence={}
            for header,mapped_field in zip(reader.fieldnames,mapped):
                if mapped_field and item.get(header) and item[header].strip():
                    fields[mapped_field]=item[header].strip();evidence[mapped_field]=item[header]
            if fields: parsed.append((fields,evidence))
    else:
        fields={};evidence={}
        for source in lines:
            match=re.fullmatch(r'([^:]{1,40})\s*:\s*(.*)',source['text'])
            if not match or not field_name(match[1]):
                warnings.append('Not mapped: '+source['text'][:150]);continue
            key=field_name(match[1]);value=match[2].strip()
            if key=='name' and fields: parsed.append((fields,evidence));fields={};evidence={}
            if key in fields: raise ValueError('An employee block repeats '+key+'. Start each employee block with Name:.')
            if value: fields[key]=value;evidence[key]=source['text']
        if fields: parsed.append((fields,evidence))
    if not parsed: raise ValueError('No employee rows found. Use CSV with a Name header, or text/PDF blocks beginning Name:, followed by Phone:, Email:, Role:, Start date:, Hourly rate: and Currency: where known.')
    if len(parsed)>200: raise ValueError('Review at most 200 employee rows in one import.')
    rows=[]
    for fields,evidence in parsed:
        if 'roles' in fields: fields['roles']=[r.strip() for r in re.split('[;|]',fields['roles']) if r.strip()]
        notes=[]
        if not fields.get('name'): notes.append('Name missing; supply it before selecting this row.')
        if not fields.get('start_date'): notes.append('Employment start date missing; supply YYYY-MM-DD before saving. No date was assumed.')
        if fields.get('hourly_rate') and not fields.get('currency'): notes.append('Hourly rate has no currency; choose the currency explicitly.')
        rows.append({'candidate_id':uuid.uuid4().hex[:12],'fields':fields,'evidence':evidence,'warnings':notes})
    return text,rows,list(dict.fromkeys(warnings))[:100]


def prepare(store, values):
    if not isinstance(values,dict) or set(values)-{'filename','base64','text'}: raise ValueError('Choose one employee document.')
    if ('base64' in values)==('text' in values): raise ValueError('Supply one file or one text input, not both.')
    filename=values.get('filename')
    if not isinstance(filename,str) or not 1<=len(filename)<=200: raise ValueError('Supply the selected filename.')
    try: raw=base64.b64decode(values['base64'],validate=True) if 'base64' in values else values['text'].encode('utf-8')
    except (ValueError,TypeError,AttributeError): raise ValueError('The selected file could not be read.')
    if len(raw)>briefing.MAX_BYTES: raise ValueError('Choose an employee document smaller than 5 MB.')
    text,rows,warnings=parse(filename,raw)
    def change(staged):
        existing={e['name'].casefold() for e in staff.book(staged)['employees']}
        for row in rows:
            if row['fields'].get('name','').casefold() in existing:
                row['warnings'].append('This employee name already exists. Deselect this row; use the existing employee to edit details.')
        p={'id':uuid.uuid4().hex[:12],'kind':'employee_import','created':now(),'team_id':staged.production_id,
           'roster_sha256':staff.roster_fingerprint(staged),'filename':Path(filename).name,
           'source_sha256':hashlib.sha256(raw).hexdigest(),'source_text':text,'rows':rows,'warnings':warnings,
           'availability_imported':False,'ocr_used':False,'pay_effective_date_rule':'An imported starting hourly rate uses the explicitly reviewed employment start date.'}
        p['sha256']=digest(p);p['status']='pending'
        staff.book(staged).setdefault('employee_imports',[]).append(p)
        return p
    return transaction(store,change)


def accept(store, values):
    if values.get('confirmation')!='YES': raise ValueError('Review the selected employee rows and type YES to save them.')
    rows=values.get('rows')
    if not isinstance(rows,list) or not 1<=len(rows)<=200: raise ValueError('Select at least one reviewed employee row.')
    def change(staged):
        p=next((p for p in staff.book(staged).get('employee_imports',[]) if p['id']==values.get('id')),None)
        if not p or p.get('status')!='pending' or p['team_id']!=staged.production_id: raise ValueError('Choose a pending employee import from this team.')
        if p['sha256']!=values.get('sha256') or digest({k:v for k,v in p.items() if k not in ('sha256','status')})!=p['sha256']:
            raise ValueError('The source import proposal changed. Prepare and review it again.')
        if p['roster_sha256']!=staff.roster_fingerprint(staged): raise ValueError('The team changed after this import was prepared. Review a fresh import to avoid overwriting employees.')
        source={r['candidate_id']:r for r in p['rows']};seen=set();created=[]
        for row in rows:
            if not isinstance(row,dict) or set(row)!={'candidate_id','fields'} or row['candidate_id'] not in source or row['candidate_id'] in seen:
                raise ValueError('Select distinct rows from the exact reviewed import.')
            seen.add(row['candidate_id']);fields=row['fields']
            if not isinstance(fields,dict) or set(fields)-FIELDS: raise ValueError('Use only the displayed employee fields; schedules and availability are separate.')
            ordinary={k:v for k,v in fields.items() if k not in ('hourly_rate','currency')}
            employee=staff.save_employee(staged,ordinary)
            actual=staff.employee(staged,employee['id'])
            if fields.get('hourly_rate') not in (None,''):
                rate=rate_fields(actual,fields['hourly_rate'],fields.get('currency'),actual['start_date'],'Starting rate from reviewed employee import')
                actual.setdefault('pay_history',[]).append({**rate,'id':uuid.uuid4().hex[:12],'recorded_at':now(),'import_id':p['id'],'source_sha256':p['source_sha256']})
            elif fields.get('currency'): raise ValueError('Currency without an hourly rate is incomplete; remove it or supply the reviewed rate.')
            actual['import_source']={'import_id':p['id'],'candidate_id':row['candidate_id'],'filename':p['filename'],
                'source_sha256':p['source_sha256'],'evidence':deepcopy(source[row['candidate_id']]['evidence']),
                'extracted_fields':deepcopy(source[row['candidate_id']]['fields']), 'reviewed_fields':deepcopy(fields)}
            actual['history'].append({'at':now(),'operation':'employee_import_reviewed','source':deepcopy(actual['import_source'])})
            created.append(deepcopy(actual))
        p.update(status='accepted',accepted_at=now(),accepted_employee_ids=[e['id'] for e in created],reviewed_rows=deepcopy(rows))
        return {'saved':True,'employees':created,'source_sha256':p['source_sha256'],
                'answer':'Saved '+str(len(created))+' reviewed employees. Contact and pay fields came from the displayed source or your edits. Availability is still not provided; no schedule was created.'}
    return transaction(store,change)
