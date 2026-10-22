import unittest
from hunter.persist import choose,merge_enrichment
class PersistTests(unittest.TestCase):
    def test_stale_halt_refresh_cannot_replace_new_full_scan(self):
        new={'updated_at':'2026-10-22T12:00:00Z','ranking_updated_at':'2026-10-22T12:00:00Z','verification_summary':{'evaluated':5000}}
        stale={'updated_at':'2026-10-21T12:00:00Z','ranking_updated_at':'2026-10-22T12:05:00Z'}
        self.assertIs(choose('public/data.json',new,stale),new)
    def test_newer_halt_rerank_of_same_scan_wins(self):
        a={'updated_at':'2026-10-22T12:00:00Z','ranking_updated_at':'2026-10-22T12:00:00Z'};b={**a,'ranking_updated_at':'2026-10-22T12:05:00Z'}
        self.assertIs(choose('public/data.json',a,b),b)
    def test_new_scan_wins_over_stale_snapshot(self):
        a={'updated_at':'2026-10-21T12:00:00Z'};b={'updated_at':'2026-10-22T12:00:00Z'}
        self.assertIs(choose('public/data.json',a,b),b)
    def test_enrichment_preserves_newest_and_both_histories(self):
        a={'symbols':{'INLF':{'observed_at':'2026-10-22T12:00:00Z','borrow':{'ctb':50},'borrow_history':[{'as_of':'2026-10-22T11:00:00Z'}]}}};b={'symbols':{'INLF':{'observed_at':'2026-10-22T11:00:00Z','borrow':{'ctb':40},'borrow_history':[{'as_of':'2026-10-22T10:00:00Z'}]}}}
        c=merge_enrichment(a,b)['symbols']['INLF'];self.assertEqual(c['borrow']['ctb'],50);self.assertEqual(len(c['borrow_history']),2)
