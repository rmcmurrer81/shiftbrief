"""Source-backed local Sarah workflow. No model, provider key or network call.

New ShiftBrief implementation, September 7 2026. Uses literal source changes,
explicit field comparisons and bounded retrieval; unsupported questions abstain.
"""
from copy import deepcopy
import re
import time
import uuid

from briefing import citation_index, digest, now, update_packet

MODE = 'sarah_local'
LABEL = 'Sarah local evidence engine'
STOP = set('a an the what which who where when how is are was were did does do has have please tell me show about of to for in on with and or it that this changed change changes current latest source sources documents document'.split())


def _terms(text):
    words=set(re.findall(r'[a-z0-9]{2,}', text.casefold())) - STOP
    return {('access' if w in ('accessibility','accessible') else w) for w in words}


def _focus_terms(text):
    match=re.search(r'\b(?:about|focus on|regarding)\s+(.+)',text,re.I)
    return _terms(match[1]) if match else set()


def _bounded(message):
    if not isinstance(message, str) or not message.strip() or len(message) > 2000:
        raise ValueError('Use a question or instruction of 1 to 2,000 characters.')
    return message.strip()


def _check_snapshot(snapshot):
    if not snapshot['documents']:
        raise ValueError('Add a document before asking about its evidence.')
    if len(snapshot['documents']) > 8 or sum(len(l['text']) for d in snapshot['documents'] for r in d['revisions'] for l in r['lines']) > 36000:
        raise ValueError('Choose a focused production with at most eight documents and 36,000 characters in their latest two revisions.')


def _evidence(doc, rev, line):
    return {'ref': f"{doc['id']}:r{rev['number']}:L{line['line']}", 'quote': line['text']}


def _field(text):
    # Only explicit labelled fields; no guessed entity, date or task state.
    m = re.match(r'^\s*([^:]{2,70}):\s*(.+?)\s*$', text)
    return (re.sub(r'\s+', ' ', m[1]).strip(), m[2]) if m else (None, None)


