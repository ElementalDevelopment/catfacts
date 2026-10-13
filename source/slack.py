"""Authenticate before parsing; persist before acknowledging; deliver afterward."""
import hashlib
import hmac
import json
import os
import time
import urllib.request
import urllib.error
from source.catalog import connect

def verify(raw, timestamp, signature, secret, now=None):
    try:
        if not secret or abs((time.time() if now is None else now) - int(timestamp)) > 300:
            return False
    except (TypeError, ValueError):
        return False
    expected = 'v0=' + hmac.new(secret.encode(), b'v0:' + timestamp.encode() + b':' + raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or '')

def message(fact):
    if not fact:
        return {'text': 'No reviewed facts are available for that category.'}
    # Plain text blocks keep source content from being interpreted as Slack markup.
    blocks = [{'type':'section','text':{'type':'plain_text','text':fact['text']}}]
    blocks.append({'type':'section','text':{'type':'mrkdwn','text':f"<{fact['source']}|Read the source> · {fact['category']}"}})
    if fact.get('image') and fact.get('image_credit'):
        blocks.append({'type':'image','image_url':fact['image'],'alt_text':'Illustration from '+fact['source_title']})
        blocks.append({'type':'context','elements':[{'type':'mrkdwn','text':f"<{fact['image_credit']}|Image credits and license>"}]})
    return {'text': fact['text'] + '\n' + fact['source'], 'blocks':blocks, 'unfurl_links':False, 'unfurl_media':False}

def enqueue(envelope, fact):
    event = envelope.get('event', {})
    eligible = event.get('type') == 'app_mention' or (event.get('type') == 'message' and event.get('channel_type') == 'im')
    if not eligible or event.get('bot_id') or event.get('subtype') or not event.get('user'):
        return False
    if not envelope.get('event_id') or not event.get('channel') or not event.get('ts'):
        return False
    payload = message(fact) | {'channel':event['channel'],'thread_ts':event.get('thread_ts',event['ts'])}
    with connect() as db:
        cursor = db.execute('INSERT OR IGNORE INTO jobs(id,payload) VALUES (?,?)',
                            (envelope['event_id'],json.dumps(payload)))
        return cursor.rowcount == 1

def deliver_once():
    with connect() as db:
        job = db.execute("SELECT * FROM jobs WHERE status='pending' AND due<=? ORDER BY due LIMIT 1",(time.time(),)).fetchone()
    if not job:
        return False
    try:
        req = urllib.request.Request('https://slack.com/api/chat.postMessage',data=job['payload'].encode(),
              headers={'Authorization':'Bearer '+os.environ['SLACK_BOT_TOKEN'],'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=15) as response:
            result = json.load(response)
        if not result.get('ok') and result.get('error') == 'invalid_blocks':
            # An unavailable external image should not hide the fact itself.
            payload = json.loads(job['payload'])
            payload['blocks'] = [block for block in payload['blocks'] if block['type'] not in ('image','context')]
            req.data = json.dumps(payload).encode()
            with urllib.request.urlopen(req, timeout=15) as response:
                result = json.load(response)
        if not result.get('ok'):
            raise RuntimeError(result.get('error','slack_error'))
        with connect() as db:
            db.execute("UPDATE jobs SET status='sent',error=NULL WHERE id=?",(job['id'],))
    except Exception as error:
        attempts = job['attempts'] + 1
        delay = min(3600, 2**attempts * 5)
        if isinstance(error, urllib.error.HTTPError) and error.code == 429:
            try: delay = max(delay,int(error.headers.get('Retry-After','60')))
            except ValueError: pass
        with connect() as db:
            db.execute('UPDATE jobs SET attempts=?,due=?,status=?,error=? WHERE id=?',
                (attempts,time.time()+delay,'dead' if attempts>=8 else 'pending',type(error).__name__,job['id']))
    return True
