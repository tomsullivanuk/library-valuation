"""Readable browsing topics derived from public bibliographic evidence only."""
import csv
import hashlib
import re
from pathlib import Path

# IDs are stable so links and owner overrides can retain their meaning.
TOPICS = [
 ('philosophy','Philosophy','Ancient, medieval and modern thought; ethics, knowledge and mind.',r'^(B|BD|BH|BJ)$',r'philosoph|metaphysic|epistemolog|ethics|aesthetics'),
 ('logic-mathematics','Logic & Mathematics','Reasoning, mathematical logic and the foundations of mathematics.',r'^(BC|QA)$',r'\blogic\b|mathematic|probability|set theory|geometry|calculus'),
 ('religion','Religion & Theology','Religious traditions, Christian thought, spirituality and saints.',r'^(BL|BM|BP|BQ|BR|BT|BV|BX)$',r'theolog|christian|catholic|religion|spiritual|saints|church|judaism|buddhis|islam'),
 ('bible','Bible & Biblical Studies','Bible editions, interpretation, commentaries and biblical history.',r'^BS$',r'\bbible\b|biblical|scripture|new testament|old testament|gospels'),
 ('history-politics','History & Politics','World and American history, government and political thought.',r'^(C[A-Z]?|D[A-Z]?|E|F|J[A-Z]?)$',r'\bhistory\b|politic|government|civil war|american revolution'),
 ('biography','Biography & Memoir','Lives of historical figures, thinkers and other remarkable people.',r'^CT$',r'biograph|memoir|autobiograph'),
 ('literature','Literature & Poetry','Fiction, poetry, drama, classics and literary criticism.',r'^(P[A-Z]?|PZ)$',r'\bpoetry\b|\bpoems\b|\bfiction\b|\bnovel\b|literature|literary|\bdrama\b'),
 ('science-nature','Science & Nature','The natural world, scientific discoveries and the history of science.',r'^(Q|QB|QC|QD|QE|QH|QK|QL|QM|QN|QP|QR)$',r'\bphysics\b|astronomy|biology|natural history|\bscience\b|cosmolog|evolution'),
 ('art','Art & Creative Practice','Art history, drawing, painting, photography and music.',r'^(N[A-Z]?|M[A-Z]?)$',r'\bpainting\b|\bdrawing\b|\bart\b|\bcolor\b|photograph|\bmusic\b'),
 ('society','Society & Everyday Life','Psychology, education, social questions and practical interests.',r'^(BF|H[A-Z]?|L[A-Z]?|R[A-Z]?|S[A-Z]?|T[A-Z]?|G[A-Z]?)$',r'psycholog|sociolog|education|teaching|health|cooking|gardening|travel'),
]
SUBTOPICS = [
 ('ancient','Ancient philosophy','philosophy',r'\bplato\b|\baristotle\b|socrates|philosophy, ancient|ancient philosophy|stoic|gorgias'),
 ('medieval','Medieval philosophy & Aquinas','philosophy',r'aquinas|thomas,|medieval philosophy|philosophy, medieval|scholastic'),
 ('ethics','Ethics','philosophy',r'\bethics\b|\bethical\b|\bmoral\b'),
 ('mind','Knowledge & Mind','philosophy',r'epistemolog|philosophy of mind|knowledge|consciousness'),
 ('metaphysics','Metaphysics','philosophy',r'metaphysic|ontology|free will'),
 ('catholic','Catholicism','religion',r'catholic|papacy|pope|thomism'),
 ('spirituality','Spirituality & Saints','religion',r'spiritual|saints|prayer|devotion|contemplation'),
 ('american','American history','history-politics',r'american history|united states|lincoln|civil war'),
 ('poetry','Poetry','literature',r'\bpoetry\b|\bpoems\b'),
]

def classify(book, metadata=None, override=None):
    if override is not None:
        valid={t[0] for t in TOPICS}|{s[0] for s in SUBTOPICS}
        chosen=[x for x in override if x in valid]
        return sorted(set(chosen)|{s[2] for s in SUBTOPICS if s[0] in chosen})
    metadata=metadata or {}
    title=book.get('title','').lower()
    evidence=' '.join([title,metadata.get('subjects','')]).lower()
    classes=re.findall(r'\b([A-Z]{1,3})\s*\d',metadata.get('lcc',''))
    result={id for id,_,_,lc,words in TOPICS if any(re.search(lc,c) for c in classes) or re.search(words,evidence)}
    # Named thinkers are useful only as bibliographic topic signals, not broad
    # assumptions about every book by an author.
    for id,_,parent,pattern in SUBTOPICS:
        if re.search(pattern,evidence):result.update((parent,id))
    return sorted(result)


def build(records, output_dir=None, overrides=None):
    metadata={}
    path=Path(output_dir)/'book_metadata.csv' if output_dir else None
    if path and path.exists():
        with path.open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                ref=hashlib.sha256(('family-v1:'+row['catalog_item_id']).encode()).hexdigest()[:20]
                metadata[ref]=row
    mapping={};matched=0
    for ref,book in records.items():
        row=metadata.get(ref,{})
        # Reconciliation can reuse IDs for a different edition. Reject stale
        # metadata when the current ISBN disagrees with the recorded ISBNs.
        isbn=re.sub(r'[^0-9Xx]','',book.get('isbn',''))
        known={re.sub(r'[^0-9Xx]','',row.get(k,'')) for k in ('isbn13','isbn10')}-{''}
        if isbn and known and isbn not in known:row={}
        if row:matched+=1
        mapping[ref]=classify(book,row,(overrides or {}).get(ref))
    topics=[dict(id=id,title=title,description=description,count=sum(id in x for x in mapping.values()),subtopics=[dict(id=sid,title=label,count=sum(sid in x for x in mapping.values())) for sid,label,parent,_ in SUBTOPICS if parent==id]) for id,title,description,_,_ in TOPICS]
    uncategorized=sum(not x for x in mapping.values())
    topics.append(dict(id='more',title='More books to explore',description='Books still awaiting a reliable topic assignment.',count=uncategorized,subtopics=[]))
    for labels in mapping.values():
        if not labels:labels.append('more')
    return dict(topics=topics,books=mapping,metadata_matched=matched,total=len(records))
