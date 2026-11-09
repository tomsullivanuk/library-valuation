"""Offline-only AbeBooks Search Web Services adapter.

No network opener, environment credential loader, or live-enable switch exists.
Wire contracts remain provisional until approved access and a small live probe.
"""
from collections import defaultdict, deque
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
import gzip
import io
import math
import re
from urllib.parse import urlencode, urlsplit, parse_qs
import xml.etree.ElementTree as ET

from valuation.live_valuation_pilot import FIELDS, clean
from valuation.offline_valuation_review import isbn, binding, listing_key, review_book

ENDPOINT = 'https://search2.abebooks.com/search'
OFFLINE_SOURCE = 'abebooks_sws_synthetic'
MAX_BYTES = 1_048_576
NATIVE_USED = {'as_new', 'fine', 'near_fine', 'very_good', 'good', 'fair', 'poor'}
CONDITIONS = {'asnew':'as_new', 'fine':'fine', 'nearfine':'near_fine',
              'verygood':'very_good', 'good':'good', 'fair':'fair', 'poor':'poor',
              'new':'new', 'asdescribed':'as_described'}


class SwsError(ValueError):
    """Fixed safe messages, never upstream response bodies or keyed URLs."""
    def __init__(self, kind, status_code=None):
        self.kind, self.status_code = kind, status_code
        super().__init__('AbeBooks offline adapter: ' + kind)


@dataclass(frozen=True)
class SearchPlan:
    strategy: str
    query: str
    currency: str
    limit: int
    parameters: dict
    url: str = field(repr=False)


def search_plan(book, *, client_key='OFFLINE-SYNTHETIC-KEY', currency='USD', limit=10):
    if not isinstance(client_key,str) or not re.fullmatch(r'OFFLINE-[A-Za-z0-9_-]{1,80}',client_key):
        raise SwsError('only synthetic OFFLINE keys are accepted')
    if type(limit) is not int or not 1 <= limit <= 10:
        raise SwsError('result limit must be 1 to 10')
    if currency not in {'USD','GBP','EUR','CAD','AUD','CHF','JPY','NZD'}:
        raise SwsError('unsupported requested currency')
    target = isbn(book.get('isbn13','')) or isbn(book.get('isbn10',''))
    title, author = clean(book.get('title','')), clean(book.get('author',''))
    if target:
        params, strategy, query = {'isbn':target}, 'isbn', target
    elif title or author:
        params = {k:v for k,v in (('title',title),('author',author)) if v}
        strategy, query = 'title_author', ' '.join(v for v in (title,author) if v)
    else:
        raise SwsError('a valid ISBN or title/author is required')
    params.update(outputsize='long', maxresults=str(limit), bookcondition='used',
                  currency=currency, targetsite='abebooks.com', destinationcountry='USA',sortorder='2')
    try:
        encoded=urlencode(dict(params,clientkey=client_key),encoding='iso-8859-1',errors='strict')
    except UnicodeEncodeError:
        raise SwsError('query cannot be represented in Latin-1; use an ISBN') from None
    return SearchPlan(strategy,query,currency,limit,params,ENDPOINT+'?'+encoded)


@dataclass(frozen=True)
class ReplayResponse:
    status: int
    body: bytes = field(repr=False)
    headers: dict = field(default_factory=dict)


class ReplayTransport:
    """Finite synthetic response queue; has no network capability."""
    def __init__(self,responses):
        self.responses=deque(responses)
        if not all(isinstance(r,ReplayResponse) for r in self.responses):
            raise SwsError('replay responses are required')
        self.requests=[]

    def request(self,plan):
        self.requests.append(plan)
        if not self.responses:raise SwsError('synthetic response queue exhausted')
        return self.responses.popleft()


class ReplayClock:
    def __init__(self):self.value=0.;self.waits=[]
    def now(self):return self.value
    def sleep(self,seconds):self.waits.append(seconds);self.value+=seconds


def retry_after(value,now):
    if value is None:return None
    try:
        seconds=float(value)
    except (TypeError,ValueError):
        try:
            parsed=parsedate_to_datetime(value)
            seconds=(parsed-now).total_seconds()
        except (ValueError,TypeError,OverflowError):return None
    return max(0.,seconds) if math.isfinite(seconds) else None


