import copy, json, sys, tempfile, threading, unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from datetime import date
from unittest.mock import patch
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'app'))
from briefing import Store
import staffing as s
import shift_schedule as d
import staffing_constraints as rules
import departure_coverage as c
import server

W='2026-09-13'

class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name); s.select_week(self.store,W)
        s.settings(self.store, {'open':'06:00','close':'23:00','roles':{'Cashier':1},'overtime_hours':40})
        self.departed=self.add('Departing')

    def add(self,name,roles=None,status='available',start='06:00',end='23:00'):
        return s.save_employee(self.store, {'name':name,'start_date':'2026-09-01','roles':roles or ['Cashier'],'week_start':W,
            'availability':[{'date':day,'status':status,'start':start,'end':end} for day in s.days(W)]})

    def day(self,rows,key=W):
        shifts=[]
        for i,row in enumerate(rows):
            e,a,b,*rest=row
            shifts.append({'id':str(i),'employee_id':e['id'],'employee':e['name'],'role':'Cashier','start':a,'end':b,
                           'breaks':[{'id':str(j),'label':'Lunch','start':x,'end':y} for j,(x,y) in enumerate(rest[0] if rest else [])]})
        return d._save(self.store,{'date':key,'open':360,'close':1380,'minimum':1,'role_requirements':{'Cashier':1},'shifts':shifts},'fixture')

    def report(self,key=W):return c.analyze(self.store,self.departed['id'],key,today=date(2026,9,13))

    def test_exact_effective_date_latest_revision_net_breaks_and_read_only(self):
        self.day([(self.departed,540,1020,[(720,750)])])
        self.day([(self.departed,600,1020,[(720,750)])])
        self.day([(self.departed,540,1020)],'2026-09-14')
        self.day([(self.departed,540,1020)],'2026-09-12')
        before=copy.deepcopy(self.store.data); disk=(self.store.path/'state.json').read_bytes()
        result=self.report(); self.assertEqual(2,result['summary']['shift_count'])
        self.assertEqual(900,result['summary']['gross_minutes']); self.assertEqual(870,result['summary']['net_planned_minutes'])
        self.assertEqual(2,result['shifts'][0]['source_revision']); self.assertEqual(before,self.store.data)
        self.assertEqual(disk,(self.store.path/'state.json').read_bytes())
        self.assertEqual(1,self.report('2026-09-14')['summary']['shift_count'])

    def test_full_replacement_retains_break_work_not_gross(self):
        replacement=self.add('Available off roster'); self.day([(self.departed,540,1020,[(720,750)])])
        option=self.report()['shifts'][0]['choices'][0]
        self.assertEqual(replacement['id'],option['employee_id']); self.assertEqual('off_schedule_replacement',option['kind'])
        self.assertEqual(450,option['covered_work_minutes']); self.assertEqual(450,option['projected_week_minutes'])
        self.assertEqual(0,option['remaining_work_minutes']); self.assertEqual([{'start':720,'end':750}],option['added_breaks'])

    def test_early_late_partial_preserve_remaining_intervals(self):
        early=self.add('Early'); late=self.add('Late')
        self.day([(self.departed,540,1020,[(720,750)]),(early,780,1020),(late,360,660)])
        result=self.report(); options=result['shifts'][0]['choices']
        a=next(o for o in options if o['name']=='Early'); b=next(o for o in options if o['name']=='Late')
        self.assertEqual('come_in_earlier',a['kind']); self.assertEqual((540,780,210,240),(a['start'],a['end'],a['covered_work_minutes'],a['remaining_work_minutes']))
        self.assertEqual('stay_later',b['kind']); self.assertEqual(330,b['covered_work_minutes'])
        self.assertEqual(1,result['summary']['partial_only_slots'])

    def test_unavailability_role_employment_timeoff_sickness_and_unknown(self):
        off=self.add('Off',status='off'); wrong=self.add('Wrong role',roles=['Floor']); future=self.add('Future'); ended=self.add('Ended')
        timeoff=self.add('Time off'); sick=self.add('Sick'); unknown=self.add('Unknown',status='unknown')
        s.employee(self.store,future['id'])['start_date']='2026-09-14'; s.end_employment(self.store,ended['id'],W,'fixture')
        s.time_off(self.store,timeoff['id'],W,W,'fixture'); plan=self.day([(self.departed,540,1020)])
        plan['absences']=[{'employee_id':sick['id'],'name':sick['name'],'reason':'Sick'}]; d._save(self.store,plan,'absence')
        result=self.report()['shifts'][0]; self.assertEqual([],result['choices']); self.assertEqual(7,len(result['excluded']))

    def test_overlap_no_break_as_free_time_and_wrong_extension_role(self):
        overlap=self.add('Overlap'); role=self.add('Other role',roles=['Cashier','Floor'])
        plan=self.day([(self.departed,600,660),(overlap,540,720,[(600,660)]),(role,660,800)])
        plan['shifts'][2]['role']='Floor'; d._save(self.store,plan,'role')
        self.assertFalse(self.report()['shifts'][0]['choices'])

    def test_overtime_is_rank_warning_not_hard_limit(self):
        low=self.add('Low'); high=self.add('High'); self.day([(self.departed,540,1020)])
        self.day([(high,540,1020)],'2026-09-14'); s.settings(self.store,{'overtime_hours':8})
        choices=self.report()['shifts'][0]['choices']; self.assertEqual('Low',choices[0]['name'])
        self.assertEqual(480,next(o for o in choices if o['name']=='High')['projected_overtime_minutes'])

    def cap(self,person,amount=600):
        request=f'cap {person["name"]} at {amount/60:g} hours this week'
        envelope={'snapshot_sha256':'fixture','constraints':[{'kind':'cap','employee_id':person['id'],'max_minutes':amount,'quote':request}], 'issues':[]}
        policy=rules.validate(self.store,W,request,envelope,'fixture')
        s.book(self.store)['proposals'].append({'id':'policy','kind':'week','week_start':W,'payload':{'constraints':policy}})

    def test_explicit_cap_uses_gross_span_and_partial_room(self):
        e=self.add('Capped'); self.day([(self.departed,540,1020,[(720,750)])]); self.day([(e,540,1020,[(720,750)])],'2026-09-14')
        self.cap(e,600); option=self.report()['shifts'][0]['choices'][0]
        self.assertEqual(120,option['added_span_minutes']); self.assertEqual('off_schedule_partial',option['kind'])
        self.assertEqual(570,option['projected_week_minutes'])

    def test_no_cross_slot_allocation_claim_and_each_week_reset(self):
        e=self.add('Available'); self.day([(self.departed,540,1020)]); self.day([(self.departed,540,1020)],'2026-09-14')
        r=self.report(); self.assertEqual([480,480],[x['choices'][0]['projected_week_minutes'] for x in r['shifts']])
        self.assertIn('independent',r['warnings'][0]); self.assertFalse(r['schedule_changes'])

    def test_explicit_exclusion_and_tampered_policy_hold(self):
        e=self.add('Excluded'); self.day([(self.departed,540,1020)])
        request='exclude Excluded on 2026-09-13 09:00 to 12:00'
        env={'snapshot_sha256':'fixture','constraints':[{'kind':'exclude','employee_id':e['id'],'date':W,'start':540,'end':720,'quote':request}],'issues':[]}
        policy=rules.validate(self.store,W,request,env,'fixture')
        s.book(self.store)['proposals'].append({'id':'policy','kind':'week','week_start':W,'payload':{'constraints':policy}})
        option=self.report()['shifts'][0]['choices'][0]; self.assertEqual(720,option['start'])
        policy['constraints'][0]['start']=600
        self.assertFalse(self.report()['shifts'][0]['choices']); self.assertTrue(self.report()['shifts'][0]['warnings'])

    def test_no_schedule_invalid_dates_id_precedence_and_saved_end(self):
        self.assertEqual(0,self.report()['summary']['shift_count'])
        with self.assertRaises(ValueError):self.report('2026-08-01')
        with self.assertRaises(ValueError):self.report('2026-99-01')
        e=self.add('Different'); plan=self.day([(e,540,1020)])
        plan['shifts'][0]['employee']=self.departed['name']; d._save(self.store,plan,'mismatched label')
        self.assertEqual(0,self.report()['summary']['shift_count'])
        s.end_employment(self.store,self.departed['id'],W,'fixture'); self.assertFalse(self.report()['scenario_only'])

    def test_closed_date_holds_saved_work(self):
        e=self.add('Available'); self.day([(self.departed,540,1020)])
        config=s.book(self.store)['settings']; config['operating_hours']={'weekdays':{str(i):{'mode':'closed'} for i in range(7)},'date_overrides':{},'closures':[]}
        slot=self.report()['shifts'][0]; self.assertEqual(480,slot['net_planned_minutes']); self.assertFalse(slot['choices']); self.assertTrue(slot['warnings'])

    def test_context_guard_rejects_team_revision_and_name(self):
        with self.assertRaises(ValueError):c.check_context(self.store,self.departed['id'],'wrong',1)
        with self.assertRaises(ValueError):c.check_context(self.store,self.departed['id'],self.store.production_id,999)
        with self.assertRaises(ValueError):c.check_context(self.store,self.departed['id'],self.store.production_id,True)
        with self.assertRaises(ValueError):c.check_context(self.store,self.departed['name'],self.store.production_id,1)

    def test_http_preview_read_only_then_guarded_end(self):
        self.day([(self.departed,540,1020)]); before=(self.store.path/'state.json').read_bytes()
        original=c.analyze
        patcher=patch.object(c,'analyze',side_effect=lambda *a,**kw:original(*a,**kw,today=date(2026,9,13)))
        patcher.start(); self.addCleanup(patcher.stop)
        http=server.make_server(self.store.path,0); worker=threading.Thread(target=http.serve_forever,daemon=True); worker.start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        body={'employee_id':self.departed['id'],'date':W,'expected_team_id':self.store.production_id,'expected_revision':self.departed.get('revision',1)}
        def post(route,payload):
            request=Request('http://127.0.0.1:'+str(http.server_port)+'/api/staff/'+route,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','X-ShiftBrief-Token':http.app.token})
            with urlopen(request,timeout=10) as r:return json.load(r)
        response=post('departure-coverage',body); self.assertEqual(1,response['summary']['shift_count'])
        self.assertEqual(before,(self.store.path/'state.json').read_bytes())
        with self.assertRaises(HTTPError) as caught:post('end',{**body,'expected_revision':999})
        caught.exception.close()
        self.assertEqual(before,(self.store.path/'state.json').read_bytes())
        result=post('end',body); self.assertEqual(W,result['end_date']); self.assertIn('departure_coverage',result)
        self.assertTrue(result['departure_summary_saved'])
        messages=http.app.store.data['assistant_threads'][self.store.production_id]['messages']
        self.assertIn('1 shifts and 8 planned working hours',messages[-1]['text'])
        with self.assertRaises(HTTPError) as duplicate:post('end',body)
        duplicate.exception.close()
        self.assertEqual(messages,http.app.store.data['assistant_threads'][self.store.production_id]['messages'])
        self.assertEqual(1,len(d.latest(http.app.store,W)['shifts']))
        self.assertNotIn('departure_coverage',s.employee(http.app.store,self.departed['id']))

    def test_past_departure_counts_only_today_and_future_whole_dates(self):
        self.day([(self.departed,540,1020)],'2026-09-12'); self.day([(self.departed,540,1020)])
        r=self.report('2026-09-10')
        self.assertEqual('2026-09-13',r['coverage_from_date']); self.assertEqual('2026-09-13',r['as_of_date'])
        self.assertEqual(1,r['summary']['shift_count']); self.assertEqual(480,r['summary']['net_planned_minutes'])

    def test_multiple_departed_slots_and_existing_extension_breaks(self):
        e=self.add('Extension'); self.day([(self.departed,540,720),(self.departed,1020,1140),(e,720,1020,[(810,840)])])
        r=self.report(); self.assertEqual(2,r['summary']['shift_count']); self.assertEqual(300,r['summary']['net_planned_minutes'])
        self.assertEqual(270,r['shifts'][0]['choices'][0]['current_week_minutes'])
        self.assertEqual(810,r['shifts'][0]['choices'][0]['preserved_existing_breaks'][0]['start'])

    def test_whole_extension_existing_overlap_or_outside_hours_is_rejected(self):
        e=self.add('Conflict'); self.day([(self.departed,540,720),(e,720,1020),(e,900,1080)])
        self.assertFalse(self.report()['shifts'][0]['choices'])
        self.day([(self.departed,540,720),(e,720,1440)])
        s.employee(self.store,e['id'])['availability'][W]['windows']=[{'start':360,'end':1440}]
        self.assertFalse(self.report()['shifts'][0]['choices'])

    def test_overnight_availability_projected_to_next_date_and_off_override(self):
        e=self.add('Night',status='unknown'); person=s.employee(self.store,e['id'])
        person['availability'][W]={'status':'available','windows':[{'start':1320,'end':1560}]}
        cfg=s.book(self.store)['settings']; cfg['operating_hours']={'weekdays':{str(i):{'mode':'24h','before_minutes':0,'after_minutes':0} for i in range(7)},'date_overrides':{},'closures':[]}
        self.day([(self.departed,0,120)],'2026-09-14')
        self.assertEqual(120,self.report()['shifts'][0]['choices'][0]['covered_work_minutes'])
        person['availability']['2026-09-14']['status']='off'
        self.assertFalse(self.report()['shifts'][0]['choices'])

    def test_week_totals_reset_and_source_hash_is_actual_input(self):
        e=self.add('Available'); person=s.employee(self.store,e['id'])
        person['availability']['2026-09-20']={'status':'available','windows':[{'start':360,'end':1380}]}
        self.day([(self.departed,540,1020)]); self.day([(e,540,1020)],'2026-09-14'); self.day([(self.departed,540,1020)],'2026-09-20')
        self.cap(e,960)
        expected=s.stamp({'staffing':s.book(self.store),'schedules':d.book(self.store)})
        r=self.report(); self.assertEqual(expected,r['source_sha256'])
        self.assertEqual([480,0],[x['choices'][0]['current_week_minutes'] for x in r['shifts']])

    def test_day_navigation_rejects_a_different_business(self):
        self.day([(self.departed,540,1020)])
        http=server.make_server(self.store.path,0); threading.Thread(target=http.serve_forever,daemon=True).start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        before=copy.deepcopy(http.app.store.data)
        body={'date':W,'expected_team_id':'business-from-a-stale-coverage-panel'}
        req=Request('http://127.0.0.1:'+str(http.server_port)+'/api/staff/day',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-ShiftBrief-Token':http.app.token})
        with self.assertRaises(HTTPError) as caught: urlopen(req,timeout=10)
        self.assertEqual(400,caught.exception.code)
        self.assertIn('business changed',caught.exception.read().decode())
        caught.exception.close()
        self.assertEqual(before,http.app.store.data)

    def test_report_failure_after_end_returns_saved_error_not_false_failure(self):
        self.day([(self.departed,540,1020)])
        http=server.make_server(self.store.path,0); threading.Thread(target=http.serve_forever,daemon=True).start()
        self.addCleanup(http.server_close); self.addCleanup(http.shutdown)
        body={'employee_id':self.departed['id'],'date':W,'expected_team_id':self.store.production_id,'expected_revision':self.departed.get('revision',1)}
        req=Request('http://127.0.0.1:'+str(http.server_port)+'/api/staff/end',data=json.dumps(body).encode(),headers={'Content-Type':'application/json','X-ShiftBrief-Token':http.app.token})
        with patch.object(c,'analyze',side_effect=ValueError('fixture calculation error')):
            with urlopen(req,timeout=10) as response: result=json.load(response)
        self.assertEqual(W,result['end_date']); self.assertIn('saved',result['departure_coverage_error'])
        self.assertEqual(W,s.employee(http.app.store,self.departed['id'])['end_date'])

if __name__=='__main__': unittest.main(verbosity=2)
