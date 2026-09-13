"""Already-decided departures open review; chat never changes employment dates."""
import copy,tempfile,unittest
from unittest.mock import patch
from briefing import Store
import staffing,staffing_chat as chat,shift_schedule,sarah_local,general_chat

class DepartureReviewTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name)
  staffing.select_week(self.store,'2026-09-13')
  self.morgan=staffing.save_employee(self.store,{'name':'Morgan Stone','start_date':'2026-01-01','roles':['Team']})
  self.ada=staffing.save_employee(self.store,{'name':'Ada Chen','start_date':'2026-01-01','roles':['Team']})
  for date in ('2026-08-01','2026-10-01'):
   shift_schedule._save(self.store,{'date':date,'open':540,'close':1020,'minimum':1,'role_requirements':{'Team':1},'shifts':[{'id':'morgan-'+date,'employee_id':self.morgan['id'],'employee':'Morgan Stone','role':'Team','start':540,'end':1020,'breaks':[]}]},'Fixture saved schedule')
 def records(self):return copy.deepcopy((staffing.book(self.store)['employees'],shift_schedule.book(self.store),self.store.data.get('work_records',{})))
 def ask_without_mutation(self,text):
  before=self.records()
  with patch.object(staffing,'end_employment',side_effect=AssertionError('Chat cannot apply departure')):result=sarah_local.ask(self.store,text)
  self.assertEqual(before,self.records());return result
 def review(self,text,date=''):
  result=self.ask_without_mutation(text)
  self.assertEqual('employee_form',result['kind'],text)
  nav=result['navigation'];self.assertEqual('employment_end',nav['view'])
  self.assertEqual(self.store.production_id,nav['team_id']);self.assertEqual(self.morgan['id'],nav['employee_id'])
  self.assertEqual(staffing.employee(self.store,self.morgan['id'])['revision'],nav['employee_revision'])
  self.assertEqual(date,nav['proposed_date']);return result
 def test_exact_user_report_opens_bound_review_and_reopens_from_saved_chat(self):
  result=self.review('i just fired morgan stone')
  reopened=Store(self.tmp.name);last=reopened.data['assistant_threads'][self.store.production_id]['messages'][-1]
  self.assertEqual(result['navigation'],last['navigation']);self.assertIn('Record end date',last['text'])
 def test_affirmative_variants_share_review_and_do_not_guess_relative_date(self):
  for text in ['I fired Morgan Stone','We just fired Morgan Stone','I have already fired Morgan Stone','I’ve just fired Morgan Stone','Morgan Stone was fired','Morgan Stone has been fired','Morgan Stone quit','Morgan Stone has quit','Morgan Stone is quitting','Morgan Stone was terminated','I just terminated Morgan Stone','Morgan Stone left the company','Morgan Stone no longer works here','I just fired Morgan Stone today']:
   with self.subTest(text=text):self.review(text)
 def test_explicit_dates_only_prefill_review(self):
  for text in ['I fired Morgan Stone on 2026-09-15','Morgan Stone quit on 2026-09-15','Morgan Stone was terminated effective 2026-09-15','terminate Morgan Stone from 2026-09-15']:
   with self.subTest(text=text):self.review(text,'2026-09-15')
 def test_negated_hypothetical_quoted_and_ambiguous_messages_never_open_review(self):
  for text in ['I did not fire Morgan Stone','I did not fire Morgan Stone on 2026-09-15','I haven’t fired Morgan Stone','Morgan Stone was not fired','Morgan Stone did not quit','If I fired Morgan Stone on 2026-09-15','Suppose Morgan Stone quit','Should I fire Morgan Stone?','Did Morgan Stone quit on 2026-09-15?','"I fired Morgan Stone"','I said I fired Morgan Stone','fire Morgan Stone','I fired Morgan','I fired Nobody Example','I fired Morgan Stone and Ada Chen','I almost fired Morgan Stone']:
   with self.subTest(text=text):self.assertNotEqual('employment_end',self.ask_without_mutation(text).get('navigation',{}).get('view'))
 def test_recommendation_question_preserves_existing_refusal(self):
  result=self.ask_without_mutation('Who should I fire?');self.assertEqual('employer_insight',result['kind'])
  self.assertIn('isn’t evidence here to recommend firing a particular person',result['answer'])
  self.assertNotEqual('employment_end',result.get('navigation',{}).get('view'))
 def test_bare_date_after_new_review_does_not_apply_any_departure(self):
  self.review('Morgan Stone quit');self.ask_without_mutation('2026-09-15')
  self.assertIsNone(staffing.employee(self.store,self.morgan['id'])['end_date'])
 def test_old_saved_pending_date_migrates_to_review_without_automatic_save(self):
  thread=self.store.data.setdefault('assistant_threads',{}).setdefault(self.store.production_id,{'messages':[],'pending':None})
  thread['staffing_pending']={'kind':'end_date','employee_id':self.morgan['id'],'name':'Morgan Stone','reason':'Morgan Stone quit'}
  self.store.save();self.review('2026-09-15','2026-09-15');self.assertIsNone(thread['staffing_pending'])
 def test_new_report_clears_older_other_employee_date_question(self):
  thread=self.store.data.setdefault('assistant_threads',{}).setdefault(self.store.production_id,{'messages':[],'pending':None})
  thread['staffing_pending']={'kind':'end_date','employee_id':self.ada['id'],'name':'Ada Chen','reason':'Ada Chen quit'}
  self.review('I just fired Morgan Stone');self.ask_without_mutation('2026-09-15')
  self.assertTrue(all(e['end_date'] is None for e in staffing.book(self.store)['employees']))
 def test_saved_end_and_history_are_preserved_on_denial_or_repeated_report(self):
  staffing.end_employment(self.store,self.morgan['id'],'2026-09-15','Fixture already reviewed')
  self.ask_without_mutation('Morgan Stone did not quit on 2026-09-15')
  self.review('I fired Morgan Stone on 2026-10-01','2026-10-01')
  self.assertEqual('2026-09-15',staffing.employee(self.store,self.morgan['id'])['end_date'])
 def test_duplicate_names_require_disambiguation(self):
  duplicate=copy.deepcopy(self.morgan);duplicate['id']='second-morgan';staffing.book(self.store)['employees'].append(duplicate)
  result=self.ask_without_mutation('I fired Morgan Stone');self.assertNotIn('navigation',result)
 def test_existing_other_staff_draft_is_not_consumed_as_departure(self):
  thread=self.store.data.setdefault('assistant_threads',{}).setdefault(self.store.production_id,{'messages':[],'pending':None})
  thread['staffing_pending']={'kind':'hire_name'}
  result=self.ask_without_mutation('I fired Morgan Stone');self.assertNotIn('navigation',result)
  self.assertEqual({'kind':'hire_name'},thread['staffing_pending'])
 def test_optional_ai_preflight_routes_departure_to_normal_review_without_model(self):
  before=copy.deepcopy(self.store.data)
  mutation,result=general_chat.preview(self.store,'I just fired Morgan Stone')
  self.assertTrue(mutation);self.assertEqual('employment_end',result['navigation']['view'])
  self.assertEqual(before,self.store.data)

if __name__=='__main__':unittest.main(verbosity=2)
