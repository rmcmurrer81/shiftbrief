"""Read-only departure scenarios over saved dated plans, never assignments."""
from copy import deepcopy
from datetime import date
from types import SimpleNamespace
import staffing as staff
import staffing_constraints as rules
import shift_schedule as daily
import operating_hours

SCHEMA = 'shiftbrief.departure-coverage.v1'


def check_context(store, identity, expected_team_id, expected_revision):
    """Caller holds the Store lock through any subsequent employee write."""
    if expected_team_id != store.production_id:
        raise ValueError('The selected business changed. Reopen this employee before continuing.')
    rows = store.data.get('staffing', {}).get(store.production_id, {}).get('employees', [])
    person = next((e for e in rows if e['id'] == identity), None)
    if person is None:
        raise ValueError('Choose a saved employee in this business.')
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision != person.get('revision', 1):
        raise ValueError('Employee details changed. Reopen this employee before continuing.')
    return person


def _matches(row, person):
    # A stored ID is authoritative; legacy names are considered only without one.
    return row.get('employee_id') == person['id'] if row.get('employee_id') else str(row.get('employee', row.get('name', ''))).casefold() == person['name'].casefold()


def _subtract(intervals, cuts):
    result = list(intervals)
    for c, d in sorted(cuts):
        result = [(x, y) for a, b in result for x, y in ((a, min(b, c)), (max(a, d), b)) if x < y]
    return result


def _intersection(left, right):
    rows = sorted((max(a, c), min(b, d)) for a, b in left for c, d in right if max(a, c) < min(b, d))
    merged = []
    for a, b in rows:
        if merged and a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return merged


def _minutes(intervals):
    return sum(b-a for a, b in intervals)


def _rows(intervals):
    return [{'start': a, 'end': b} for a, b in intervals]


def _policy(snapshot, week):
    candidates = [p for p in staff.book(snapshot).get('proposals', []) if p.get('kind') == 'week' and p.get('week_start') == week]
    latest = candidates[-1] if candidates else None
    policy = (latest or {}).get('payload', {}).get('constraints')
    if not policy:
        return {'constraints': []}, None
    # Revalidate the source-bound literal restriction using existing rules. Select
    # its week only in this detached read snapshot, never the user's workspace.
    staff.book(snapshot)['selected_week'] = week
    try:
        return rules.verify_policy(snapshot, week, policy), None
    except (ValueError, KeyError, TypeError) as exc:
        return None, 'Saved weekly restrictions need review before replacement suggestions: '+str(exc)


