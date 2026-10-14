import importlib
import json
import unittest
from unittest.mock import AsyncMock
from test_client import Response, HTTP
from support import client

auth=importlib.import_module('bge_test_component.auth')

class AuthHTTP(HTTP):
    def get(self,url,**kwargs):return self.request('GET',url,**kwargs)
    def post(self,url,**kwargs):return self.request('POST',url,**kwargs)

def bootstrap():
    payload={'props':{'initialReduxState':{'envVars':{'digitalApiKey':'synthetic-client-key'}}}}
    return Response(raw=('<html><script id="__NEXT_DATA__" type="application/json">'+json.dumps(payload)+'</script></html>').encode())

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_password_login_omits_captcha_and_does_not_log_secrets(self):
        http=AuthHTTP([bootstrap(),Response(data={'accessToken':'private-access','refreshToken':'private-refresh'})])
        reserve=AsyncMock()
        with self.assertLogs(auth._LOGGER,level='DEBUG') as logs:
            session=await auth.password_login(http,' PRIVATE-EMAIL@example.test ','private-password',reserve)
        reserve.assert_awaited_once_with('private-email@example.test')
        self.assertEqual(session['accessToken'],'private-access')
        self.assertEqual(len(http.calls),2)
        headers=http.calls[1][2]['headers'];self.assertNotIn('captcha',headers)
        self.assertEqual(http.calls[1][2]['json']['password'],'private-password')
        self.assertFalse(http.calls[1][2]['allow_redirects'])
        combined=' '.join(logs.output)
        for secret in ['private-email','private-password','private-access','private-refresh','synthetic-client-key',session['anonymousId']]:self.assertNotIn(secret,combined)
    async def test_captcha_rejection_logged_without_body_and_no_retry(self):
        http=AuthHTTP([bootstrap(),Response(400,data={'message':'CAPTCHA required private-secret'})])
        with self.assertLogs(auth._LOGGER,level='WARNING') as logs:
            with self.assertRaisesRegex(client.PortalError,'browser_verification_required'):
                await auth.password_login(http,'user@example.test','private-password',AsyncMock())
        self.assertEqual(len(http.calls),2);self.assertNotIn('private-secret',' '.join(logs.output))
    async def test_generic_rejection_does_not_claim_captcha(self):
        http=AuthHTTP([bootstrap(),Response(401,data={'message':'private-secret'})])
        with self.assertLogs(auth._LOGGER,level='WARNING'):
            with self.assertRaisesRegex(client.PortalError,'login_rejected'):
                await auth.password_login(http,'user@example.test','password',AsyncMock())
    async def test_otp_is_not_mistaken_for_session(self):
        http=AuthHTTP([bootstrap(),Response(data={'state':'otp','tempToken':'private-temp'})])
        with self.assertLogs(auth._LOGGER,level='WARNING') as logs:
            with self.assertRaisesRegex(client.PortalError,'otp_required'):
                await auth.password_login(http,'user@example.test','password',AsyncMock())
        self.assertNotIn('private-temp',' '.join(logs.output))
    async def test_budget_rejection_sends_no_network_requests(self):
        http=AuthHTTP([])
        with self.assertRaisesRegex(client.PortalError,'login_cooldown'):
            await auth.password_login(http,'user@example.test','password',AsyncMock(side_effect=client.PortalError('login_cooldown')))
        self.assertEqual(http.calls,[])
    async def test_changed_bootstrap_stops_before_password_submission(self):
        http=AuthHTTP([Response(raw=b'<html>No expected config</html>')])
        with self.assertRaisesRegex(client.PortalError,'login_page_changed'):
            await auth.password_login(http,'user@example.test','password',AsyncMock())
        self.assertEqual(len(http.calls),1)

if __name__=='__main__':unittest.main()
