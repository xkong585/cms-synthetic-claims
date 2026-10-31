"""Verify or retrieve exact official CMS sources. Never auto-accept changed bytes."""
from pathlib import Path
import hashlib,json,os,urllib.request
from datetime import datetime,timezone
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def download():
    root=ROOT/'data/raw';root.mkdir(parents=True,exist_ok=True)
    lock=json.loads((ROOT/'docs/source_lock.json').read_text());rows=[]
    manifest=ROOT/'evidence/source_manifest.csv'
    old=pd.read_csv(manifest).set_index('file').to_dict('index') if manifest.exists() else {}
    for item in lock:
        p=root/item['file'];downloaded=False
        if not p.exists():
            req=urllib.request.Request(item['url'],headers={'User-Agent':'SyntheticClaimsPortfolio/1.0'})
            with urllib.request.urlopen(req,timeout=180) as response:content=response.read()
            if hashlib.sha256(content).hexdigest()!=item['sha256']:raise ValueError('CMS source changed: '+p.name)
            temp=p.with_suffix('.tmp');temp.write_bytes(content);os.replace(temp,p);downloaded=True
        if sha(p)!=item['sha256']:raise ValueError('Corrupt cached source: '+p.name)
        magic=p.read_bytes()[:10]
        if p.suffix=='.zip' and not magic.startswith(b'PK'):raise ValueError('Expected ZIP, not HTML: '+p.name)
        if p.suffix=='.pdf' and not magic.startswith(b'%PDF'):raise ValueError('Expected PDF: '+p.name)
        rows.append({**item,'downloaded_at_utc':datetime.now(timezone.utc).isoformat() if downloaded else old.get(p.name,{}).get('downloaded_at_utc',item['obtained_at_utc'])})
    pd.DataFrame(rows).to_csv(manifest,index=False)
    return rows
if __name__=='__main__':download()
