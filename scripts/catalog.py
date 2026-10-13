"""Local editorial tools. Network imports remain candidates until reviewed."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlencode, quote, urlparse
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from source.catalog import ROOT, initialize, connect, insert

TITLES = ['Cat','Cat behavior','Cat communication','Cat senses','Cat anatomy',
 'Cat intelligence','Cat righting reflex','Purr','Kitten','Cat coat genetics',
 'Domestication of the cat','Felis','Felidae','Siamese cat','Maine Coon','Bengal cat',
 'Ragdoll','Sphynx cat','British Shorthair','Abyssinian cat']

def wikipedia():
    folder = ROOT/'data/snapshots'
    folder.mkdir(exist_ok=True)
    for title in TITLES:
        snapshot = folder/(title.replace(' ','_')+'.json')
        params = urlencode(dict(action='query',prop='extracts|pageimages|revisions',
             explaintext=1,piprop='original',rvprop='ids',format='json',titles=title))
        if snapshot.exists():
            data = json.loads(snapshot.read_text())
        else:
            result = subprocess.run(['curl','-fsSL','--retry','2','-A','CatFacts/0.1 (educational catalogue)',
                'https://en.wikipedia.org/w/api.php?'+params],capture_output=True,check=True)
            snapshot.write_bytes(result.stdout)
            data = json.loads(result.stdout)
        with connect() as db:
            for page in data['query']['pages'].values():
                revision = str(page.get('revisions',[{}])[0].get('revid',''))
                source = 'https://en.wikipedia.org/w/index.php?'+urlencode(dict(title=page['title'],oldid=revision))
                text = re.sub(r'==[^\n]+==','',page.get('extract',''))
                for sentence in re.split(r'(?<=[.!?])\s+',text):
                    sentence = ' '.join(sentence.split())
                    if 55 <= len(sentence) <= 350 and not re.search(r'\b(?:ISBN|doi|http|Retrieved)\b',sentence):
                        insert(db,dict(text=sentence,category='Wikipedia',source=source,
                            source_title=page['title'],revision=revision,status='candidate'))
        print('Imported candidates:',title)

def import_json(path):
    records = json.loads(Path(path).read_text())
    with connect() as db:
        for record in records:
            if not record.get('text') or len(record['text'])>1000:
                raise ValueError('Fact text must be 1–1000 characters')
            source = record.get('source','')
            if urlparse(source).scheme != 'https' or not urlparse(source).hostname or re.search(r'[<>|\s]',source) or not record.get('source_title'):
                raise ValueError('Each fact needs an HTTPS source and source title')
            record['status'] = 'candidate'
            # Only Wikimedia images with an attribution page enter the catalogue.
            if record.get('image') and (urlparse(record['image']).hostname != 'upload.wikimedia.org' or not record.get('image_credit') or not urlparse(record['image']).path.lower().endswith(('.jpg','.jpeg','.png','.gif'))):
                raise ValueError('Image needs a Wikimedia URL and attribution link')
            if record.get('image_credit') and (urlparse(record['image_credit']).hostname != 'commons.wikimedia.org' or re.search(r'[<>|\s]',record['image_credit'])):
                raise ValueError('Image credits must link to Wikimedia Commons')
            record.setdefault('category','Discoveries')
            if re.search(r'[<>|\n]',record['category']) or len(record['category']) > 60:
                raise ValueError('Invalid category')
            insert(db,record)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action',required=True)
    sub.add_parser('wikipedia')
    sub.add_parser('candidates')
    imp = sub.add_parser('import'); imp.add_argument('file')
    review = sub.add_parser('review'); review.add_argument('id'); review.add_argument('decision',choices=['approved','rejected'])
    retry = sub.add_parser('retry'); retry.add_argument('id')
    args = parser.parse_args()
    initialize()
    if args.action == 'wikipedia': wikipedia()
    elif args.action == 'import': import_json(args.file)
    elif args.action == 'candidates':
        with connect() as db:
            for row in db.execute("SELECT id,text,source FROM facts WHERE status='candidate'"):
                print(json.dumps(dict(row)))
    elif args.action == 'review':
        with connect() as db:
            if db.execute('UPDATE facts SET status=? WHERE id=?',(args.decision,args.id)).rowcount != 1:
                parser.error('Unknown fact ID')
    elif args.action == 'retry':
        with connect() as db:
            if db.execute("UPDATE jobs SET status='pending',attempts=0,due=0 WHERE id=? AND status='dead'",(args.id,)).rowcount != 1:
                parser.error('Unknown dead job ID')
