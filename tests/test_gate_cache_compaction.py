import unittest,time
from app.gate_repair_policy import compact_gate_result,repeated_editorial_failure
class CacheTests(unittest.TestCase):
 def test_compact_removes_recursive_snapshots(self):
  old={'key':'content_gate','score':58,'before':{'score':57,'before':{'score':1}},'after':{'score':58,'rounds':[1]},'rounds':[{'round':1,'before':{'x':1}}]}
  out=compact_gate_result(old)
  self.assertNotIn('before',out['before']);self.assertNotIn('rounds',out['after']);self.assertNotIn('before',out['rounds'][0])
 def test_timeout_action_can_retry_without_active_cooldown(self):
  self.assertFalse(repeated_editorial_failure({'cache_hit':True,'actions':['自动修复失败：Request timed out.'],'editorial_attempted':True}))
 def test_successful_failed_quality_is_locked(self):
  self.assertTrue(repeated_editorial_failure({'cache_hit':True,'actions':['DeepSeek 总编改稿并复检'],'reassessment_completed':True}))
if __name__=='__main__':unittest.main()
