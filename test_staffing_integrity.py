import copy,io,json,tempfile,unittest,zipfile
from unittest.mock import patch
from datetime import date
from pathlib import Path
from briefing import Store
from sarah_local import ask
import staffing as staff
import shift_schedule as daily
import operating_hours as hours

class IntegrityTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.store=Store(self.tmp.name)
 def example(self):staff.load_staff_example(self.store);p=staff.suggest_week(self.store,'2026-09-13');staff.accept(self.store,p['id'],p['sha256'])
 def test_missing_customer_hours_asks_without_inventing_schedule(self):
  staff.save_employee(self.store,{'name':'Morgan','start_date':'2026-09-01'});r=ask(self.store,'Suggest next week');self.assertIn('Review your customer opening hours',r['answer']);self.assertEqual('staffing_clarification',r['kind']);self.assertFalse(daily.book(self.store)['days'])
 def test_atomic_week_failure_keeps_memory_and_disk_unchanged(self):
  self.example();p=staff.suggest_week(self.store,'2026-09-13');before=copy.deepcopy(self.store.data);raw=(Path(self.tmp.name)/'state.json').read_bytes()
  with patch.object(self.store,'save',side_effect=OSError('test full disk')):
   with self.assertRaises(OSError):staff.accept(self.store,p['id'],p['sha256'])
  self.assertEqual(before,self.store.data);self.assertEqual(raw,(Path(self.tmp.name)/'state.json').read_bytes())
 def test_stale_employee_form_cannot_erase_new_timeoff(self):
  self.example();e=copy.deepcopy(staff.employee(self.store,'Adam'));staff.time_off(self.store,e['id'],'2026-09-15','2026-09-15','Requested appointment')
  with self.assertRaisesRegex(ValueError,'changed'):staff.save_employee(self.store,{'id':e['id'],'expected_revision':e['revision'],'preferences':'Stale form'})
  self.assertIn('2026-09-15',staff.employee(self.store,e['id'])['time_off']);fresh=staff.employee(self.store,e['id']);staff.cancel_time_off(self.store,e['id'],'2026-09-15',fresh['revision']);self.assertNotIn('2026-09-15',staff.employee(self.store,e['id'])['time_off']);self.assertEqual('time_off_cancelled',staff.employee(self.store,e['id'])['history'][-1]['operation'])
 def test_week_zip_has_actual_revisions_and_excludes_contacts_and_other_teams(self):
  self.example();e=staff.employee(self.store,'Adam');staff.save_employee(self.store,{'id':e['id'],'expected_revision':e['revision'],'phone':'PRIVATE-CALL-DETAIL','email':'private@example.invalid'});raw=staff.export_week(self.store,'2026-09-13')
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   self.assertIsNone(z.testzip());self.assertEqual({'weekly-shifts.csv','coverage-intervals.csv','dated-schedules.json','README.txt'},set(z.namelist()));content='\n'.join(z.read(n).decode() for n in z.namelist());self.assertNotIn('PRIVATE-CALL-DETAIL',content);self.assertNotIn('private@example.invalid',content);data=json.loads(z.read('dated-schedules.json'));self.assertEqual(7,len(data['days']));self.assertEqual(1,data['days'][0]['number'])
 def test_closed_date_cannot_receive_fresh_sick_or_lunch_proposals(self):
  self.example();plan=daily.latest(self.store,'2026-09-13');cfg=hours.settings(self.store);cfg['closures'].append({'kind':'date','date':'2026-09-13','reason':'System install'});p=hours.propose(self.store,cfg,'System install');hours.accept(self.store,p['id'],p['sha256'])
  with self.assertRaisesRegex(ValueError,'closed'):staff.suggest_lunch(self.store,plan['shifts'][0]['id'],'2026-09-13')
  with self.assertRaisesRegex(ValueError,'closed'):staff.suggest_sick(self.store,plan['shifts'][0]['employee_id'],'2026-09-13')
  with self.assertRaisesRegex(ValueError,'conflicts'):staff.restore_schedule(self.store,{'date':'2026-09-13','number':1,'expected_sha':plan['sha256']})
 def test_overnight_proposal_can_be_edited_with_explicit_midnight(self):
  cfg=hours.settings(self.store)
  for row in cfg['weekdays'].values():row.update(mode='24h')
  p=hours.propose(self.store,cfg,'24 hour test');hours.accept(self.store,p['id'],p['sha256']);w='2026-09-13';staff.save_employee(self.store,{'name':'Night staff','start_date':w,'week_start':w,'availability':[{'date':d,'status':'available','start':'22:00','end':'06:00','end_next_day':True} for d in staff.days(w)]});p=staff.suggest_week(self.store,w);plans=copy.deepcopy(p['payload']['days'])
  for plan in plans:
   for shift in plan['shifts']:shift.update(start=daily.hm(shift['start']),end='00:00' if shift['end']==1440 else daily.hm(shift['end']),end_next_day=shift['end']==1440)
  revised=staff.revise_week(self.store,p['id'],p['sha256'],plans);staff.accept(self.store,revised['id'],revised['sha256']);self.assertEqual(1440,daily.latest(self.store,w)['shifts'][0]['end'])
 def test_weekday_range_does_not_silently_skip_middle_days(self):
  thread={};hours.converse(self.store,thread,'Open 10am to 6pm Monday through Friday',date(2026,9,7));p=staff.book(self.store)['operating_proposals'][-1];self.assertTrue(all(p['config']['weekdays'][str(i)]['open']=='10:00' for i in range(1,6)));self.assertEqual('09:00',p['config']['weekdays']['0']['open']);hours.accept(self.store,p['id'],p['sha256']);r=hours.converse(self.store,thread,'Closed weekends',date(2026,9,7));self.assertIn('Saturday and Sunday',r['answer'])

if __name__=='__main__':unittest.main()
