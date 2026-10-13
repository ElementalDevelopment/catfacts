"""Independent checks for the behaviors promised in specs/component.md."""
import hashlib
import hmac
import json
import os
import tempfile
import threading
import time
import unittest
import urllib.request
import urllib.error
from pathlib import Path
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from source import catalog, slack
from source.server import Handler

class Acceptance(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.original = catalog.DB
        catalog.DB = Path(self.folder.name)/'test.sqlite3'
        catalog.initialize()
        self.env = patch.dict(os.environ,SLACK_SIGNING_SECRET='test-secret',SLACK_BOT_TOKEN='test-token',SLACK_TEAM_ID='T1')
        self.env.start()

    def tearDown(self):
        self.env.stop()
        catalog.DB = self.original
        self.folder.cleanup()

    def signed(self, raw, timestamp=None):
        ts = str(timestamp or int(time.time()))
        signature = 'v0='+hmac.new(b'test-secret',b'v0:'+ts.encode()+b':'+raw,hashlib.sha256).hexdigest()
        return {'X-Slack-Request-Timestamp':ts,'X-Slack-Signature':signature}

    def test_signature_and_replay_boundaries(self):
        raw = b'{"hello":"world"}'
        headers = self.signed(raw)
        self.assertTrue(slack.verify(raw,headers['X-Slack-Request-Timestamp'],headers['X-Slack-Signature'],'test-secret'))
        self.assertFalse(slack.verify(raw+b' ',headers['X-Slack-Request-Timestamp'],headers['X-Slack-Signature'],'test-secret'))
        old = self.signed(raw,int(time.time())-301)
        self.assertFalse(slack.verify(raw,old['X-Slack-Request-Timestamp'],old['X-Slack-Signature'],'test-secret'))
        self.assertFalse(slack.verify(raw,'bad','v0=x','test-secret'))
        self.assertFalse(slack.verify(raw,headers['X-Slack-Request-Timestamp'],headers['X-Slack-Signature'],''))

    def event(self):
        return {'event_id':'E1','event':{'type':'app_mention','channel':'C1','ts':'123.4','user':'U1'}}

    def test_duplicates_and_bot_loops(self):
        event = self.event(); fact = catalog.random_fact()
        self.assertTrue(slack.enqueue(event,fact))
        self.assertFalse(slack.enqueue(event,fact))
        event['event_id']='E2'; event['event']['bot_id']='B1'
        self.assertFalse(slack.enqueue(event,fact))
        with catalog.connect() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)

    def test_threading_and_direct_messages(self):
        event=self.event(); event['event']['thread_ts']='100.1'
        slack.enqueue(event,catalog.random_fact())
        with catalog.connect() as db:
            self.assertEqual(json.loads(db.execute('SELECT payload FROM jobs').fetchone()[0])['thread_ts'],'100.1')
        event['event_id']='E2'; event['event']['type']='message'; event['event']['channel_type']='channel'
        self.assertFalse(slack.enqueue(event,catalog.random_fact()))
        event['event']['channel_type']='im'
        self.assertTrue(slack.enqueue(event,catalog.random_fact()))

    def test_candidate_is_never_published(self):
        with catalog.connect() as db:
            catalog.insert(db,dict(text='Unverified test passage',category='Secret',source='https://example.com',source_title='Example'))
        self.assertEqual(catalog.catalogue(category='Secret'),[])
        self.assertIsNone(catalog.random_fact('Secret'))
        self.assertGreaterEqual(catalog.stats()['approved'],100)

    def test_images_have_attribution(self):
        for fact in catalog.catalogue():
            self.assertTrue(fact['source'].startswith('https://'))
            if fact['image']:
                self.assertTrue(fact['image_credit'].startswith('https://commons.wikimedia.org/wiki/File:'))
                output=json.dumps(slack.message(fact))
                self.assertIn(fact['image'],output)
                self.assertIn(fact['image_credit'],output)

    def test_delivery_is_durable_and_retries(self):
        slack.enqueue(self.event(),catalog.random_fact())
        with patch('urllib.request.urlopen',side_effect=TimeoutError):
            self.assertTrue(slack.deliver_once())
        with catalog.connect() as db:
            row=db.execute('SELECT * FROM jobs').fetchone()
            self.assertEqual(row['attempts'],1)
            self.assertEqual(row['status'],'pending')
            self.assertGreater(row['due'],time.time())
            db.execute('UPDATE jobs SET due=0,attempts=7')
        with patch('urllib.request.urlopen',side_effect=TimeoutError): slack.deliver_once()
        with catalog.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'dead')

    def test_successful_delivery(self):
        slack.enqueue(self.event(),catalog.random_fact())
        import io
        with patch('urllib.request.urlopen',return_value=io.BytesIO(b'{"ok":true}')): slack.deliver_once()
        with catalog.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0],'sent')

    def test_unavailable_image_falls_back_to_fact(self):
        slack.enqueue(self.event(),catalog.random_fact('Breeds'))
        import io
        with patch('urllib.request.urlopen',side_effect=[io.BytesIO(b'{"ok":false,"error":"invalid_blocks"}'),io.BytesIO(b'{"ok":true}')]) as send:
            slack.deliver_once()
            self.assertEqual(send.call_count,2)
            payload=json.loads(send.call_args.args[0].data)
            self.assertFalse(any(block['type']=='image' for block in payload['blocks']))
            self.assertIn('https://',payload['text'])

    def test_http_contract(self):
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def post(path,data,headers):
            req=urllib.request.Request(base+path,data=data,headers=headers)
            with urllib.request.urlopen(req) as response: return json.load(response)
        try:
            with urllib.request.urlopen(base+'/api/random') as r: self.assertIn('source',json.load(r))
            with urllib.request.urlopen(base+'/') as r: self.assertIn(b'CatFacts',r.read())
            raw=json.dumps({'type':'url_verification','challenge':'abc'}).encode()
            self.assertEqual(post('/slack/events',raw,self.signed(raw)),{'challenge':'abc'})
            with self.assertRaises(urllib.error.HTTPError) as caught: post('/slack/events',raw,{})
            self.assertEqual(caught.exception.code,401)
            caught.exception.close()
            event=self.event()|{'team_id':'T1','type':'event_callback'}; raw=json.dumps(event).encode()
            self.assertEqual(post('/slack/events',raw,self.signed(raw)),{'ok':True})
            post('/slack/events',raw,self.signed(raw))
            with catalog.connect() as db: self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],1)
            event['team_id']='T2'; raw=json.dumps(event).encode()
            with self.assertRaises(urllib.error.HTTPError) as caught: post('/slack/events',raw,self.signed(raw))
            self.assertEqual(caught.exception.code,403)
            caught.exception.close()
            raw=b'team_id=T1&command=%2Fcatfact&text='
            self.assertEqual(post('/slack/commands',raw,self.signed(raw))['response_type'],'ephemeral')
            raw=b'not json'
            with self.assertRaises(urllib.error.HTTPError) as caught: post('/slack/events',raw,self.signed(raw))
            self.assertEqual(caught.exception.code,400)
            caught.exception.close()
        finally:
            server.shutdown(); server.server_close(); thread.join()

if __name__=='__main__': unittest.main()
