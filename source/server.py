"""A thin HTTP boundary around the catalogue and Slack contracts."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from source.catalog import ROOT, initialize, catalogue, random_fact, stats
from source.slack import verify, message, enqueue, deliver_once

class Handler(BaseHTTPRequestHandler):
    def respond(self, value, status=200, content_type='application/json'):
        body = json.dumps(value).encode() if content_type == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' https://upload.wikimedia.org; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlparse(self.path)
        params = parse_qs(url.query)
        category = params.get('category',[''])[0]
        if url.path == '/api/random':
            return self.respond(random_fact(category))
        if url.path == '/api/facts':
            return self.respond(catalogue(params.get('q',[''])[0],category))
        if url.path == '/api/status':
            return self.respond(stats() | {'slack_configured':bool(os.getenv('SLACK_SIGNING_SECRET') and os.getenv('SLACK_BOT_TOKEN') and os.getenv('SLACK_TEAM_ID'))})
        files = {'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript'),'/style.css':('style.css','text/css')}
        if url.path in files:
            name, mime = files[url.path]
            return self.respond((ROOT/'public'/name).read_bytes(),content_type=mime)
        self.respond({'error':'Not found'},404)

    def do_POST(self):
        if self.path not in ('/slack/events','/slack/commands'):
            return self.respond({'error':'Not found'},404)
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length <= 0 or length > 1000000:
                return self.respond({'error':'Invalid body size'},413)
            raw = self.rfile.read(length)
            if not verify(raw,self.headers.get('X-Slack-Request-Timestamp'),self.headers.get('X-Slack-Signature'),os.getenv('SLACK_SIGNING_SECRET','')):
                return self.respond({'error':'Invalid signature'},401)
            if self.path == '/slack/commands':
                data = parse_qs(raw.decode())
                if not os.getenv('SLACK_TEAM_ID') or data.get('team_id',[''])[0] != os.getenv('SLACK_TEAM_ID'):
                    return self.respond({'error':'Wrong workspace'},403)
                if data.get('command',[''])[0] != '/catfact':
                    return self.respond({'error':'Unknown command'},400)
                return self.respond(message(random_fact(data.get('text',[''])[0].strip())) | {'response_type':'ephemeral'})
            data = json.loads(raw)
            if not isinstance(data,dict):
                raise ValueError('Expected object')
            if data.get('type') == 'url_verification':
                return self.respond({'challenge':data.get('challenge','')})
            if not os.getenv('SLACK_TEAM_ID') or data.get('team_id') != os.getenv('SLACK_TEAM_ID'):
                return self.respond({'error':'Wrong workspace'},403)
            if not os.getenv('SLACK_BOT_TOKEN'):
                return self.respond({'error':'Slack token not configured'},503)
            if data.get('type') == 'event_callback':
                enqueue(data,random_fact())
            self.respond({'ok':True})
        except (ValueError,UnicodeError,AttributeError,TypeError):
            self.respond({'error':'Malformed request'},400)

    def log_message(self, format, *args):
        # Paths can contain search queries; avoid logging message contents or secrets.
        pass

def worker():
    while True:
        if os.getenv('SLACK_BOT_TOKEN'):
            deliver_once()
        time.sleep(1)

def main():
    initialize()
    threading.Thread(target=worker,daemon=True).start()
    server = ThreadingHTTPServer((os.getenv('HOST','127.0.0.1'),int(os.getenv('PORT','3000'))),Handler)
    print('CatFacts listening on http://%s:%s' % server.server_address,flush=True)
    server.serve_forever()

if __name__ == '__main__':
    main()
