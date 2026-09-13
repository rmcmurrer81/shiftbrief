import copy,tempfile,unittest
from datetime import date
from briefing import Store
import staffing as staff
import staffing_chat as chat
import shift_schedule as daily
import operating_hours as op

class LanguageCorrectionTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name);self.thread={}
 def lisa(self):return next(e for e in staff.book(self.store)['employees'] if e['name']=='Lisa')
 def last(self):return staff.book(self.store)['operating_proposals'][-1]
 def accept(self,p):return op.accept(self.store,p['id'],p['sha256'])
 def test_negated_employment_never_changes_saved_end_or_history(self):
  staff.load_staff_example(self.store);before=copy.deepcopy(staff.book(self.store)['employees']);history=copy.deepcopy(daily.book(self.store))
  for text in ['Lisa did not quit on 2026-09-15. She is staying.',"Lisa didn't quit on 2026-09-15.",'Lisa was not terminated on 2026-09-15.','Lisa hasn’t quit on 2026-09-15.']:
   answer=chat.converse(self.store,self.thread,text);self.assertEqual(answer['kind'],'staffing_clarification');self.assertEqual(staff.book(self.store)['employees'],before);self.assertEqual(daily.book(self.store),history)
 def test_negated_employment_cancels_pending_date_before_date_consumption(self):
  staff.load_staff_example(self.store);self.thread['staffing_pending']={'kind':'end_date','employee_id':self.lisa()['id'],'name':'Lisa','reason':'Legacy saved quit report'};chat.converse(self.store,self.thread,'Actually Lisa did not quit on 2026-09-15.');self.assertIsNone(self.thread['staffing_pending']);self.assertIsNone(self.lisa()['end_date']);chat.converse(self.store,self.thread,'2026-09-16');self.assertIsNone(self.lisa()['end_date'])
 def test_pending_end_date_denial_can_use_pronoun_and_date(self):
  staff.load_staff_example(self.store);self.thread['staffing_pending']={'kind':'end_date','employee_id':self.lisa()['id'],'name':'Lisa','reason':'Legacy saved quit report'};answer=chat.converse(self.store,self.thread,'No, she is staying. 2026-09-15 was a mistake.');self.assertEqual(answer['kind'],'staffing_clarification');self.assertIsNone(self.lisa()['end_date']);self.assertIsNone(self.thread['staffing_pending'])
 def test_do_not_close_correction_withdraws_pending(self):
  op.converse(self.store,self.thread,'We are closed on Christmas.');reply=op.converse(self.store,self.thread,"We don't close on Christmas.");self.assertIn('withdrawn',reply['answer']);self.assertTrue(self.last()['cancelled_at'])
 def test_saved_ended_record_is_not_silently_erased_by_denial(self):
  staff.load_staff_example(self.store);review=chat.converse(self.store,self.thread,'Lisa quit on 2026-09-15.');self.assertEqual('employment_end',review['navigation']['view']);self.assertIsNone(self.lisa()['end_date']);staff.end_employment(self.store,self.lisa()['id'],'2026-09-15','Explicitly reviewed end date');answer=chat.converse(self.store,self.thread,'Lisa did not quit on 2026-09-15.');self.assertIn('currently has a saved end date of 2026-09-15',answer['answer']);self.assertEqual(self.lisa()['end_date'],'2026-09-15')
 def test_christmas_eve_is_december24_recurring_not_day25(self):
  answer=op.converse(self.store,self.thread,'We are closed on Christmas Eve.',date(2026,9,7));self.assertIn('2027-12-24',answer['answer']);self.assertFalse(op.resolve(self.store,'2026-12-24')['closed']);self.accept(self.last())
  for year in [2026,2027,2028]:self.assertTrue(op.resolve(self.store,f'{year}-12-24')['closed']);self.assertFalse(op.resolve(self.store,f'{year}-12-25')['closed'])
 def test_christmas_day_retains_december25_behavior(self):
  op.converse(self.store,self.thread,'We are closed on Christmas Day.');self.accept(self.last());self.assertTrue(op.resolve(self.store,'2026-12-25')['closed']);self.assertFalse(op.resolve(self.store,'2026-12-24')['closed'])
 def test_denial_withdraws_pending_closure_and_rejects_stale_accept(self):
  before=op.settings(self.store);op.converse(self.store,self.thread,'We are closed on Christmas.');old=copy.deepcopy(self.last());reply=op.converse(self.store,self.thread,'Actually, we are not closed on Christmas.');self.assertIn('withdrawn',reply['answer']);self.assertTrue(self.last()['cancelled_at']);self.assertIsNone(self.thread['operating_proposal_id']);self.assertEqual(op.settings(self.store),before)
  with self.assertRaisesRegex(ValueError,'no longer current'):self.accept(old)
  restored=Store(self.tmp.name);self.assertTrue(staff.book(restored)['operating_proposals'][-1]['cancelled_at']);self.assertEqual(op.settings(restored),before)
 def test_accepted_closure_removal_is_reviewed_and_preserves_other_closures(self):
  staff.load_staff_example(self.store);week=staff.suggest_week(self.store,'2026-09-13');staff.accept(self.store,week['id'],week['sha256']);history=copy.deepcopy(daily.book(self.store));cfg=op.settings(self.store);cfg['closures']=[{'kind':'annual','month':12,'day':24,'reason':'Eve'},{'kind':'annual','month':12,'day':25,'reason':'Day'}];self.accept(op.propose(self.store,cfg,'Owner entered two closures'))
  reply=op.converse(self.store,self.thread,'Actually, we are not closed on Christmas.');self.assertEqual(reply['kind'],'operating_proposal');self.assertTrue(op.resolve(self.store,'2026-12-25')['closed']);self.assertEqual([c['day'] for c in self.last()['config']['closures']],[24]);self.accept(self.last());self.assertFalse(op.resolve(self.store,'2026-12-25')['closed']);self.assertTrue(op.resolve(self.store,'2026-12-24')['closed']);self.assertEqual(daily.book(self.store),history)
 def test_date_exception_does_not_remove_entire_annual_closure(self):
  op.converse(self.store,self.thread,'We are closed on Christmas.');self.accept(self.last());before=op.settings(self.store);reply=op.converse(self.store,self.thread,'We are not closed on 2026-12-25.');self.assertEqual(reply['kind'],'operating_clarification');self.assertEqual(op.settings(self.store),before)
 def test_unsupported_holiday_qualifiers_require_exact_dates(self):
  for text in ['We are closed Christmas week.','We are closed the day after Christmas.','We are closed on Christmas Eve in the afternoon.','We are closed on Christmas except Christmas Eve.']:
   reply=op.converse(self.store,self.thread,text);self.assertEqual(reply['kind'],'operating_clarification');self.assertFalse(staff.book(self.store).get('operating_proposals'));self.assertEqual(op.settings(self.store)['closures'],[])
 def test_explicit_date_and_named_day_conflict_is_not_guessed(self):
  reply=op.converse(self.store,self.thread,'We are closed on Christmas Eve, 2026-12-25.');self.assertEqual(reply['kind'],'operating_clarification');self.assertEqual(op.settings(self.store)['closures'],[])
 def test_matching_explicit_date_is_one_date_not_annual(self):
  op.converse(self.store,self.thread,'We are closed on Christmas Eve, 2026-12-24.');self.assertEqual(self.last()['config']['closures'][0]['kind'],'date');self.accept(self.last());self.assertTrue(op.resolve(self.store,'2026-12-24')['closed']);self.assertFalse(op.resolve(self.store,'2027-12-24')['closed'])
 def test_normal_opening_hours_still_create_reviewed_proposal(self):
  reply=op.converse(self.store,self.thread,'We open 9am to 5pm Monday through Friday.');self.assertEqual(reply['kind'],'operating_proposal');self.assertEqual(self.last()['config']['weekdays']['3']['open'],'09:00')

if __name__=='__main__':unittest.main()