class OfflineSwsClient:
    def __init__(self,transport=None,*,budget=30,retries=2,interval=1.,clock=None,utc_now=None):
        if type(transport) is not ReplayTransport:
            raise SwsError('only ReplayTransport is enabled; live access is disabled')
        if type(budget) is not int or not 1<=budget<=400 or type(retries) is not int or not 0<=retries<=2:
            raise SwsError('invalid offline request/retry budget')
        if not isinstance(interval,(int,float)) or not math.isfinite(interval) or interval<.25:
            raise SwsError('pacing must be at least 0.25 seconds')
        self.transport,self.budget,self.retries,self.interval=transport,budget,retries,float(interval)
        self.clock=clock or ReplayClock();self.utc_now=utc_now or (lambda:datetime.now(timezone.utc))
        self.attempts=0;self.last=None;self.dispatch_times=[]

    def search(self,book,*,currency='USD',limit=10,observed_at):
        plan=search_plan(book,currency=currency,limit=limit)
        for attempt in range(self.retries+1):
            if self.attempts>=self.budget:raise SwsError('request budget exhausted')
            if self.last is not None:
                self.clock.sleep(max(0.,self.last+self.interval-self.clock.now()))
            self.attempts+=1;self.last=self.clock.now()
            self.dispatch_times.append(self.last)
            response=self.transport.request(plan)
            if response.status==200:
                return parse_response(response,plan,book,observed_at=observed_at)
            if response.status in {401,403}:
                raise SwsError('authorization rejected',response.status)
            if response.status not in {429,500,502,503,504} or attempt==self.retries:
                raise SwsError('request rejected',response.status)
            headers={k.lower():v for k,v in response.headers.items()}
            delay=retry_after(headers.get('retry-after'),self.utc_now())
            delay=max(2**attempt,delay or 0)
            if delay>60:raise SwsError('server cooldown exceeds retry bound',response.status)
            self.clock.sleep(delay)
        raise AssertionError('unreachable')


def local_name(tag):return tag.rsplit('}',1)[-1]


def amount(value,zero=False):
    try:
        n=Decimal(value)
        if n.is_finite() and (n>=0 if zero else n>0) and n<=999999999 and n==n.quantize(Decimal('.01')):
            return format(n,'.2f')
    except (ValueError,InvalidOperation,TypeError):pass
    return ''


def safe_url(value,book_id):
    value=value.strip()
    if value.startswith('www.abebooks.com/'):value='https://'+value
    try:
        parsed=urlsplit(value)
        if (parsed.scheme not in {'https','http'} or parsed.hostname not in {'abebooks.com','www.abebooks.com'} or
                parsed.username or parsed.password or parsed.port not in {None,80,443} or
                parsed.path!='/servlet/BookDetailsPL' or parse_qs(parsed.query).get('bi')!=[book_id]):return ''
    except ValueError:return ''
    return 'https://www.abebooks.com/servlet/BookDetailsPL?bi='+book_id