def analyze(snapshot, focus=''):
    _check_snapshot(snapshot)
    findings, decisions, questions, seen = [], [], [], set()
    all_current = [(doc, doc['revisions'][-1], line) for doc in snapshot['documents'] for line in doc['revisions'][-1]['lines']]
    def add(text, evidence, task=None):
        key = digest([text, evidence])
        if key in seen: return
        seen.add(key)
        findings.append({'text': text, 'evidence': evidence})
        if task: decisions.append({'text': task, 'evidence': evidence})
    changes = 0
    for doc in snapshot['documents']:
        revisions = doc['revisions']
        if len(revisions) < 2: continue
        before, after = revisions
        for block in update_packet(doc)['changes']:
            old_lines = before['lines'][block['before_start']-1:block['before_start']-1+len(block['before'])]
            new_lines = after['lines'][block['after_start']-1:block['after_start']-1+len(block['after'])]
            for i in range(max(len(old_lines), len(new_lines))):
                old = old_lines[i] if i < len(old_lines) else None
                new = new_lines[i] if i < len(new_lines) else None
                evidence = ([_evidence(doc,before,old)] if old else []) + ([_evidence(doc,after,new)] if new else [])
                if any(len(x['quote']) > 380 for x in evidence):
                    # Quotes remain exact excerpts; complete originals are available by citation.
                    evidence = [{**x, 'quote': x['quote'][:380]} for x in evidence]
                changes += 1
                if old and new:
                    label, old_value = _field(old['text']); new_label, new_value = _field(new['text'])
                    add(f"{doc['title']}: “{evidence[0]['quote']}” changed to “{evidence[-1]['quote']}”.", evidence,
                        f"Review the revised {new_label or 'instruction'} in {doc['title']} with the responsible person before relying on it.")
                    if label and new_label and label.casefold() == new_label.casefold() and old_value != new_value and len(old_value) >= 3:
                        pattern = re.compile(r'(?<!\w)' + re.escape(old_value) + r'(?!\w)', re.I)
                        for other, rev, line in all_current:
                            if other['id'] != doc['id'] and pattern.search(line['text']):
                                refs = [evidence[0], evidence[-1], _evidence(other,rev,line)]
                                add(f"{other['title']} still mentions the earlier value “{old_value[:180]}” after {doc['title']} recorded “{new_value[:180]}”. This is a possible mismatch; the newer document alone does not establish approval.", refs,
                                    f"Confirm whether {other['title']} should use the revised {new_label.lower()}; keep the earlier instruction visible until resolved.")
                elif new:
                    add(f"{doc['title']} added: “{evidence[0]['quote']}”.", evidence, f"Review the added instruction in {doc['title']} before the next shift.")
                else:
                    add(f"{doc['title']} removed: “{evidence[0]['quote']}”.", evidence, f"Confirm the removed instruction in {doc['title']} is intentionally retired.")
    groups = {}
    for doc, rev, line in all_current:
        label, value = _field(line['text'])
        if label and len(value) < 300:
            groups.setdefault(label.casefold(), []).append((doc,rev,line,label,value))
        if re.search(r'\b(?:not (?:yet )?(?:confirmed|received|sent|approved|complete|completed)|unconfirmed|pending|awaiting|proposed|tbd|to be confirmed)\b', line['text'], re.I):
            exact = line['text'][:380]
            add(f"{doc['title']} explicitly records an unresolved state: “{exact}”.", [{**_evidence(doc,rev,line), 'quote': exact}], f"Ask the source owner for the missing confirmation recorded in {doc['title']}; no completion is established by this line.")
    for rows in groups.values():
        if len({d['id'] for d,_,_,_,_ in rows}) > 1 and len({v.casefold() for *_,v in rows}) > 1:
            refs = [_evidence(d,r,l) for d,r,l,_,_ in rows[:4]]
            add(f"Current documents list different values for “{rows[0][3]}”. Compare the quoted scope and obtain the approved value; these may describe different activities.", refs, f"Resolve which “{rows[0][3]}” value applies to this handoff before the next person acts.")
    if not findings:
        for doc, rev, line in all_current[:6]:
            add(f"Current evidence in {doc['title']}: “{line['text'][:380]}”.", [{**_evidence(doc,rev,line), 'quote':line['text'][:380]}])
        questions.append('No revision difference was found in the selected source snapshot. Add an earlier version if a comparison is needed.')
    if not findings:
        raise ValueError('The documents contain no usable source lines.')
    wanted = _terms(focus)
    generic = _terms('Summarize production changes flag conflicting timing location details need decision prepare next shift handoff short important practical unconfirmed accessibility mismatched instructions assume later plan approved task completed')
    focused = _focus_terms(focus) or (wanted - generic)
    if focused:
        findings.sort(key=lambda row: -len(focused & _terms(row['text'] + ' '.join(c['quote'] for c in row['evidence']))))
        decisions.sort(key=lambda row: -len(focused & _terms(row['text'] + ' '.join(c['quote'] for c in row['evidence']))))
    omitted = max(0, len(findings)-12)
    if omitted: questions.append(f'{omitted} additional source-derived findings are outside this handoff. Review the full comparisons or prepare a handoff focused on a specific topic.')
    questions.append('Which revised instructions have actually been approved? A file timestamp is not an approval receipt.')
    return {'findings':findings[:12], 'decisions':decisions[:12], 'open_questions':questions[:8], 'change_count':changes, 'total_findings':len(findings)}


def run_local(store, instruction='Prepare the next-shift handoff.', progress=None):
    instruction = _bounded(instruction)
    started=time.monotonic(); snapshot=store.snapshot(); trace=[]
    def report(tool, detail):
        trace.append({'tool':tool,'detail':detail})
        if progress: progress(deepcopy(trace))
    report('read_source_snapshot', 'Read only this production’s latest two saved revisions.')
    result=analyze(snapshot,instruction)
    report('compare_literal_evidence', f"Computed {result['change_count']} changed lines and {result['total_findings']} evidence-derived findings. No language model was called.")
    report('save_validated_handoff', 'Rechecked exact source quotes and snapshot before saving the handoff and unchecked decisions.')
    record=store.save_briefing(snapshot, 'Source changes and next-shift review', result['findings'], result['decisions'],result['open_questions'],trace,model='none',framework=LABEL,interpretation=False)
    with store.lock:
        record['elapsed_seconds']=round(time.monotonic()-started,3)
        record['request']=instruction
        store.save()
    return record


def _thread(store):
    return store.data.setdefault('assistant_threads',{}).setdefault(store.production_id,{'messages':[],'pending':None,'last_refs':[]})


def _public_evidence(snapshot, rows):
    index=citation_index(snapshot)
    return [{'ref':x['ref'],'quote':x['quote'],**index[x['ref']]} for x in rows]


