import unittest
from types import SimpleNamespace as N
from unittest.mock import Mock
from app.editor_stream import request_editor_stream
class StreamTests(unittest.TestCase):
 def run_stream(self,finish):
  chunk=N(choices=[N(index=0,delta=N(content='# 稿子',reasoning_content='thinking'),finish_reason=finish)])
  stream=Mock();stream.__iter__=Mock(return_value=iter([chunk]));client=Mock();client.chat.completions.create.return_value=stream
  return client,stream
 def test_complete(self):
  c,s=self.run_stream('stop');r=request_editor_stream(c,model='test');self.assertEqual(r.choices[0].message.content,'# 稿子');s.close.assert_called_once()
 def test_disconnect(self):
  c,s=self.run_stream(None)
  with self.assertRaisesRegex(RuntimeError,'提前断开'):request_editor_stream(c,model='test')
  s.close.assert_called_once()
if __name__=='__main__':unittest.main()