def parse_response(response,plan,book,*,observed_at):
    if response.status!=200:raise SwsError('non-success response cannot be parsed',response.status)
    try:datetime.fromisoformat(observed_at.replace('Z','+00:00'))
    except (TypeError,ValueError):raise SwsError('invalid observation timestamp') from None
    body=response.body
    if not isinstance(body,bytes) or len(body)>MAX_BYTES:raise SwsError('response too large or not bytes')
    encoding={k.lower():v for k,v in response.headers.items()}.get('content-encoding','identity').lower()
    if encoding=='gzip':
        try:body=gzip.GzipFile(fileobj=io.BytesIO(body)).read(MAX_BYTES+1)
        except (OSError,EOFError):raise SwsError('invalid gzip response') from None
    elif encoding not in {'identity',''}:raise SwsError('unsupported response compression')
    if len(body)>MAX_BYTES:raise SwsError('expanded response too large')
    if b'\x00' in body or re.search(br'<!\s*(?:DOCTYPE|ENTITY)\b',body,re.I):
        raise SwsError('DTD, entities and non-text XML encodings are forbidden')
    try:root=ET.fromstring(body)
    except (ET.ParseError,ValueError):raise SwsError('malformed XML') from None
    if local_name(root.tag).lower() in {'html','body','head'}:raise SwsError('unexpected HTML response')
    if local_name(root.tag) not in {'Book','SearchResults'}:
        raise SwsError('unverified XML envelope')
    nodes=list(root.iter())
    if any(local_name(n.tag).lower() in {'error','errors','errormessage'} and ''.join(n.itertext()).strip() for n in nodes):
        raise SwsError('API error response')
    books=[n for n in nodes if local_name(n.tag)=='Book']
    counts=[(n.text or '').strip() for n in nodes if local_name(n.tag) in {'resultCount','ResultCount','totalResults'}]
    if counts and (len(set(counts))!=1 or not counts[0].isdigit()):raise SwsError('invalid result count')
    if len(books)>plan.limit:raise SwsError('response exceeds requested result cap')
    if counts and int(counts[0])<len(books):raise SwsError('result count contradicts listings')
    if not books:
        if counts and counts[0]=='0':return []
        raise SwsError('unrecognized empty response; not assumed to mean no results')
    return [normalize_listing(n,plan,book,observed_at) for n in books]


def normalize_listing(node,plan,book,observed_at):
    fields=defaultdict(list)
    for child in node:
        fields[local_name(child.tag)].append(' '.join(child.itertext()).strip())
    if any(len(set(values))>1 for values in fields.values()):raise SwsError('conflicting duplicate XML fields')
    def value(name):return clean(fields.get(name,[''])[0])
    ids={isbn(value(name)) for name in ('isbn10','isbn13')} - {''}
    actual=next(iter(ids)) if len(ids)==1 else ''
    book_id=value('bookId');valid_id=bool(re.fullmatch(r'\d{1,19}',book_id))
    url=safe_url(value('listingUrl'),book_id) if valid_id else ''
    fmt={'H':'hardcover','S':'paperback'}.get(value('bindingType'),'')
    native=value('itemCondition');grade=CONDITIONS.get(re.sub(r'[\s_-]','',native).lower(),'')
    condition=value('listingCondition').upper();diagnostics=[]
    if len(ids)>1:diagnostics.append('conflicting_isbns')
    title_binding=binding(value('title'))
    if fmt and title_binding and fmt!=title_binding:diagnostics.append('conflicting_bindings')
    if (condition=='NEW BOOK' and grade and grade!='new') or (condition=='NOT NEW BOOK' and grade=='new'):
        diagnostics.append('conflicting_condition')
    if value('currency') and value('currency')!=plan.currency:diagnostics.append('unexpected_price_currency')
    if value('quantity') and (not value('quantity').isdigit() or int(value('quantity'))<1):
        diagnostics.append('unavailable_or_invalid_quantity')
    price=amount(value('listingPrice'));ship=amount(value('firstBookShipCost'),True);total=amount(value('totalListingPrice'),True)
    if total and price and ship and Decimal(total)!=Decimal(price)+Decimal(ship):diagnostics.append('inconsistent_shipping_total')
    description=clean(value('vendorDescription')+' '+value('keywords'),2000)
    description=re.sub(r'https?://\S+','[link omitted]',description)
    description=re.sub(r'(?<!\w)(?:\+?\d[ ()-]*){10,}(?!\w)','[contact number omitted]',description)
    row=dict.fromkeys(FIELDS,'')
    row.update(catalog_id=book['catalog_item_id'],source=OFFLINE_SOURCE,
        lookup_status='metadata_conflict' if diagnostics else 'observed',observation_date=observed_at,
        lookup_strategy=plan.strategy,search_query=plan.query,listing_url=url,raw_reference='abebooks:'+book_id if valid_id else '',
        listing_title=value('title'),listing_author=value('author'),asking_price=price,currency=plan.currency,
        condition=native,listing_isbn13=actual,listing_isbn10=value('isbn10') if actual and isbn(value('isbn10'))==actual else '',
        listing_isbns='; '.join(sorted(ids)),listing_binding=fmt,listing_condition_grade=grade,
        listing_publisher=value('publisherName'),listing_year=value('publicationYear'),
        listing_edition='first edition' if value('editionType')=='F' else '',listing_format_raw=value('bindingType'),
        listing_condition_description=description,detail_status=diagnostics[0] if diagnostics else 'sws_record',
        metadata_basis='AbeBooks SWS listing fields; synthetic offline transport',
        native_condition=native,shipping_price=ship,total_listing_price=total,
        vendor_currency=value('vendorCurrency'),vendor_price=amount(value('vendorPrice')),
        vendor_id=value('vendorId') if value('vendorId').isdigit() else '',
        price_currency_basis='explicit requested currency; not vendor currency',
        quantity_available=value('quantity'),adapter_diagnostics='; '.join(diagnostics),
        evidence_mode='synthetic_offline',actual_condition='ungraded',publishable=False)
    return row