def ask(store, message, briefing_id=None):
    message=_bounded(message)
    with store.lock:
        thread=_thread(store)
        if len(thread['messages']) >= 400:
            raise ValueError('This team has 200 saved conversation turns. Export its handoffs and start a new team workspace.')
        snapshot=store.snapshot(); lower=message.casefold(); response={'answer':'','evidence':[],'kind':'answer','snapshot_sha256':snapshot['sha256']}
        proposal=None
        briefs=store.view()['briefings']; brief=next((b for b in briefs if b['id']==briefing_id),None) if briefing_id else (briefs[-1] if briefs else None)
        mark=re.fullmatch(r'(?:mark|set)\s+(?:decision|task)\s+(\d+)\s+(done|complete|completed|open|not done)',lower.strip(' .!'))
        revise=re.fullmatch(r'(?:revise|change|edit)\s+(?:decision|task)\s+(\d+)\s*:\s*(.+)',message,re.I|re.S)
        note = re.fullmatch(r'(?:save|add|write|record)\s+(?:an?\s+)?(?:note|update)(?:\s+(?:called|titled)\s+([^:\n]{1,100}))?\s*:\s*(.+)', message, re.I | re.S)
        greeting = re.fullmatch(r'(?:hi|hello|hey|good morning|good evening|thanks|thank you)[!. ]*', lower)
        introduction = re.search(r'\b(?:tell me about yourself|who are you|what are you|what can you do|how (?:do|can) (?:i|we) (?:use|start)|where (?:do|should|can) (?:we|i) (?:start|begin)|help me (?:start|begin)|get started|help)\b', lower)
        source_read=bool(re.search(r'\b(?:sources?|documents?|evidence|quot(?:e|es|ation)|citations?|handbooks?|polic(?:y|ies)|memos?|notes?)\b|\baccording to\b',lower) and (message.rstrip().endswith('?') or re.match(r'^(?:what|where|which|who|when|how|show|find|quote|explain|read|tell me|help|according to)\b',lower.strip())))
        if source_read: proposal=thread.get('pending')
        from staffing_chat import converse as staffing_converse, import_request
        try: staffing_response = None if note or (source_read and not import_request(message)) else staffing_converse(store,thread,message)
        except ValueError as exc: staffing_response = {'kind':'staffing_clarification','answer':str(exc)}
        if staffing_response:
            response.update(staffing_response)
        elif note:
            title = (note[1] or 'My team note').strip()
            content = note[2].strip()
            proposal = {'id': uuid.uuid4().hex[:12], 'operation': 'save_source_note', 'title': title, 'text': content, 'snapshot_sha256': snapshot['sha256'], 'production_id': store.production_id}
            proposal['sha256'] = digest(proposal)
            response.update(kind='proposal', answer='Here is your first source note, using only your words:\n' + title + '\n' + content + '\nReview it and confirm YES to save it as a team document. After that, I can compare later updates and prepare a handoff.')
        elif (greeting or introduction) and not source_read:
            title = next((p['title'] for p in store.data['productions'] if p['id'] == store.production_id), 'this production')
            response['answer'] = ('Hi, I’m Sarah. I help your store, office or team plan employee shifts, lunch coverage and handoffs. Say “I hired a new employee” to add a person and their dated availability, then ask me to suggest a week. We review every suggested schedule before saving it. I also keep source notes and compare updates.\n\n' + ('Let’s start with ' + title + '. Tell me the first real detail you want the next shift to know. You can say “Save a note: …” in your own words, or attach a employee list, schedule or existing note. I’ll show the note for review before saving; you do not need a document ready to talk with me.' if not snapshot['documents'] else 'You already have ' + str(len(snapshot['documents'])) + ' source documents here. We can look at a specific topic, compare an updated version, or prepare the next handoff. What part should we work through first?'))
            response['kind'] = 'onboarding'
        elif not snapshot['documents']:
            thread['onboarding_context'] = message
            proposal=thread.get('pending')
            source_request=re.search(r'\b(?:sources?|documents?|evidence|quot(?:e|es|ation)|citations?|handbooks?|polic(?:y|ies)|memos?|notes?)\b|\baccording to\b|\bwhat changed\b', lower)
            if source_request:
                response.update(kind='answer', answer='There is no source document saved in this team yet, so I cannot answer from source evidence. Open Sources to add the document or paste its exact text, then ask about it. No approval, policy, date or completion has been inferred.')
            else:
                from employee_directory import summary as employee_summary
                data=employee_summary(store)
                response.update(kind='onboarding', employee_summary=data, answer='I have not matched that request to a supported action. '+data['team_name']+' has '+str(data['total_records'])+' employees saved ('+str(data['active_count'])+' active). Open Employees to add or import people, review contacts, or record hourly pay. Open Settings for business hours and coverage; open Schedule to review shifts, availability and lunch breaks. You can say “employees”, “I hired a new employee”, or “suggest next week”. Changes are reviewed before saving; no employee or schedule was changed.')
        elif mark or revise:
            match=mark or revise; number=int(match[1]); position=number-1
            if not brief or not 0<=position<len(brief['decisions']):
                response['answer']='Choose a decision number from the selected saved handoff. No checklist was changed.'
            elif brief['outdated']:
                response['answer']='This handoff is outdated. Prepare a current handoff before changing its decisions.'
            else:
                target=brief['decisions'][position]
                proposal={'id':uuid.uuid4().hex[:12],'snapshot_sha256':snapshot['sha256'],'briefing_id':brief['id'],'decision_id':target['id'],'decision_number':number,'old_text':target['text'],'operation':'set_done' if mark else 'revise_text','done':mark[2] in ('done','complete','completed') if mark else None,'new_text':revise[2].strip() if revise else None}
                if proposal['new_text'] and len(proposal['new_text'])>800: raise ValueError('Keep a revised decision under 800 characters.')
                if revise:
                    query=_terms(proposal['new_text'])
                    candidates=[]
                    for doc in snapshot['documents']:
                        rev=doc['revisions'][-1]
                        for line in rev['lines']:
                            score=len(query&_terms(line['text']))
                            if score: candidates.append((score,doc,rev,line))
                    candidates.sort(key=lambda x:-x[0])
                    if not candidates:
                        raise ValueError('This new decision has no matching current source line. Add its evidence first or revise the wording to name a supported topic.')
                    best=candidates[0][0]
                    proposal['new_evidence']=_public_evidence(snapshot,[_evidence(doc,rev,line) for score,doc,rev,line in candidates if score==best][:4])
                proposal['old_done']=target['done']
                proposal['sha256']=digest(proposal)
                response.update(kind='proposal',answer=f"Review decision {number}: {target['text']}\n"+(f"Proposed status: {'done' if proposal['done'] else 'open'}." if mark else 'Proposed owner wording: '+proposal['new_text'])+' Confirm YES to save this local checklist change. This sends no message and does not prove an external task occurred.',evidence=proposal.get('new_evidence',target['evidence']))
        elif re.search(r'\b(?:send|email|call|book|pay|publish|delete)\b',lower) and not lower.startswith(('what','where','when','who','show','find','did','has','is')):
            response['answer']='I cannot perform that external action. I can locate its source evidence, prepare a handoff, or propose a local checklist change for you to review.'
        elif re.search(r'\b(?:what changed|changes|differences|mismatch|conflict|unconfirmed|pending)\b',lower):
            result=analyze(snapshot,message)
            focus=_focus_terms(message)
            selected=([row for row in result['findings'] if focus&_terms(row['text']+' '.join(c['quote'] for c in row['evidence']))] if focus else result['findings'])[:6]
            if not selected:
                response['answer']='No changed or unresolved source line matched that topic. Name the field or document, or ask to show its current source.'
            if selected: response['answer']='\n\n'.join(f"{i}. {r['text']}" for i,r in enumerate(selected,1))
            refs={x['ref']:x for row in selected for x in row['evidence']}
            response['evidence']=_public_evidence(snapshot,list(refs.values()))
            if len(result['findings'])>6: response['answer']+='\n\nPrepare a saved handoff for the full checklist; all original comparisons remain available.'
        elif re.search(r'\b(?:next steps|next actions|checklist|decisions|tasks|what should .* do|what needs doing)\b',lower):
            if not brief: response['answer']='Prepare a handoff first to create the saved, source-backed checklist.'
            else:
                response['answer']=('OUTDATED source snapshot; prepare a new handoff.\n' if brief['outdated'] else '')+'\n'.join(f"{i}. [{'done' if d['done'] else 'open'}] {d['text']}" for i,d in enumerate(brief['decisions'],1))
                response['evidence']=[c for d in brief['decisions'] for c in d['evidence']]
        elif re.search(r'\b(?:help|what can you do|what are you)\b',lower):
            response['answer']='Sarah’s local evidence mode compares revisions, shows exact source lines, tracks unresolved statuses, and prepares saved handoffs. Ask about a topic, what changed, or next steps. “Mark decision 2 done” and “Revise decision 2: …” prepare changes for explicit review. I use bounded rules and retrieval, not a general language model.'
        else:
            _check_snapshot(snapshot)
            query=_terms(message)
            if lower.strip(' ?.!') in ('where is that from','show that source','show the source','why','what about that') and thread.get('last_refs'):
                index=citation_index(snapshot)
                rows=[{'ref':r,'quote':index[r]['text']} for r in thread['last_refs'] if r in index]
            else:
                candidates=[]
                for doc in snapshot['documents']:
                    rev=doc['revisions'][-1]
                    for line in rev['lines']:
                        score=len(query&_terms(line['text']+' '+doc['title']))
                        if score: candidates.append((score,doc,rev,line))
                candidates.sort(key=lambda x:-x[0])
                rows=[_evidence(doc,rev,line) for score,doc,rev,line in candidates if score==candidates[0][0]][:8] if candidates else []
            if not rows:
                response['answer']='I do not have source evidence that answers this question. Name the document or the exact topic, or add the missing source. I have not guessed a date, person, approval or completion.'
            else:
                response['answer']='These are the matching saved source statements; they do not independently establish approval:\n'+'\n'.join('• '+r['quote'] for r in rows)
                response['evidence']=_public_evidence(snapshot,rows)
        if staffing_response and response['kind'] in ('employee_directory','employee_pay','employee_import','employee_comparison','employer_insight','work_history'):
            proposal=thread.get('pending')
        thread['pending']=proposal
        thread['last_refs']=list(dict.fromkeys(c['ref'] for c in response['evidence']))
        public_extra={k:deepcopy(response[k]) for k in ('navigation','employee_summary','hours_chart','pay_form','pay_read','availability_read','employee_comparison','employer_insight','work_history') if k in response}
        if 'navigation' in response: thread['navigation']=deepcopy(response['navigation'])
        thread['messages'].extend([{'role':'user','text':message,'created':now()},{'role':'assistant','text':response['answer'],'evidence':response['evidence'],'kind':response['kind'],'snapshot_sha256':snapshot['sha256'],'created':now(),**public_extra}])
        store.save()
        return {**response,'proposal':deepcopy(proposal)}


