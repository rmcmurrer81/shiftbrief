"""Read-only employer questions, with explicit evidence gaps and contextual follow-ups."""
from copy import deepcopy
import re
import employee_directory


def respond(store, thread, message):
    text = re.sub(r'\s+', ' ', message.strip().casefold().replace('’', "'"))
    # Leave a name/date being entered in an existing form to that form's workflow.
    if thread.get('staffing_pending') and not re.search(r'\b(?:who|which|how|what|show|compare)\b', text):
        return None
    read = bool(re.search(r'\b(?:who|which|how|what|show|compare|rank|tell me|can you|need to|want to)\b', text))
    attendance = read and bool(re.search(r'\b(?:late|lateness|tardy|tardiness|punctual|punctuality|attendance|no.?shows?|absen(?:t|ces?)|miss(?:ed|es) shifts?)\b', text))
    decision = read and bool(re.search(r'\b(?:fire|firing|let (?:someone|somebody|an? employee|people|staff) go|lay ?off|layoffs|reduce (?:staff|headcount)|downsiz\w*|cut (?:staff|headcount))\b', text))
    performance = read and bool(re.search(r'\b(?:best|worst|poor|performance|underperform\w*|reliable|reliability|productive|productivity)\b', text))
    costs = read and bool(re.search(r'\b(?:payroll|(?:staff|staffing|labor|labour) costs?|(?:cut|reduce|lower|save) (?:costs|money))\b', text))
    kind = 'attendance' if attendance else 'staffing_decision' if decision else 'performance' if performance else 'costs' if costs else None
    history = thread.get('messages', [])
    previous = next((m.get('employer_insight') for m in reversed(history) if m.get('role') == 'assistant'), None)
    previous = previous if isinstance(previous, dict) and previous.get('team_id') == store.production_id else None
    if kind is None and previous:
        short = text.strip(' .!?')
        if re.fullmatch(r'(?:the |their |about )?(?:performance|attendance|lateness|punctuality)', short):
            kind = 'attendance' if short.split()[-1] != 'performance' else 'performance'
        elif re.fullmatch(r'(?:(?:i need|i want|it is|it\'s|its) (?:to )?)?(?:(?:reduce|cut|save|lower) )?(?:staff |staffing |labor |labour |payroll )?(?:costs?|money|budget)', short):
            kind = 'costs'
        elif short in ('what do you have', 'what can you compare', 'what can you show me', 'tell me more'):
            kind = previous['topic']
        elif short in ('yes', 'please do', 'show me', 'compare them'):
            kind = 'costs' if previous['topic'] == 'costs' else previous['topic']
    if kind is None:
        return None

    if kind == 'attendance':
        import work_history
        read=work_history.work_read(store, 'show team attendance '+text, late=True, employee_ids=[])
        if re.search(r'\b(?:punctual|punctuality)\b',text):read['summary']='I can compare recorded late-arrival counts and the number of comparable starts, but those counts alone do not establish who is most punctual across unequal or missing records. '+read['summary']
        read['summary']+=' Recorded starts can show lateness; missing arrivals, absences and explanations are not inferred. This is not a performance ranking.'
        return {'kind':'work_history','answer':read['summary'],'navigation':{'screen':'comparison','view':'work_history'},'work_history':read}

    summary = employee_directory.summary(store)
    hours = employee_directory.hours(store)
    import staffing, shift_schedule
    hours['source_revisions'] = [{'date':day,'sha256':(shift_schedule.latest(store,day) or {}).get('sha256')} for day in staffing.days(hours['week_start'])]
    title = {'attendance':'Attendance & punctuality', 'performance':'Performance review',
             'staffing_decision':'Review staffing options', 'costs':'Staffing costs'}[kind]
    if kind == 'attendance':
        answer = ("I can’t tell who is late most often yet: this team has saved planned shifts, but no clock-in or attendance records. "
                  "Scheduled hours don’t tell us who arrived late. The center shows what is available and what would be needed for a fair comparison.")
        question = 'Would you like to compare the saved planned hours or review an employee’s record?'
        available = 'Planned hours and employee records'
        missing = ['Scheduled start matched to actual arrival', 'Dated absences and no-shows', 'Corrections and recorded explanations']
    elif kind == 'performance':
        answer = ("I don’t have documented performance reviews or results for this team, so I can’t rank the best or worst employee. "
                  "I can compare saved hours, hourly rates and time on the team. None of those alone measures performance.")
        question = 'Are you looking at staffing costs, coverage or a particular documented concern?'
        available = 'Hours, hourly rates and time on the team'
        missing = ['Relevant responsibilities and expectations', 'Dated, documented results', 'Comparable review period for each employee']
    elif kind == 'staffing_decision':
        answer = ("I can help you review the situation. There isn’t evidence here to recommend firing a particular person. "
                  "The saved records can help compare hours, hourly rates and coverage; recorded work is separate from documented performance and the reasons for a staffing decision.")
        question = 'Is the reason reducing staffing costs, a coverage problem or a performance concern?'
        available = 'Staffing and coverage comparisons'
        missing = ['Reason for the proposed change', 'Coverage needed after a change', 'Relevant documented performance or attendance, if that is the concern']
    else:
        answer = ("Let’s start with the saved hourly rates and planned hours. I can show those comparisons, but I won’t treat them as actual earnings or combine different currencies. "
                  "We can then look for schedule changes that preserve the coverage you need.")
        question = 'Would you like hourly rates, planned hours or the current week’s coverage first?'
        available = 'Recorded rates and planned hours'
        missing = ['Target saving and date range', 'Actual paid hours for an actual payroll total', 'Coverage constraints to preserve']
    insight = {'schema':'shiftbrief.employer-insight.v1','topic':kind,'team_id':store.production_id,
               'title':title,'summary':answer,'question':question,'available_label':available,'missing':missing,
               'attendance_available':False,'performance_available':False,'hours':hours,
               'employee_revisions':[{k:deepcopy(e.get(k)) for k in ('id','revision')} for e in summary['employees']]}
    return {'kind':'employer_insight','answer':answer+'\n\n'+question,
            'navigation':{'screen':'employees','view':'comparison','employee_id':None},
            'employee_summary':summary,'employer_insight':insight}
