import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.gate_repair_policy import needs_sentence_split,repeated_editorial_failure
class GatePolicyTests(unittest.TestCase):
    def test_information_not_splitting(self):
        self.assertFalse(needs_sentence_split({'issues':[{'where':'观众收获'},{'where':'中段留存'}]}))
    def test_long_sentence(self):
        self.assertTrue(needs_sentence_split({'issues':[{'where':'口播句长'}]}))
    def test_unchanged_failure(self):
        self.assertTrue(repeated_editorial_failure({'cache_hit':True,'passed':False,'actions':['DeepSeek 总编改稿并复检'],'reassessment_completed':True}))
    def test_changed_input(self):
        self.assertFalse(repeated_editorial_failure({'cache_hit':False,'passed':False,'editorial_attempted':True}))
    def test_first_failure(self):
        self.assertFalse(repeated_editorial_failure({'cache_hit':True,'passed':False}))
    def test_passed(self):
        self.assertFalse(repeated_editorial_failure({'cache_hit':True,'passed':True,'editorial_attempted':True}))
if __name__=='__main__':unittest.main()