def analyze(store, employee_id, first_unavailable_date, *, today=None):
    key = daily.day_key(first_unavailable_date)
    as_of = (today or date.today()).isoformat()
    coverage_from = max(key, as_of)
    with store.lock:
        snapshot = SimpleNamespace(data=deepcopy(store.data), production_id=store.production_id)
    source_sha = staff.stamp({'staffing': snapshot.data.get('staffing', {}).get(snapshot.production_id),
                             'schedules': snapshot.data.get('shift_schedules', {}).get(snapshot.production_id)})
    people = staff.book(snapshot)['employees']
    person = next((e for e in people if e['id'] == employee_id), None)
    if person is None:
        raise ValueError('Choose one saved employee by ID in this business.')
    if key < person['start_date']:
        raise ValueError('The first unavailable date precedes this employee’s start date.')
    data = daily.book(snapshot)
    saved = sorted(d for d, value in data['days'].items() if d >= coverage_from and value.get('revisions'))
    plans = {d: daily.latest(snapshot, d) for d in saved}
    threshold = staff.book(snapshot)['settings']['overtime_hours']*60
    warnings = ['These are independent call-list alternatives, not a combined assignment plan. Recalculate after any schedule or employee change.',
                'Off schedule means no saved shift that date, not availability marked Off. Unknown availability is never assumed.',
                'Recorded breaks are excluded from planned work and retained in options; confirm breaks, preferences and employee agreement before editing shifts.']
    slots = []; totals = {}; span_totals = {}; policies = {}
    for day, plan in plans.items():
        daily.validate(plan)
        absent = [s for s in plan['shifts'] if _matches(s, person)]
        if not absent:
            continue
        week = staff.current_sunday(date.fromisoformat(day))
        if week not in totals:
            totals[week] = staff.hours_by_employee(snapshot, week)
            span_totals[week] = {e['id']: 0 for e in people}
            for d in staff.days(week):
                for s in (daily.latest(snapshot, d) or {}).get('shifts', []):
                    for e in people:
                        if _matches(s, e): span_totals[week][e['id']] += s['end']-s['start']
            policies[week] = _policy(snapshot, week)
        policy, policy_error = policies[week]
        windows = operating_hours.resolve(snapshot, day)['coverage_windows']
        confirmed = staff.book(snapshot)['settings'].get('hours_confirmed') or staff.book(snapshot)['settings'].get('operating_hours')
        for shift in absent:
            a, b = shift['start'], shift['end']; role = shift.get('role') or 'Team'
            breaks = [(r['start'], r['end']) for r in shift.get('breaks', [])]
            work = _subtract([(a, b)], breaks)
            slot = {'date': day, 'shift_id': shift['id'], 'source_revision': plan.get('number'), 'source_sha256': staff.stamp(plan),
                    'start': a, 'end': b, 'role': role, 'gross_minutes': b-a, 'break_minutes': _minutes(breaks),
                    'net_planned_minutes': _minutes(work), 'breaks': deepcopy(shift.get('breaks', [])), 'work_intervals': _rows(work), 'choices': [], 'excluded': [], 'warnings': []}
            slots.append(slot)
            if not confirmed:
                slot['warnings'].append('Business staffing hours have not been confirmed; review them before considering replacements.')
                continue
            if policy_error:
                slot['warnings'].append(policy_error)
                continue
            if not any(w['start'] <= a and w['end'] >= b for w in windows):
                slot['warnings'].append('This saved shift falls outside current staffing hours or on a closed date. Revise it before arranging replacement coverage.')
                continue
            for e in people:
                if e['id'] == person['id']: continue
                reason = None
                if not staff.active(e, day): reason = 'Outside saved employment dates.'
                elif any(_matches(r, e) for r in plan.get('absences', [])): reason = 'Recorded absent or sick on this date.'
                elif day in e.get('time_off', {}): reason = 'Recorded time off on this date.'
                elif not staff.qualifies(e, role): reason = 'Required role qualification is not recorded.'
                availability = staff.available(e, day)
                if reason is None and not availability:
                    reason = 'Availability is marked Off.' if e.get('availability', {}).get(day, {}).get('status') == 'off' else 'No eligible recorded availability window.'
                if reason:
                    slot['excluded'].append({'employee_id': e['id'], 'name': e['name'], 'reason': reason}); continue
                own = [s for s in plan['shifts'] if _matches(s, e)]
                exclusions = [(c['start'], c['end']) for c in policy['constraints'] if c['kind'] == 'exclude' and c['employee_id'] == e['id'] and c['date'] == day]
                free = _subtract(_intersection([(a, b)], [(w['start'], w['end']) for w in availability]), [(s['start'], s['end']) for s in own]+exclusions)
                possible = []
                if not own:
                    possible = [(x, y, None, 'off_schedule_replacement' if x == a and y == b else 'off_schedule_partial') for x, y in free]
                else:
                    for s in own:
                        if (s.get('role') or 'Team').casefold() != role.casefold(): continue
                        if not any(w['start'] <= s['start'] and w['end'] >= s['end'] for w in availability): continue
                        for x, y in free:
                            if y == s['start']: possible.append((x, y, s['id'], 'come_in_earlier'))
                            if x == s['end']: possible.append((x, y, s['id'], 'stay_later'))
                for x, y, extend, kind in possible:
                    # The existing restriction rule measures gross scheduled spans,
                    # unlike overtime ranking, which measures planned work net of breaks.
                    caps = [c['max_minutes'] for c in policy['constraints'] if c['kind'] == 'cap' and c['employee_id'] == e['id']]
                    room = min(caps)-span_totals[week][e['id']] if caps else y-x
                    if room <= 0: continue
                    if room < y-x:
                        if kind == 'come_in_earlier': x = y-room
                        else: y = x+room
                        if kind == 'off_schedule_replacement': kind = 'off_schedule_partial'
                    if not rules.allows(policy, e['id'], day, x, y, span_totals[week][e['id']]): continue
                    original = next((s for s in own if s['id'] == extend), None) if extend else None
                    if original:
                        full_start, full_end = min(x, original['start']), max(y, original['end'])
                        if not any(w['start'] <= full_start and w['end'] >= full_end for w in availability): continue
                        if not any(w['start'] <= full_start and w['end'] >= full_end for w in windows): continue
                        if any(o['id'] != extend and o['start'] < full_end and o['end'] > full_start for o in own): continue
                        if not rules.allows(policy, e['id'], day, full_start, full_end, span_totals[week][e['id']]-(original['end']-original['start'])): continue
                    covered = _intersection(work, [(x, y)])
                    if not covered: continue
                    remaining = _subtract(work, [(x, y)])
                    net = _minutes(covered); current = totals[week].get(e['id'], 0)
                    option = {'employee_id': e['id'], 'name': e['name'], 'kind': kind, 'start': x, 'end': y, 'extend_shift_id': extend,
                              'covered_work_minutes': net, 'remaining_work_minutes': _minutes(remaining), 'remaining_work_intervals': _rows(remaining),
                              'added_span_minutes': y-x, 'added_breaks': _rows(_intersection(breaks, [(x, y)])),
                              'preserved_existing_breaks': deepcopy((original or {}).get('breaks', [])),
                              'current_week_minutes': current, 'projected_week_minutes': current+net,
                              'projected_overtime_minutes': max(0, current+net-threshold), 'week_start': week,
                              'phone': e.get('phone', ''), 'email': e.get('email', ''), 'preferences': e.get('preferences', ''),
                              'dated_preference': e.get('availability', {}).get(day, {}).get('preference', ''), 'requires_agreement': True}
                    option['id'] = staff.stamp({'date': day, 'shift': shift['id'], 'choice': option})[:20]
                    slot['choices'].append(option)
                if not any(c['employee_id'] == e['id'] for c in slot['choices']):
                    slot['excluded'].append({'employee_id': e['id'], 'name': e['name'], 'reason': 'No non-overlapping off-schedule or adjacent extension option within saved availability and weekly restrictions.'})
            slot['choices'].sort(key=lambda c: (c['remaining_work_minutes'] != 0, c['projected_overtime_minutes'], -c['covered_work_minutes'], c['projected_week_minutes'], c['name'].casefold(), c['start']))
    summary = {name: sum(s[name] for s in slots) for name in ('gross_minutes', 'break_minutes', 'net_planned_minutes')}
    summary.update(shift_count=len(slots), dates_with_shifts=len({s['date'] for s in slots}),
                   full_replacement_slots=sum(any(c['remaining_work_minutes'] == 0 for c in s['choices']) for s in slots),
                   partial_only_slots=sum(bool(s['choices']) and not any(c['remaining_work_minutes'] == 0 for c in s['choices']) for s in slots),
                   no_option_slots=sum(not s['choices'] for s in slots))
    result = {'schema': SCHEMA, 'team_id': snapshot.production_id, 'employee_id': employee_id, 'employee_name': person['name'],
              'employee_revision': person.get('revision', 1), 'first_unavailable_date': key, 'recorded_end_date': person.get('end_date'),
              'as_of_date': as_of, 'coverage_from_date': coverage_from,
              'scenario_only': key != person.get('end_date'), 'summary': summary, 'saved_dates': saved, 'shifts': slots, 'warnings': warnings,
              'overtime_threshold_minutes': threshold, 'overtime_is_hard_cap': False, 'schedule_changes': False, 'employees_contacted': False,
              'scope': 'Latest saved dated schedules from the later of today or the first unavailable date. Today counts whole planned shifts, without assuming clock-in or attendance. Missing dates are not assumed scheduled. Planned work only; not attendance or payroll.',
              'source_sha256': source_sha}
    result['sha256'] = staff.stamp(result)
    return result
