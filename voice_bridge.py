"""Optional approved CPU voice pack bridge; no model downloads or cloud calls."""
from pathlib import Path
import atexit,base64,hashlib,threading
from sarah_voice_client import discover_pack,SarahVoiceClient,VoiceUnavailable

class AppVoice:
 def __init__(self,app_directory,voice_id):self.base=Path(app_directory);self.voice_id=voice_id;self.client=None;self.lock=threading.Lock();atexit.register(self.close)
 def status(self):return {'available':discover_pack(self.base) is not None,'voice_id':self.voice_id,'mode':'optional approved CPU voice pack'}
 def speak(self,text):
  if not isinstance(text,str) or not text.strip() or len(text)>400 or len(text.split())>65:raise ValueError('Speak a nonempty chunk of at most 400 characters and 65 words.')
  with self.lock:
   if self.client is None:
    root=discover_pack(self.base)
    if root is None:raise ValueError('Sarah’s optional voice pack is not beside this app yet. Written conversation remains available.')
    self.client=SarahVoiceClient(root)
   try:result=self.client.speak(self.voice_id,text)
   except VoiceUnavailable as exc:raise ValueError(str(exc)) from exc
   data=Path(result['wav_path']).read_bytes()
   if hashlib.sha256(data).hexdigest()!=result['sha256']:raise ValueError('The generated voice file changed before playback. Try again.')
   return {'audio_base64':base64.b64encode(data).decode(),'mime_type':'audio/wav','sha256':result['sha256'],'seconds':result['seconds'],'text':text,'voice_id':self.voice_id,'cached':result.get('cached',False)}
 def close(self):
  if self.client:self.client.close();self.client=None
