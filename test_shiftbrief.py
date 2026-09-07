import json, tempfile, threading, unittest, urllib.request, urllib.error
from pathlib import Path
from briefing import Store, load_sample, update_packet, citation_index
from server import make_server
from agent import run_agent

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(self.temp.name)
        load_sample(self.store)
    def rows(self,snapshot=None):
        snap=snapshot or self.store.snapshot();doc=snap['documents'][0];rev=doc['revisions'][-1];line=rev['lines'][1]
        return [{'text':'Crew call changed; confirm transport pickup.','evidence':[{'ref':f"{doc['id']}:r{rev['number']}:L{line['line']}",'quote':line['text']}]}]
    def save(self):
        return self.store.save_briefing(self.store.snapshot(),'Next shift',self.rows(),self.rows(),['Confirm destination with transport.'],[])
    def test_productions_keep_sources_and_handoffs_separate(self):
        original=self.store.production_id;b=self.save();doc=self.store.snapshot()['documents'][0]
        new=self.store.create_production('My real production')
        self.assertEqual([],self.store.snapshot()['documents']);self.assertEqual([],self.store.view()['briefings'])
        with self.assertRaises(ValueError):self.store.import_document('','updated.txt',b'Wrong project',doc['id'])
        with self.assertRaises(ValueError):self.store.export(b['id'])
        self.store.import_document('Real notes','notes.txt',b'Crew call 10:00')
        self.store.select_production(original)
        self.assertEqual(2,len(self.store.snapshot()['documents']));self.assertFalse(self.store.view()['briefings'][0]['outdated'])
        restored=Store(self.temp.name);self.assertEqual(original,restored.production_id)
        restored.select_production(new['id']);self.assertEqual(1,len(restored.snapshot()['documents']))

    def test_runtime_configuration_is_local_and_records_actual_model(self):
        from unittest.mock import patch
        from agent import runtime_settings
        with patch.dict('os.environ',{'SHIFTBRIEF_OLLAMA_URL':'http://localhost:12345','SHIFTBRIEF_MODEL':'installed-test-model'}):
            self.assertEqual({'url':'http://localhost:12345','model':'installed-test-model'},runtime_settings())
        with patch.dict('os.environ',{'SHIFTBRIEF_OLLAMA_URL':'https://example.com'}):
            with self.assertRaises(ValueError):runtime_settings()

    def test_revisions_and_restart(self):
        snap=self.store.snapshot();self.assertEqual(2,len(snap['documents'][0]['revisions']))
        packets=[update_packet(x) for x in snap['documents']];self.assertTrue(any('Crew call: 08:30' in c['after'] for c in packets[0]['changes']))
        self.assertEqual(snap,Store(self.temp.name).snapshot())
    def test_duplicate_does_not_stale(self):
        snap=self.store.snapshot();doc=snap['documents'][0];rev=doc['revisions'][-1]
        result=self.store.import_document('',rev['filename'],'\n'.join(x['text'] for x in rev['lines']).encode(),doc['id'])
        self.assertTrue(result['unchanged']);self.assertEqual(snap,self.store.snapshot())
    def test_fake_quote_rejected(self):
        rows=self.rows();rows[0]['evidence'][0]['quote']='Crew call: 06:00'
        with self.assertRaisesRegex(ValueError,'exactly quote'):self.store.save_briefing(self.store.snapshot(),'Bad',rows,[],[],[])
        self.assertEqual([],self.store.data['briefings'])
    def test_source_change_during_agent_rejected(self):
        snap=self.store.snapshot();self.store.import_document('Weather','weather.txt',b'Rain.')
        with self.assertRaisesRegex(ValueError,'changed while'):self.store.save_briefing(snap,'Stale',self.rows(snap),[],[],[])
    def test_checklist_export_and_staleness(self):
        b=self.save();self.store.set_decision(b['id'],b['decisions'][0]['id'],True)
        self.assertIn('- [x]',self.store.export(b['id']))
        self.store.import_document('Weather','weather.txt',b'Rain.')
        self.assertIn('OUTDATED',self.store.export(b['id']))
        with self.assertRaisesRegex(ValueError,'outdated'):self.store.set_decision(b['id'],b['decisions'][0]['id'],False)
    def test_watch_reads_only_chosen_file_and_pauses(self):
        chosen=Path(self.temp.name)/'chosen.txt';other=Path(self.temp.name)/'unselected.txt';chosen.write_text('Call 09:00');other.write_text('PRIVATE UNSELECTED')
        watch=self.store.watch_file(str(chosen),'Chosen');chosen.write_text('Call 10:00');self.store.refresh_watches()
        doc=self.store.document(watch['document_id']);self.assertEqual(2,len(doc['revisions']));self.assertNotIn('PRIVATE',json.dumps(self.store.data))
        self.store.toggle_watch(watch['id'],False);chosen.write_text('Call 11:00');self.store.refresh_watches();self.assertEqual(2,len(doc['revisions']))
    def test_real_strands_decorated_tool_boundary_with_fake_model(self):
        def factory(tools,system_prompt):
            def agent(prompt):
                packet=tools[0]();self.assertEqual(2,len(packet['documents']))
                doc=packet['documents'][0];line=doc['revisions'][-1]['lines'][1]
                rows=[{'text':'Confirm revised crew call.','evidence':[{'ref':line['ref'],'quote':line['text']}]}]
                result=tools[1](headline='Harbor handoff',findings=rows,decisions=rows,open_questions=['Confirm transport.'])
                self.assertTrue(result['saved'])
            return agent
        b=run_agent(self.store,agent_factory=factory)
        self.assertEqual(['read_updates','save_shift_brief'],[x['tool'] for x in b['trace']])
        self.assertFalse(b['decisions'][0]['done'])
    def test_sample_button_is_idempotent(self):
        snapshot=self.store.snapshot();load_sample(self.store);self.assertEqual(snapshot,self.store.snapshot())
    def test_pdf_import_retains_page_and_exact_text(self):
        import io
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(612,792)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 740 Td (Crew call: 08:30) Tj ET');page[NameObject('/Contents')]=writer._add_object(stream)
        buf=io.BytesIO();writer.write(buf);result=self.store.import_document('PDF call sheet','call.pdf',buf.getvalue());line=self.store.document(result['document_id'])['revisions'][0]['lines'][0]
        self.assertEqual(1,line['page']);self.assertEqual('Crew call: 08:30',line['text'])
    def test_repeated_line_comparison_has_exact_change_positions(self):
        result=self.store.import_document('Repeats','a.txt',b'A\nB\nA\n')
        self.store.import_document('','b.txt',b'A\nA\nB\n',result['document_id'])
        packet=next(x for x in self.store.view()['comparisons'] if x['document_id']==result['document_id'])
        self.assertTrue(packet['changes']);self.assertTrue(all('before_start' in x and 'after_start' in x for x in packet['changes']))
    def test_unsupported_and_empty_import(self):
        for name,raw in [('a.exe',b'foo'),('a.txt',b'')]:
            with self.assertRaises(ValueError):self.store.import_document('Bad',name,raw)

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.server=make_server(self.temp.name,0);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='http://127.0.0.1:'+str(self.server.server_port);self.token=self.get('/api/state')['token']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.temp.cleanup()
    def get(self,path):
        return json.load(urllib.request.urlopen(self.base+path))
    def post(self,path,body,token=True,origin=None):
        headers={'Content-Type':'application/json'}
        if token:headers['X-ShiftBrief-Token']=self.token
        if origin:headers['Origin']=origin
        return json.load(urllib.request.urlopen(urllib.request.Request(self.base+path,json.dumps(body).encode(),headers)))
    def test_live_http_import_and_duplicate(self):
        a=self.post('/api/import',{'title':'Day1','text':'Call 08:00'});b=self.post('/api/import',{'document_id':a['document_id'],'text':'Call 09:00'})
        self.assertFalse(b['unchanged']);self.assertEqual(2,len(self.get('/api/state')['state']['documents'][0]['revisions']))
    def test_cross_origin_and_missing_token_rejected(self):
        for token,origin in [(False,None),(True,'https://example.com')]:
            with self.assertRaises(urllib.error.HTTPError):self.post('/api/sample',{},token,origin)
        self.assertEqual([],self.get('/api/state')['state']['documents'])
    def test_example_is_separate_from_real_production_and_switching_is_persisted(self):
        original=self.get('/api/state')['state']['current_production']
        self.post('/api/import',{'title':'My real notes','text':'Do not include in example'})
        self.post('/api/sample',{})
        sample=self.get('/api/state')['state'];self.assertNotEqual(original,sample['current_production']);self.assertEqual(2,len(sample['documents']))
        self.post('/api/sample',{});self.assertEqual(2,len(self.get('/api/state')['state']['documents']))
        self.post('/api/production/select',{'id':original});self.assertEqual('My real notes',self.get('/api/state')['state']['documents'][0]['title'])
        self.server.app.jobs['test']={'id':'test','production_id':original,'status':'running'}
        with self.assertRaises(urllib.error.HTTPError):self.post('/api/production/create',{'title':'Cannot interrupt agent'})
        self.assertEqual(original,self.get('/api/state')['state']['current_production'])

    def test_arbitrary_file_path_not_served(self):
        with self.assertRaises(urllib.error.HTTPError):self.get('/../briefing.py')

if __name__=='__main__':unittest.main()
