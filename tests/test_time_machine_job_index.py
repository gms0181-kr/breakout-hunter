import json,tempfile,unittest
from pathlib import Path
from scripts.build_time_machine_job_index import build_index

class CompletedJobIndexTests(unittest.TestCase):
    def fixture(self):
        return {'job':{'id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa','et':'2026-10-12T14:00','scope':'all'},'as_of':'2026-10-12T18:00:00Z','retrieved_at':'2026-10-23T18:00:00Z','result':{'mode':'all','engine_hash':'test-hash','acquisition_mode':'HISTORICAL RECONSTRUCTION','status':'PARTIAL REPLAY','top20':[]}}
    def test_completed_lookup_keeps_request_identity_without_scoring(self):
        with tempfile.TemporaryDirectory() as root:
            folder=Path(root)/'time-machine/jobs';folder.mkdir(parents=True);r=self.fixture();(folder/(r['job']['id']+'.json')).write_text(json.dumps(r))
            index=build_index(root,'test-hash');self.assertEqual(len(index['jobs']),1);self.assertEqual(index['jobs'][0]['et'],'2026-10-12T14:00');self.assertIn('never a new collection',index['purpose'])
    def test_wrong_date_scope_engine_and_non_uuid_paths_are_excluded(self):
        for change in [lambda r:r['job'].update(et='2026-10-15T12:00'),lambda r:r['result'].update(mode='china'),lambda r:r['result'].update(engine_hash='other')]:
            with self.subTest(change=change),tempfile.TemporaryDirectory() as root:
                folder=Path(root)/'time-machine/jobs';folder.mkdir(parents=True);r=self.fixture();change(r);(folder/(r['job']['id']+'.json')).write_text(json.dumps(r));index=build_index(root,'test-hash');self.assertEqual(index['jobs'],[]);self.assertEqual(index['rejected_reports'],1)
