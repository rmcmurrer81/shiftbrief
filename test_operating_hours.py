import copy,tempfile,unittest
from datetime import date
from briefing import Store
import staffing as staff
import shift_schedule as daily
import operating_hours as op

class OperatingHoursTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name);self.thread={}
 def accept(self,p):return op.accept(self.store,p['id'],p['sha256'])
 def use(self,window):
  cfg=op.settings(self.store);cfg['weekdays']={str(i):copy.deepcopy(window) for i in range(7)};p=op.propose(self.store,cfg,'owner test hours');self.accept(p)
 def test_customer_hours_and_real_buffer_bands(self):
  self.use({'mode':'hours','open':'09:00','close':'17:00','before_minutes':120,'after_minutes':60});r=op.resolve(self.store,'2026-09-13');self.assertEqual([{'start':420,'end':540,'kind':'Opening staff'},{'start':540,'end':1020,'kind':'Customer hours'},{'start':1020,'end':1080,'kind':'Closing staff'}],r['bands']);self.assertEqual([{'start':420,'end':1080}],r['coverage_windows'])
 def test_24_hours_is_full_day_and_no_zero_length(self):
  self.use({'mode':'24h'});r=op.resolve(self.store,'2026-09-13');self.assertEqual([{'start':0,'end':1440}],r['customer_windows']);self.assertFalse(r['closed'])
 def test_overnight_wrap_projects_to_actual_calendar_days(self):
  self.use({'mode':'hours','open':'22:00','close':'06:00','end_next_day':True,'before_minutes':60,'after_minutes':60});r=op.resolve(self.store,'2026-09-13');self.assertEqual([{'start':0,'end':420},{'start':1260,'end':1440}],r['coverage_windows']);self.assertEqual([{'start':0,'end':360},{'start':1320,'end':1440}],r['customer_windows'])
 def test_closed_christmas_recurs_and_blocks_overnight_both_years(self):
  self.use({'mode':'hours','open':'22:00','close':'06:00','end_next_day':True,'before_minutes':120,'after_minutes':120});result=op.converse(self.store,self.thread,'We are closed on Christmas',date(2026,9,7));self.assertIn('2027-12-25',result['answer']);self.assertFalse(op.resolve(self.store,'2026-12-25')['closed']);p=staff.book(self.store)['operating_proposals'][-1];self.accept(p)
  for year in (2026,2027,2028):self.assertEqual([],op.resolve(self.store,f'{year}-12-25')['coverage_windows']);self.assertTrue(op.resolve(self.store,f'{year}-12-25')['closed'])
  self.assertFalse(op.resolve(self.store,'2026-12-24')['closed']);self.assertFalse(op.resolve(self.store,'2026-12-26')['closed'])
 def test_one_date_closure_resolved_reviewed_and_reason_preserved(self):
  result=op.converse(self.store,self.thread,'Next Thursday we are closed for a new system installation',date(2026,9,7));self.assertIn('2026-09-10',result['answer']);self.assertFalse(op.resolve(self.store,'2026-09-10')['closed']);self.accept(staff.book(self.store)['operating_proposals'][-1]);self.assertTrue(op.resolve(self.store,'2026-09-10')['closed']);self.assertFalse(op.resolve(self.store,'2026-09-17')['closed'])
 def test_am_pm_and_weekday_clarification_before_mutation(self):
  r=op.converse(self.store,self.thread,'We open 9 to 5');self.assertIn('AM/PM',r['answer']);self.assertFalse(staff.book(self.store).get('operating_proposals'))
  r=op.converse(self.store,self.thread,'We open 9am to 5pm');self.assertIn('Which weekdays',r['answer']);r=op.converse(self.store,self.thread,'Every day');self.assertEqual('operating_proposal',r['kind']);self.assertFalse('operating_hours' in staff.book(self.store)['settings'])
 def test_changed_hours_stale_week_and_preserve_saved_history(self):
  staff.load_staff_example(self.store);p=staff.suggest_week(self.store,'2026-09-13');staff.accept(self.store,p['id'],p['sha256']);old=daily.latest(self.store,'2026-09-13');pending=staff.suggest_week(self.store,'2026-09-13');cfg=op.settings(self.store);cfg['closures'].append({'kind':'date','date':'2026-09-13','reason':'Owner closure'});self.accept(op.propose(self.store,cfg,'Owner closure'))
  with self.assertRaisesRegex(ValueError,'changed'):staff.accept(self.store,pending['id'],pending['sha256'])
  self.assertEqual(old,daily.latest(self.store,'2026-09-13'));self.assertTrue(staff.conflicts(self.store,old));fresh=staff.suggest_week(self.store,'2026-09-13');self.assertEqual([],fresh['payload']['days'][0]['shifts']);self.assertEqual(0,staff.role_coverage(fresh['payload']['days'][0])['role_missing_person_minutes'])
 def test_overnight_availability_is_projected_not_invented(self):
  w='2026-09-13';e=staff.save_employee(self.store,{'name':'Night worker','start_date':w,'roles':['Team'],'week_start':w,'availability':[{'date':d,'status':'available' if i==0 else 'unknown','start':'22:00','end':'06:00','end_next_day':True} for i,d in enumerate(staff.days(w))]});self.assertEqual([{'start':1320,'end':1440}],staff.available(e,w));self.assertEqual([{'start':0,'end':360}],staff.available(e,'2026-09-14'));self.assertEqual([],staff.available(e,'2026-09-15'));staff.time_off(self.store,e['id'],'2026-09-14','2026-09-14');self.assertEqual([],staff.available(staff.employee(self.store,e['id']),'2026-09-14'))
 def test_closed_weekday_and_24_hour_schedule_no_silent_overlap(self):
  self.use({'mode':'24h'});cfg=op.settings(self.store);cfg['weekdays']['1']['mode']='closed';self.accept(op.propose(self.store,cfg,'Closed every Monday'));self.assertTrue(op.resolve(self.store,'2026-09-14')['closed']);self.assertEqual(1440,op.resolve(self.store,'2026-09-15')['staffing_close'])
 def test_outside_customer_hours_not_outside_staffing_hours(self):
  self.use({'mode':'hours','open':'09:00','close':'17:00','before_minutes':60,'after_minutes':60});w='2026-09-13';staff.save_employee(self.store,{'name':'Opener','start_date':w,'week_start':w,'availability':[{'date':d,'status':'available','start':'08:00','end':'18:00'} for d in staff.days(w)]});p=staff.suggest_week(self.store,w);day=p['payload']['days'][0];self.assertEqual(480,day['shifts'][0]['start']);self.assertEqual(1080,day['shifts'][0]['end']);self.assertEqual(0,staff.role_coverage(day)['role_missing_person_minutes'])

if __name__=='__main__':unittest.main()
