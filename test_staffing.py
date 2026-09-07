import tempfile,unittest,copy
from datetime import date
from briefing import Store
from sarah_local import ask
import staffing as s
import shift_schedule as d

W='2026-09-13'
class StaffingTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name);s.select_week(self.store,W);s.settings(self.store,{'open':'09:00','close':'17:00'})
 def add(self,name,roles=None,hours=('09:00','17:00'),off=()):return s.save_employee(self.store,{'name':name,'start_date':'2026-09-01','roles':roles or ['Team'],'week_start':W,'availability':[{'date':key,'status':'off' if i in off else 'available','start':hours[0],'end':hours[1]} for i,key in enumerate(s.days(W))]})
 def saved_day(self,rows,key=W):
  plan={'date':key,'open':540,'close':1020,'minimum':1,'role_requirements':{'Team':1},'shifts':[{'id':str(i),'employee_id':e['id'],'employee':e['name'],'role':'Team','start':a,'end':b,'breaks':[]} for i,(e,a,b) in enumerate(rows)]};return d._save(self.store,plan,'test owner entry')
 def test_hire_conversation_exact_dated_form_without_auto_employee(self):
  self.assertIn('name',ask(self.store,'I hired a new employee')['answer']);self.assertEqual([],s.book(self.store)['employees'])
  r=ask(self.store,'Her name is Morgan Lee');self.assertEqual('employee_form',r['kind']);form=self.store.view()['assistant']['staffing_form'];self.assertEqual('Morgan Lee',form['name']);self.assertEqual(W,form['week_start']);self.assertEqual([],s.book(self.store)['employees'])
 def test_unknown_never_eligible_and_off_dates_preserved(self):
  unknown=s.save_employee(self.store,{'name':'Unknown','start_date':'2026-09-01','roles':['Team']});a=self.add('A',off=(0,));p=s.suggest_week(self.store,W)
  self.assertFalse(p['payload']['days'][0]['shifts']);self.assertTrue(p['payload']['unknown_availability']);self.assertFalse(any(x['employee_id']==unknown['id'] for day in p['payload']['days'] for x in day['shifts']));self.assertIsNone(d.latest(self.store,W))
 def test_week_readonly_accept_history_restart_and_workspace_isolation(self):
  self.add('Morgan');p=s.suggest_week(self.store,W);self.assertIsNone(d.latest(self.store,W));s.accept(self.store,p['id'],p['sha256']);self.assertEqual(7,len(d.book(self.store)['days']));restored=Store(self.tmp.name);self.assertEqual(480,d.latest(restored,W)['shifts'][0]['end']-d.latest(restored,W)['shifts'][0]['start'])
  p=s.suggest_week(self.store,W);s.accept(self.store,p['id'],p['sha256']);self.assertEqual(2,len(d.book(self.store)['days'][W]['revisions']));self.store.create_production('Real office');self.assertEqual([],s.view(self.store)['employees']);self.assertEqual({},d.book(self.store)['days'])
 def test_stale_roster_and_schedule_reject(self):
  a=self.add('A');p=s.suggest_week(self.store,W);s.time_off(self.store,a['id'],W,W)
  with self.assertRaisesRegex(ValueError,'changed'):s.accept(self.store,p['id'],p['sha256'])
  p=s.suggest_week(self.store,W);self.saved_day([])
  with self.assertRaisesRegex(ValueError,'changed'):s.accept(self.store,p['id'],p['sha256'])
 def test_role_coverage_cannot_double_credit(self):
  with self.assertRaises(ValueError):s.settings(self.store,{'roles':{'Team':1,'Cashier':1}})
  s.settings(self.store,{'roles':{'Cashier':1,'Floor':1}});self.add('Sam',['Cashier','Floor']);p=s.suggest_week(self.store,W);c=s.role_coverage(p['payload']['days'][0]);self.assertGreater(c['role_missing_person_minutes'],0);self.assertTrue(all(len({x['employee_id'] for x in day['shifts']})==1 for day in p['payload']['days']))
 def test_lunch_uses_overlap_and_requires_accept(self):
  a=self.add('A');b=self.add('B');plan=self.saved_day([(a,540,1020),(b,720,780)]);p=s.suggest_lunch(self.store,'0',W);choice=p['payload']['choices'][0];self.assertEqual(720,choice['start']);self.assertEqual(0,choice['extra_missing_person_minutes']);self.assertEqual([],d.latest(self.store,W)['shifts'][0]['breaks']);s.accept(self.store,p['id'],p['sha256'],choice['id']);self.assertEqual(1,len(d.latest(self.store,W)['shifts'][0]['breaks']));self.assertEqual([],d.view(self.store,W,1)['plan']['shifts'][0]['breaks'])
 def test_sick_order_threshold_partial_extension_and_no_contacts_sent(self):
  adam=self.add('Adam');lisa=self.add('Lisa');low=self.add('Low hours');high=self.add('High hours');unknown=s.save_employee(self.store,{'name':'No availability','start_date':'2026-09-01'})
  self.saved_day([(adam,540,780),(lisa,780,1020)]);self.saved_day([(high,540,1020)],'2026-09-14');s.settings(self.store,{'overtime_hours':8});p=s.suggest_sick(self.store,adam['id'],W);choices=p['payload']['choices'];self.assertEqual('Low hours',choices[0]['name']);self.assertFalse(any(c['name']=='No availability' for c in choices));extension=next(c for c in choices if c['name']=='Lisa');self.assertEqual(180,extension['covered_minutes']);self.assertEqual('Come in earlier',extension['kind']);self.assertEqual(2,len(d.latest(self.store,W)['shifts']));s.accept(self.store,p['id'],p['sha256'],extension['id']);plan=d.latest(self.store,W);self.assertEqual(1,len(plan['shifts']));self.assertEqual(600,plan['shifts'][0]['start']);self.assertEqual('Adam',plan['absences'][0]['name']);self.assertGreater(s.role_coverage(plan)['role_missing_person_minutes'],0)
 def test_quit_effective_date_preserves_past_and_flags_future(self):
  a=self.add('Adam');self.saved_day([(a,540,1020)]);ask(self.store,'Adam quit');self.assertIsNone(s.employee(self.store,a['id'])['end_date']);ask(self.store,'2026-09-13');self.assertEqual(W,s.employee(self.store,a['id'])['end_date']);self.assertTrue(s.conflicts(self.store,d.latest(self.store,W)));self.assertTrue(d.latest(self.store,W)['shifts']);self.assertTrue(s.active(s.employee(self.store,a['id']),'2026-09-12'))
 def test_week_must_be_sunday_with_all_actual_seven_dates(self):
  with self.assertRaises(ValueError):s.select_week(self.store,'2026-09-14')
  with self.assertRaises(ValueError):s.save_employee(self.store,{'name':'Bad','start_date':W,'week_start':W,'availability':[]})
  self.assertEqual([],s.book(self.store)['employees'])
 def test_proposal_edit_readonly_and_validation(self):
  e=self.add('Morgan');p=s.suggest_week(self.store,W);plans=copy.deepcopy(p['payload']['days'])
  for plan in plans:
   for shift in plan['shifts']:shift.update(start='10:00',end='16:00')
  revised=s.revise_week(self.store,p['id'],p['sha256'],plans);self.assertIsNone(d.latest(self.store,W));self.assertNotEqual(p['sha256'],revised['sha256']);s.accept(self.store,revised['id'],revised['sha256']);self.assertEqual(600,d.latest(self.store,W)['shifts'][0]['start'])
 def test_weekend_reminder_and_changed_employee(self):
  self.add('A');p=s.suggest_week(self.store,W);s.accept(self.store,p['id'],p['sha256']);self.assertFalse(s.view(self.store,date(2026,9,11))['reminder']['due']);s.time_off(self.store,'A',W,W);self.assertTrue(s.view(self.store,date(2026,9,11))['reminder']['due'])
 def test_example_is_separate_and_never_seeded_at_start(self):
  self.assertEqual([],s.view(self.store)['employees']);original=self.store.production_id;s.load_staff_example(self.store);self.assertNotEqual(original,self.store.production_id);self.assertEqual(5,len(s.view(self.store)['employees']));self.store.select_production(original);self.assertEqual([],s.view(self.store)['employees'])

if __name__=='__main__':unittest.main()
