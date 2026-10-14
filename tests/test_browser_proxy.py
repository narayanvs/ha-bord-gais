import importlib.util
import pathlib
import unittest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from support import client
import importlib
m=importlib.import_module('bge_test_component.browser_proxy')

class Rules(unittest.TestCase):
 def test_allowlist(self):
  for method,path in [('POST','/api/accounts/'),('POST','/api/payments'),('GET','/api/accounts/'),('DELETE','/sign-in'),('GET','//attacker.example/')]:
   self.assertFalse(m.allowed(method,path))
  self.assertTrue(m.allowed('POST','/api/auth/token'))
  self.assertTrue(m.allowed('GET','/_next/static/script.js'))
 def test_private_only(self):
  for host in ['example.org','8.8.8.8','127.0.0.1','0.0.0.0']:
   with self.assertRaises(ValueError):m.BrowserLogin(host,None)
 def test_rewrite(self):
  origin='https://192.168.1.2:8743'
  self.assertEqual(m.rewrite(m.BASE+'/api/auth/token',origin),origin+'/api/auth/token')
  self.assertEqual(m.rewrite('https://www.google.com/recaptcha/api.js',origin),'https://www.google.com/recaptcha/api.js')
 def test_safe_category(self):
  self.assertEqual(m.category(400,{'message':'CAPTCHA failed for private@example.org'}),'captcha_required_or_rejected')

class Certificates(unittest.IsolatedAsyncioTestCase):
 async def test_temporary_key_permissions_and_cleanup(self):
  from cryptography import x509
  import os
  folder,cert,key=await __import__('asyncio').to_thread(m.make_certificate,'192.168.1.2')
  root=pathlib.Path(folder.name)
  self.assertEqual(os.stat(key).st_mode & 0o777,0o600)
  loaded=x509.load_pem_x509_certificate(cert.read_bytes())
  names=loaded.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
  self.assertEqual(str(names.get_values_for_type(x509.IPAddress)[0]),'192.168.1.2')
  trial=m.BrowserLogin('192.168.1.2',None);trial.certificate=folder
  cleared=[]
  trial.on_close=lambda:cleared.append(True)
  await trial.close()
  self.assertFalse(root.exists())
  self.assertEqual(cleared,[True])
  self.assertIsNone(trial.on_complete)
  await trial.close()
  self.assertEqual(cleared,[True])

class Requests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.trial=m.BrowserLogin('192.168.1.2',None)
  app=web.Application()
  app.router.add_route('*','/{tail:.*}',self.trial.handle)
  self.client=TestClient(TestServer(app))
  await self.client.start_server()
  self.headers={'Host':'192.168.1.2:8743','Cookie':m.COOKIE+'='+self.trial.cookie}
 async def asyncTearDown(self):await self.client.close()
 async def test_requires_cookie(self):
  r=await self.client.get('/sign-in',headers={'Host':'192.168.1.2:8743'})
  self.assertEqual(r.status,403)
 async def test_wrong_host(self):
  r=await self.client.get('/trial-result',headers={**self.headers,'Host':'attacker.example'})
  self.assertEqual(r.status,403)
 async def test_api_blocked(self):
  r=await self.client.get('/api/accounts/',headers=self.headers)
  self.assertEqual(r.status,403)
 async def test_csrf_blocked(self):
  r=await self.client.post('/api/auth/token',headers={**self.headers,'Origin':'https://attacker.example'},json={'password':'synthetic'})
  self.assertEqual(r.status,403)
 async def test_safe_status(self):
  r=await self.client.get('/trial-result',headers=self.headers)
  self.assertEqual(await r.json(),{'state':'waiting','attempts':0})
 async def test_expiry(self):
  self.trial.deadline=0
  r=await self.client.get('/trial-result',headers=self.headers)
  self.assertEqual(r.status,403)
 async def test_one_use_start(self):
  url='/start/'+self.trial.start_token
  r=await self.client.get(url,headers={'Host':'192.168.1.2:8743'},allow_redirects=False)
  self.assertEqual(r.status,302)
  self.assertTrue(r.cookies[m.COOKIE]['secure'])
  self.assertTrue(r.cookies[m.COOKIE]['httponly'])
  r=await self.client.get(url,headers=self.headers,allow_redirects=False)
  self.assertEqual(r.status,403)
 async def test_login_budget(self):
  self.trial.attempts=3
  r=await self.client.post('/api/auth/token',headers={**self.headers,'Origin':self.trial.origin},json={})
  self.assertEqual(r.status,429)

class Content:
 def __init__(self, raw):self.raw=raw
 async def iter_chunked(self, n):
  for i in range(0,len(self.raw),n):yield self.raw[i:i+n]

class Response:
 def __init__(self,data,status=200):
  import json
  self.status=status;self.headers={'Content-Type':'application/json'}
  self.content=Content(json.dumps(data).encode())
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass

class FakeHTTP:
 def __init__(self,status=200):self.status=status;self.calls=[]
 def request(self,*args,**kwargs):
  self.calls.append((args,kwargs))
  return Response({'accessToken':'synthetic-access','refreshToken':'synthetic-refresh'},self.status)
 def get(self,*args,**kwargs):
  self.calls.append((args,kwargs))
  return Response({'content':[{'accountId':'synthetic-private-id'}]})

class Capture(Requests):
 async def test_verified_outcome_has_no_secrets(self):
  completed=[]
  async def done(result):
   completed.append(result)
   return {'account_count':1}
  self.trial.on_complete=done
  self.trial.http=FakeHTTP()
  headers={**self.headers,'Origin':self.trial.origin,'AnonymousId':'synthetic-anonymous'}
  with self.assertLogs(m._LOGGER,level='INFO') as logs:
   r=await self.client.post('/api/auth/token',headers=headers,json={'username':'synthetic','password':'synthetic'})
  self.assertEqual(r.status,200)
  self.assertEqual(completed,[{'accessToken':'synthetic-access','refreshToken':'synthetic-refresh','anonymousId':'synthetic-anonymous'}])
  self.assertEqual(self.trial.result,{'state':'verified','account_count':1,'attempts':1})
  self.assertNotIn('synthetic',str(logs.output))
  self.assertNotIn('Token',str(self.trial.__dict__))
  r=await self.client.post('/api/auth/token',headers=headers,json={})
  self.assertEqual(r.status,403)
 async def test_missing_anonymous_cannot_complete(self):
  self.trial.http=FakeHTTP()
  with self.assertLogs(m._LOGGER,level='WARNING'):
   r=await self.client.post('/api/auth/token',headers={**self.headers,'Origin':self.trial.origin},json={})
  self.assertEqual(r.status,200)
  self.assertEqual(self.trial.result['state'],'invalid_session')
  self.assertEqual(len(self.trial.http.calls),1)
 async def test_rejection_never_retries(self):
  self.trial.http=FakeHTTP(400)
  with self.assertLogs(m._LOGGER,level='WARNING'):
   r=await self.client.post('/api/auth/token',headers={**self.headers,'Origin':self.trial.origin},json={})
  self.assertEqual(r.status,400)
  self.assertEqual(len(self.trial.http.calls),1)
  self.assertEqual(self.trial.result['state'],'login_rejected')

if __name__=='__main__':unittest.main()
