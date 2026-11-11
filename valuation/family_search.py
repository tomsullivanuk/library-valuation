"""Ranked search over the recipient allowlist, with optional offline embeddings."""
from collections import defaultdict
from difflib import get_close_matches
import hashlib
import html
import json
import math
import re
import sqlite3
import threading
import unicodedata

from valuation.family_catalog import FIELDS
STOP=set('a an and are as at be books book by for from i in introduction is it me of on or read show some that the to want with about looking find please'.split())
TEXT_FIELDS=('title','author','publisher','isbn','description')


def normalize(value):
    value=''.join(c for c in unicodedata.normalize('NFKD',str(value)) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[^\W_]+',value.lower().replace("'",'').replace('’',''),re.UNICODE))


def plain(value):
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',str(value)))).strip()


def safe_records(records):
    result=[]
    for r in records:
        if set(r)!=set(FIELDS) or not all(isinstance(v,str) for v in r.values()):raise ValueError('Search accepts only recipient fields')
        result.append({k:r[k] for k in FIELDS})
    if len({r['reference'] for r in result})!=len(result):raise ValueError('Duplicate search reference')
    return sorted(result,key=lambda r:r['reference'])


def fingerprint(records):
    return hashlib.sha256(json.dumps(safe_records(records),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class Search:
    def __init__(self,records,semantic=None):
        self.records={r['reference']:r for r in safe_records(records)}
        self.semantic=semantic;self.lock=threading.Lock()
        self.db=sqlite3.connect(':memory:',check_same_thread=False)
        self.db.execute('CREATE VIRTUAL TABLE books USING fts5(reference UNINDEXED,title,author,publisher,isbn,description)')
        self.vocabulary=set();self.terms={}
        for ref,r in self.records.items():
            self.db.execute('INSERT INTO books VALUES(?,?,?,?,?,?)',(ref,*(normalize(plain(r.get(k,''))) for k in TEXT_FIELDS)))
            self.vocabulary.update(normalize(r['title']+' '+r['author']).split())
            self.terms[ref]=set(normalize(' '.join(plain(r[k]) for k in TEXT_FIELDS)).split())

    def search(self,query,allowed=None,limit=30,mode='hybrid'):
        if not isinstance(query,str) or len(query)>500:raise ValueError('Search must be at most 500 characters')
        if mode not in ('keyword','hybrid'):raise ValueError('Invalid search mode')
        allowed=set(self.records) if allowed is None else set(allowed)&self.records.keys()
        q=normalize(query);words=[w for w in q.split() if w not in STOP][:24]
        if not q:return dict(results=[],engine='keyword',notice='Enter a title, author, ISBN or topic.')
        digits=re.sub(r'[^0-9Xx]','',query)
        isbn_query=bool(re.fullmatch(r'[0-9Xx\s-]+',query.strip()) and len(digits) in (10,13))
        exact=[]
        for ref,r in self.records.items():
            if ref in allowed and ((isbn_query and re.sub(r'[^0-9Xx]','',r['isbn']).lower()==digits.lower()) or normalize(r['title'])==q):exact.append(ref)
        if not words:
            if not exact:return dict(results=[],engine='keyword',notice='Enter a title, author, ISBN or topic.')
            words=q.split()[:24]
        expanded=list(words);groups=[]
        for w in words:
            alternatives=[w]
            if len(w)>=4 and w not in self.vocabulary:
                alternatives.extend(get_close_matches(w,self.vocabulary,n=1,cutoff=.82));expanded.extend(alternatives[1:])
            groups.append(alternatives)
        expression=' OR '.join('"'+w+'"' for w in dict.fromkeys(expanded))
        with self.lock:
            lexical=[r[0] for r in self.db.execute('SELECT reference FROM books WHERE books MATCH ? ORDER BY bm25(books,0,12,7,2,5,1),reference',(expression,)) if r[0] in allowed]
        required=max(1,math.ceil(.6*len(words)))
        lexical=[ref for ref in lexical if sum(any(option in self.terms[ref] for option in group) for group in groups)>=required]
        scores=defaultdict(float);why={};sem_scores={};notice='';engine='keyword'
        for rank,ref in enumerate(lexical):scores[ref]+=.8/(30+rank);why[ref]='Keyword match'
        if mode=='hybrid' and self.semantic and not isbn_query:
            try:
                semantic=self.semantic(query,allowed)
                engine='hybrid'
                for rank,(ref,score) in enumerate(semantic):
                    if ref not in allowed or score<.40:continue
                    sem_scores[ref]=score;scores[ref]+=1.2/(30+rank)
                    why[ref]='Keywords and related topics' if ref in why else 'Related topics'
            except Exception:notice='AI matching is unavailable; showing keyword results.'
        elif mode=='hybrid' and not self.semantic:notice='Keyword search; local AI index is not enabled.'
        # Avoid matching a precise but absent ISBN against arbitrary number fragments.
        if isbn_query:scores={ref:1 for ref in exact}
        for ref in exact:scores[ref]=10;why[ref]='Exact ISBN' if isbn_query else 'Exact title'
        ranked=sorted(scores,key=lambda ref:(-scores[ref],normalize(self.records[ref]['title']),ref))[:max(1,min(limit,100))]
        results=[]
        for ref in ranked:
            r=self.records[ref];description=plain(r['description']);positions=[description.lower().find(w) for w in words if description.lower().find(w)>=0]
            start=max(0,min(positions)-60) if positions else 0
            excerpt=description[start:start+260]
            results.append(dict(reference=ref,reason=why.get(ref,'Keyword match'),excerpt=('…' if start else '')+excerpt+('…' if start+260<len(description) else '')))
        return dict(results=results,engine=engine,notice=notice)
