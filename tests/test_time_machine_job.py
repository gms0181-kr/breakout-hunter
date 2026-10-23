import unittest,uuid
from datetime import datetime,timezone
from unittest.mock import patch
from hunter.time_machine_job import validate_job,execute
from tests.test_time_machine_reconstruct import FakeClient

class TimeMachineJobTests(unittest.IsolatedAsyncioTestCase):
 async def test_each_date_runs_external_queries_and_has_distinct_identity(self):
  seen=[]
  for et in ['2026-10-12T14:00','2026-10-15T12:00']:
   client=FakeClient();identifier=str(uuid.uuid4());r=await execute(identifier,et,'all',client)
   self.assertEqual(r['job']['id'],identifier);self.assertEqual(r['job']['et'],et);self.assertFalse(r['job']['cache_reused']);self.assertTrue(client.requests)
   self.assertTrue(any(p.get('end')==r['as_of'] for u,p in client.requests));seen.append((r['as_of'],r['job']['id']))
  self.assertNotEqual(*[x[0] for x in seen]);self.assertNotEqual(*[x[1] for x in seen])
 async def test_invalid_job_path_future_and_scope_rejected(self):
  for identifier,et,scope in [('../latest','2026-10-15T12:00','all'),(str(uuid.uuid4()),'2099-10-15T12:00','all'),(str(uuid.uuid4()),'2026-10-15T12:00','admin')]:
   with self.assertRaises(ValueError):validate_job(identifier,et,scope)
