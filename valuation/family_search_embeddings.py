"""Private offline index and encoder. Network is used only by explicit model setup."""
import hashlib
import json
import os
from pathlib import Path
import threading
from valuation.family_search import safe_records,fingerprint,plain
MODEL='sentence-transformers/all-MiniLM-L6-v2'


def documents(records):
    for r in safe_records(records):
        prefix=plain(r['title']+' — '+r['author']+' — '+r['publisher'])[:500]
        words=plain(r['description']).split()
        chunks=[words[i:i+110] for i in range(0,min(len(words),1320),85)] or [[]]
        for chunk in chunks:yield r['reference'],prefix+'\n'+' '.join(chunk)


def encoder(model_path):
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(2)
    return SentenceTransformer(str(model_path),device='cpu',local_files_only=True,trust_remote_code=False,model_kwargs={'use_safetensors':True})


def build(records,model_path,destination):
    import numpy as np
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    docs=list(documents(records));model=encoder(model_path)
    vectors=model.encode([t for _,t in docs],batch_size=32,normalize_embeddings=True,show_progress_bar=False)
    path=destination/'vectors.npz';tmp=destination/'vectors.tmp.npz'
    np.savez_compressed(tmp,vectors=vectors,refs=np.array([ref for ref,_ in docs]));tmp.chmod(0o600);tmp.replace(path)
    meta=dict(fingerprint=fingerprint(records),model=MODEL,revision=Path(model_path).name,chunks=len(docs),books=len(records),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    temp=destination/'manifest.tmp';temp.write_text(json.dumps(meta));temp.chmod(0o600);temp.replace(destination/'manifest.json')
    return meta


class Embeddings:
    def __init__(self,records,model_path,directory):
        import numpy as np
        self.np=np;directory=Path(directory);meta=json.loads((directory/'manifest.json').read_text());path=directory/'vectors.npz'
        if meta['model']!=MODEL or meta['revision']!=Path(model_path).name:raise ValueError('Different AI model revision')
        if meta['fingerprint']!=fingerprint(records) or meta['sha256']!=hashlib.sha256(path.read_bytes()).hexdigest():raise ValueError('Stale or damaged AI index')
        data=np.load(path,allow_pickle=False);self.vectors=data['vectors'];self.refs=data['refs'];self.model=encoder(model_path);self.lock=threading.Lock()
        if len(self.vectors)!=len(self.refs) or not np.isfinite(self.vectors).all():raise ValueError('Invalid AI index')
    def __call__(self,query,allowed):
        with self.lock:q=self.model.encode([query],normalize_embeddings=True,show_progress_bar=False)[0]
        scores=self.vectors@q;best={}
        for ref,score in zip(self.refs,scores):
            ref=str(ref)
            if ref in allowed:best[ref]=max(best.get(ref,-1),float(score))
        return sorted(best.items(),key=lambda x:(-x[1],x[0]))[:100]