def preview(book,rows,*,as_of):
    """Exercise the shared evidence checks, retaining native condition scenarios."""
    if any(r.get('evidence_mode')!='synthetic_offline' for r in rows):
        raise SwsError('offline preview requires synthetic offline evidence')
    target={k:book.get(k,'') for k in ('catalog_item_id','title','author','isbn13','isbn10','reviewed_estimate_id')}
    target_isbn=isbn(book.get('isbn13','')) or isbn(book.get('isbn10',''))
    target.update(isbn13=target_isbn,isbn10='')
    target.update(target_condition='',target_binding='')
    # The frozen matcher strips query strings from URLs. SWS IDs live in ?bi=,
    # so match one stable-ID group at a time, then combine diagnostic decisions.
    # Distinct SWS offers must never collapse to one BookDetailsPL path.
    assessment=review_book(target,[],as_of=as_of)
    assessment.update(decisions=[],sources={},next_steps=[
        'Keep native seller-condition scenarios separate; actual physical grading remains deferred.'])
    groups=defaultdict(list)
    for index,row in enumerate(rows):groups[row.get('raw_reference') or 'missing:'+str(index)].append(row)
    retained={};candidate_ids=set();reasons=Counter()
    for stable_id,items in groups.items():
        result=review_book(target,[dict(r,source='abebooks') for r in items],as_of=as_of)
        if result['proposal'] is not None:raise SwsError('offline proposals are forbidden')
        candidates=[d for d in result['decisions'] if d['disposition']=='candidate_only']
        for d in result['decisions']:
            d.update(source=OFFLINE_SOURCE,listing=stable_id)
            reasons.update(d['reasons'])
        assessment['decisions'].extend(result['decisions'])
        if candidates:candidate_ids.add(stable_id)
        for row in items:
            valid_id=bool(re.fullmatch(r'abebooks:\d{1,19}',stable_id))
            if (candidates and valid_id and row['listing_url'] and row['lookup_status']=='observed' and target_isbn and
                    isbn(row.get('listing_isbn13') or row.get('listing_isbn10',''))==target_isbn):
                retained.setdefault(stable_id,row)
    if rows:assessment['sources']={OFFLINE_SOURCE:dict(reasons=dict(reasons))}
    grouped=defaultdict(list)
    for row in retained.values():
        if row['listing_condition_grade'] in NATIVE_USED:
            grouped[(row['listing_condition_grade'],row['listing_binding'] or 'unknown',row['currency'])].append(Decimal(row['asking_price']))
    scenarios=[]
    for (grade,fmt,currency),prices in sorted(grouped.items()):
        scenarios.append(dict(hypothetical_grade=grade,condition_system='AbeBooks native seller condition',
            listing_binding=fmt,currency=currency,low=format(min(prices),'.2f'),high=format(max(prices),'.2f'),
            listing_count=len(prices),high_spread=max(prices)>=3*min(prices),scenario_only=True,publishable=False))
    return dict(catalog_item_id=book['catalog_item_id'],evidence_mode='synthetic_offline',
                assessment=assessment,condition_scenarios=scenarios,actual_condition='ungraded',
                condition_assumed=False,publishable=False,estimates_changed=0,live_requests=0,
                physical_grading='deferred',
                identity_held_candidates=len(candidate_ids)-len(retained),
                new_copy_offers=sum(r['listing_condition_grade']=='new' for r in retained.values()))
