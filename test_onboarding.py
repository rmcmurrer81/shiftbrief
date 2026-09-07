import tempfile,unittest
from briefing import Store
from sarah_local import ask,confirm,run_local

class OnboardingTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.store=Store(self.temp.name)
 def test_starting_questions_before_documents(self):
  for message in ['hello','where should we start','Tell me about yourself','What can you do?','How can I start?','Help me begin']:
   with self.subTest(message=message):
    response=ask(self.store,message);self.assertEqual('onboarding',response['kind']);self.assertIn('first real detail',response['answer']);self.assertEqual([],response['evidence'])
  self.assertEqual([],self.store.view()['documents'])
 def test_exact_owner_note_review_save_and_actual_handoff(self):
  text='Location: south loading entrance\nDelivery confirmation: not received.'
  response=ask(self.store,'Save a note titled Morning setup: '+text);p=response['proposal'];self.assertEqual([],self.store.view()['documents']);self.assertEqual(text,p['text'])
  with self.assertRaises(ValueError):confirm(self.store,p['id'],p['sha256'],'yes')
  result=confirm(self.store,p['id'],p['sha256'],'YES');doc=self.store.document(result['document_id']);self.assertEqual(text.splitlines(),[line['text'] for line in doc['revisions'][0]['lines']]);self.assertEqual('owner_words_confirmed_in_sarah_chat',doc['revisions'][0]['origin']);self.assertEqual('none',run_local(self.store)['model'])
  with self.assertRaises(ValueError):confirm(self.store,p['id'],p['sha256'],'YES')
 def test_note_proposal_stale_and_production_isolation(self):
  p=ask(self.store,'Save a note: Parking information is not confirmed.')['proposal'];self.store.import_document('New evidence','new.txt',b'Parking: confirmed by owner')
  with self.assertRaises(ValueError):confirm(self.store,p['id'],p['sha256'],'YES')
  self.store.create_production('Separate shoot');self.assertEqual([],self.store.view()['documents']);self.assertEqual([],self.store.view()['assistant']['messages'])
 def test_unclear_start_kept_in_chat_without_inventing_a_source(self):
  message='I am trying to organize tomorrow but I am not ready yet.';result=ask(self.store,message);self.assertEqual('onboarding',result['kind']);self.assertIsNone(result['proposal']);self.assertEqual([],self.store.view()['documents']);self.assertEqual(message,self.store.view()['assistant']['messages'][0]['text'])

if __name__=='__main__':unittest.main()
