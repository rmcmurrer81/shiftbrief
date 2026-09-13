'use strict';

// Coverage options are independent readings of saved schedules, never assignments.
(function () {
  const duration = minutes => Number((Number(minutes || 0) / 60).toFixed(2)) + ' h';
  const kinds = {
    off_schedule_replacement: 'Not scheduled that day · full cover',
    off_schedule_partial: 'Not scheduled that day · partial cover',
    come_in_earlier: 'Could come in earlier',
    stay_later: 'Could stay later'
  };

  window.openDepartureCoverage = async function (employee, date) {
    const report = await api('staff/departure-coverage', {
      employee_id: employee.id,
      date,
      expected_team_id: state.current_production,
      expected_revision: employee.revision
    });
    window.showDepartureCoverage(report);
  };

  window.showDepartureCoverage = function (report) {
    if (report.team_id !== state.current_production) throw Error('The business changed while coverage was loading. Reopen coverage for the current business.');
    const {body, d} = modal('Remaining shifts to cover · ' + report.employee_name);
    d.style.width = 'min(860px, calc(100vw - 32px))';
    d.style.maxHeight = '90vh';
    body.style.overflowY = 'auto';
    body.style.maxHeight = '72vh';
    let shiftIndex = 0, optionPage = 0;

    function draw() {
      body.replaceChildren();
      const summary = report.summary;
      body.append(node('p', (report.scenario_only ? 'Preview only · ' : 'Departure recorded · ') +
        'Unavailable from ' + fmtDate(report.first_unavailable_date, true) +
        '. No shifts have been reassigned.', 'muted'));
      const totals = node('div', undefined, 'employee-card-data');
      totals.style.gridTemplateColumns = 'repeat(3, minmax(0, 1fr))';
      for (const [label, value] of [
        ['Planned hours to cover', duration(summary.net_planned_minutes)],
        ['Affected shifts', String(summary.shift_count)],
        ['Saved dates affected', String(summary.dates_with_shifts)]
      ]) {
        const cell = node('div');
        cell.append(node('span', label), node('b', value));
        totals.append(cell);
      }
      body.append(totals);
      const details = node('details'), list = node('ul');
      details.append(node('summary', 'How these hours and options are counted'));
      const notes = [
        'Hours exclude saved breaks. Only recorded schedules are counted; unsaved future dates are unknown.',
        'Reviewing saved shifts from ' + fmtDate(report.coverage_from_date || report.first_unavailable_date) + '. Today’s planned shifts are shown in full; actual time worked is recorded separately.',
        'These are alternatives to discuss with your team, not a combined new schedule. Employee history and saved shifts are preserved.',
        ...(report.warnings || [])
      ];
      for (const note of notes) list.append(node('li', note));
      details.append(list); body.append(details);
      if (!report.shifts.length) {
        body.append(node('p', 'No saved shifts remain for this employee from that date.', 'empty'));
        return;
      }
      const selectorLabel = node('label', 'Affected shift'), selector = node('select');
      selector.setAttribute('aria-label', 'Affected shift');
      report.shifts.forEach((shift, index) => selector.add(new Option(
        fmtDate(shift.date, true) + ' · ' + ampm(shift.start) + '–' + ampm(shift.end) + ' · ' + duration(shift.net_planned_minutes), String(index))));
      selector.value = String(shiftIndex);
      selector.onchange = () => { shiftIndex = Number(selector.value); optionPage = 0; draw(); };
      selectorLabel.append(selector); body.append(selectorLabel);
      const shift = report.shifts[shiftIndex];
      body.append(node('h3', fmtDate(shift.date, true) + ' · ' + shift.role),
        node('p', ampm(shift.start) + '–' + ampm(shift.end) + ' · ' + duration(shift.net_planned_minutes) +
          ' work to cover · ' + duration(shift.break_minutes) + ' saved breaks'));
      for (const warning of shift.warnings || []) body.append(node('p', warning, 'warning'));
      if (!shift.choices.length) {
        body.append(node('p', 'No eligible cover found in the saved availability. Check with your team and update their availability before arranging cover.', 'warning'));
      }
      const perPage = innerHeight < 850 ? 1 : 2;
      for (const choice of shift.choices.slice(optionPage * perPage, (optionPage + 1) * perPage)) {
        const card = node('article', undefined, 'employee-card');
        card.append(node('strong', choice.name), node('p', kinds[choice.kind] || choice.kind),
          node('p', ampm(choice.start) + '–' + ampm(choice.end) + ' · ' + duration(choice.covered_work_minutes) + ' covered'),
          node('p', choice.remaining_work_minutes ? duration(choice.remaining_work_minutes) + ' still needs cover for this option.' : 'Covers this shift’s remaining working hours.'),
          node('p', 'Projected week: ' + duration(choice.projected_week_minutes) + ' if this option alone is arranged.'));
        if (choice.projected_overtime_minutes) card.append(node('p',
          duration(choice.projected_overtime_minutes) + ' above the saved weekly overtime threshold.', 'warning'));
        if (choice.remaining_work_intervals?.length) card.append(node('p', 'Still uncovered: ' +
          choice.remaining_work_intervals.map(x => ampm(x.start) + '–' + ampm(x.end)).join(', '), 'muted'));
        if (choice.added_breaks?.length) card.append(node('p', 'Breaks excluded from this option’s hours: ' +
          choice.added_breaks.map(x => ampm(x.start) + '–' + ampm(x.end)).join(', ') + '. Include them when reviewing the shift.', 'muted'));
        card.append(node('p', 'Contact: ' + ([choice.phone, choice.email].filter(Boolean).join(' · ') || 'Not recorded')));
        const preferences = [choice.preferences, choice.dated_preference].filter(Boolean).join('\n\n');
        if (preferences) card.append(btt('Read saved preferences', () => readPages(choice.name + ' · preferences', preferences)));
        body.append(card);
      }
      const pageControls = node('div', undefined, 'pager');
      pager(pageControls, optionPage, Math.ceil(shift.choices.length / perPage), page => { optionPage = page; draw(); });
      const feedback = node('p', '', 'warning');
      feedback.setAttribute('role', 'status');
      body.append(pageControls, btt('Review this saved date', async () => {
        try {
          feedback.textContent = '';
          if (state.current_production !== report.team_id) throw Error('The business changed. Reopen coverage for the current business.');
          await api('staff/day', {date: shift.date, expected_team_id: report.team_id});
          planningCenter = null; previewId = null; dayShiftPage = 0;
          d.close(); await refresh(); showScreen('schedule');
        } catch (error) {
          if (d.isConnected) feedback.textContent = error.message;
          else status(error.message);
        }
      }, 'primary'), feedback);
    }
    draw();
  };
})();
