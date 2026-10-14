import json
import base64
import unittest
from unittest.mock import AsyncMock
from support import client

SESSION = {'accessToken':'synthetic-access','refreshToken':'synthetic-refresh','anonymousId':'a'*32}

class Response:
    def __init__(self, status=200, data=None, raw=None):
        self.status=status
        self.raw=raw if raw is not None else json.dumps(data).encode()
        self.headers={'Content-Type':'application/json'}
        self.content=self
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def iter_chunked(self,n):
        for i in range(0,len(self.raw),7):yield self.raw[i:i+7]

class HTTP:
    def __init__(self,responses):self.responses=list(responses);self.calls=[]
    def request(self,method,url,**kwargs):
        self.calls.append((method,url,kwargs))
        if not self.responses:raise AssertionError('Unexpected additional HTTP request')
        return self.responses.pop(0)

def account_listing():return Response(data={'content':[{'accountId':'synthetic-account'}],'totalElements':1})
def details():return Response(data={'account':{'accountId':'synthetic-account','serviceType':'EL','balance':-12.50},'lastBill':{'billId':'synthetic-bill','amount':-12.50}})
def transactions():return Response(data=[{'billId':'synthetic-bill','type':'Bill','transactionType':'Bill','billAmount':7.25}])

class Tests(unittest.IsolatedAsyncioTestCase):
    async def test_read_only_fetch_chunked_json(self):
        http=HTTP([account_listing(),details(),transactions(),Response(data={'items':[]})]);data=await client.BGEClient(http,SESSION).fetch()
        value=next(iter(data.values()))
        self.assertEqual(value['account_credit'],12.5);self.assertEqual(value['latest_bill_charge'],7.25)
        self.assertNotIn('synthetic-account',json.dumps(data));self.assertNotIn('synthetic-access',json.dumps(data))
        for method,url,kw in http.calls:
            self.assertEqual(method,'GET');self.assertFalse(kw['allow_redirects'])
            self.assertEqual(kw['headers']['AnonymousId'],'a'*32);self.assertTrue(kw['params']['cache'].isdigit())
    async def test_refresh_rotation_persisted_before_retry(self):
        http=HTTP([Response(401),Response(data={'accessToken':'new-access','refreshToken':'new-refresh'}),account_listing(),details(),transactions(),Response(data={'items':[]})])
        async def save(session):
            self.assertEqual(len(http.calls),2)
            self.assertEqual(session['refreshToken'],'new-refresh')
        persist=AsyncMock(side_effect=save)
        await client.BGEClient(http,SESSION,persist).fetch();persist.assert_awaited_once()
        self.assertEqual(http.calls[2][2]['headers']['Authorization'],'Bearer new-access')
    async def test_expired_jwt_refreshes_before_first_read(self):
        payload = base64.urlsafe_b64encode(json.dumps({'exp': 1}).encode()).decode().rstrip('=')
        session = {**SESSION, 'accessToken': 'synthetic.' + payload + '.synthetic'}
        http = HTTP([Response(data={'accessToken':'new-access','refreshToken':'new-refresh'}),account_listing(),details(),transactions(),Response(data={'items':[]})])
        await client.BGEClient(http,session).fetch()
        self.assertEqual(http.calls[0][0],'POST')
        self.assertTrue(http.calls[0][1].endswith('/api/auth/refresh-token'))

    async def test_known_expired_identifier_response_refreshes_once(self):
        http = HTTP([Response(400,data={'code':'BAD_REQUEST','message':'The request identifier is invalid or not provided.'}),Response(data={'accessToken':'new-access','refreshToken':'new-refresh'}),account_listing(),details(),transactions(),Response(data={'items':[]})])
        await client.BGEClient(http,SESSION).fetch()
        self.assertEqual(sum(method=='POST' for method,url,kw in http.calls),1)

    async def test_rate_limit_does_not_retry_or_require_reauth(self):
        http=HTTP([Response(429)])
        with self.assertRaisesRegex(client.PortalError,'rate_limited') as caught:await client.BGEClient(http,SESSION).fetch()
        self.assertNotIsInstance(caught.exception,client.AuthError);self.assertEqual(len(http.calls),1)
    async def test_refresh_rate_limit_is_not_invalid_credentials(self):
        http=HTTP([Response(401),Response(429)])
        with self.assertRaisesRegex(client.PortalError,'rate_limited') as caught:await client.BGEClient(http,SESSION).fetch()
        self.assertNotIsInstance(caught.exception,client.AuthError)
    async def test_expired_refresh_no_retry_loop(self):
        http=HTTP([Response(401),Response(401)])
        with self.assertRaises(client.AuthError):await client.BGEClient(http,SESSION).fetch()
        self.assertEqual(len(http.calls),2)
    async def test_optional_transaction_failure_preserves_balance(self):
        http=HTTP([account_listing(),details(),Response(500),Response(data={'items':[]})])
        value=next(iter((await client.BGEClient(http,SESSION).fetch()).values()))
        self.assertEqual(value['account_credit'],12.5);self.assertIsNone(value['latest_bill_charge']);self.assertFalse(value['transactions_available'])
    async def test_unexpected_pagination_rejected(self):
        http=HTTP([Response(data={'content':[{'accountId':'synthetic-account'}],'totalElements':2})])
        with self.assertRaisesRegex(client.PortalError,'pagination_required'):await client.BGEClient(http,SESSION).fetch()
    async def test_wrong_account_details_rejected(self):
        http=HTTP([account_listing(),Response(data={'account':{'accountId':'other'}})])
        with self.assertRaisesRegex(client.PortalError,'account_mismatch'):await client.BGEClient(http,SESSION).fetch()
    async def test_payments_and_redirects_not_allowed(self):
        c=client.BGEClient(HTTP([]),SESSION)
        with self.assertRaisesRegex(client.PortalError,'forbidden_endpoint'):await c._request('/api/payments/v1/accounts/synthetic')
        c=client.BGEClient(HTTP([Response(302,raw=b'private redirect details')]),SESSION)
        with self.assertRaisesRegex(client.PortalError,'portal_http_error') as e:await c._read('/api/accounts/')
        self.assertNotIn('private',str(e.exception))
    async def test_malformed_session_does_not_echo_data(self):
        for v in ['private-secret',{}, {'accessToken':'x','refreshToken':'y','anonymousId':'../private-secret'}]:
            with self.assertRaisesRegex(client.PortalError,'invalid_session') as e:client.parse_session(v)
            self.assertNotIn('private-secret',str(e.exception))

if __name__=='__main__':unittest.main()
