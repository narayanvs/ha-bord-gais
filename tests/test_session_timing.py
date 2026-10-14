import base64,importlib,json,unittest
from support import client
m=importlib.import_module('bge_test_component.session_timing')
def jwt(exp):
 return 'header.'+base64.urlsafe_b64encode(json.dumps({'exp':exp}).encode()).decode().rstrip('=')+'.signature'
class Timing(unittest.TestCase):
 def test_short_refresh_renewed_before_expiry(self):
  self.assertEqual(m.renewal_delay({'refreshToken':jwt(1901)},1000),600)
 def test_about_to_expire_renews_with_margin(self):
  self.assertEqual(m.renewal_delay({'refreshToken':jwt(1050)},1000),25)
 def test_expired_requests_reauth(self):
  self.assertEqual(m.renewal_delay({'refreshToken':jwt(999)},1000),0)
 def test_opaque_has_bounded_fallback(self):
  self.assertEqual(m.renewal_delay({'refreshToken':'opaque'},1000),600)
 def test_invalid_claims_not_trusted(self):
  for exp in [True,'1000',None,float('inf')]:self.assertIsNone(m.token_expiry(jwt(exp)))
class Renewal(unittest.IsolatedAsyncioTestCase):
 async def test_renewal_is_one_request_and_persists_rotation(self):
  from test_client import HTTP,Response
  saved=[]
  async def persist(session):saved.append(session)
  http=HTTP([Response(data={'accessToken':'new-access','refreshToken':'new-refresh'})])
  c=client.BGEClient(http,{'accessToken':'old-access','refreshToken':'old-refresh','anonymousId':'synthetic-anonymous'},persist)
  await c.renew_session()
  self.assertEqual(len(http.calls),1)
  self.assertEqual(http.calls[0][0],'POST')
  self.assertTrue(http.calls[0][1].endswith('/api/auth/refresh-token'))
  self.assertEqual(saved[0]['refreshToken'],'new-refresh')