def confirm(store, proposal_id, proposal_sha, confirmation):
    if confirmation!='YES': raise ValueError('Type YES to confirm this exact local checklist change.')
    with store.lock:
        thread=_thread(store); proposal=thread.get('pending')
        if not proposal or proposal.get('id')!=proposal_id or proposal.get('sha256')!=proposal_sha or digest({k:v for k,v in proposal.items() if k!='sha256'})!=proposal_sha:
            raise ValueError('This proposal is no longer current. Ask for the change again.')
        if proposal['snapshot_sha256']!=store.snapshot()['sha256']:
            raise ValueError('Documents changed after this proposal. Prepare a current handoff and review the change again.')
        if proposal['operation'] == 'save_source_note':
            if proposal.get('production_id') != store.production_id:
                raise ValueError('Return to the production where this note was drafted.')
            result = store.import_document(proposal['title'], 'owner-note.txt', proposal['text'].encode('utf-8'))
            doc = store.document(result['document_id'])
            doc['revisions'][-1]['origin'] = 'owner_words_confirmed_in_sarah_chat'
            thread['pending'] = None
            answer = 'Saved your reviewed words as a source document. You can add its next revision, ask about it, or prepare a handoff. No dates, people or completion claims were added.'
            thread['messages'].append({'role': 'assistant', 'text': answer, 'kind': 'confirmed_source_note', 'created': now()})
            store.save()
            return {'saved': True, 'answer': answer, 'document_id': result['document_id']}
        brief=next((b for b in store.data['briefings'] if b['id']==proposal['briefing_id'] and b.get('production_id','main')==store.production_id),None)
        decision=next((d for d in brief['decisions'] if d['id']==proposal['decision_id']),None) if brief else None
        if not decision or (decision['text']!=proposal['old_text'] or decision['done']!=proposal['old_done']): raise ValueError('The decision changed. Review a fresh proposal.')
        if proposal['operation']=='set_done': store.set_decision(brief['id'],decision['id'],proposal['done'])
        else:
            decision.setdefault('owner_revisions',[]).append({'previous_text':decision['text'],'text':proposal['new_text'],'created':now(),'kind':'owner_wording','previous_evidence':deepcopy(decision['evidence'])})
            decision['text']=proposal['new_text'];decision['evidence']=deepcopy(proposal['new_evidence']);decision['owner_edited']=True;decision['done']=False
        thread['pending']=None
        message='Saved the reviewed local checklist change. Source evidence and revision history are preserved; no external action was performed.'
        thread['messages'].append({'role':'assistant','text':message,'created':now(),'kind':'confirmed_change'})
        store.save()
        return {'saved':True,'answer':message,'briefing_id':brief['id']}
