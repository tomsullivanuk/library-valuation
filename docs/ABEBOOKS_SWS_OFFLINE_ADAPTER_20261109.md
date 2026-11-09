# AbeBooks SWS offline preparation — November 9, 2026

The adapter is ready for synthetic replay testing. This is not live API validation or fresh AbeBooks market evidence. The whole-library valuation review still awaits fresh AbeBooks comparisons and review; current estimates remain unchanged and physical grading remains deferred.

## Scope and safeguards

`valuation/abebooks_sws.py` accepts only a finite replay transport and synthetic keys. It has no network opener, real credential loader, or live-enable switch. Observations carry the unsupported `abebooks_sws_synthetic` source, which the production comparison reviewer rejects. Preview output is explicitly hypothetical and nonpublishable; no estimate writer is included.

Tests cover ISBN-first queries, Latin-1 encoding, XML and bounded gzip parsing, malformed and unexpected responses, independent listing ISBNs, conflicting metadata, binding, availability, currencies, shipping, duplicates, native seller conditions, authentication errors, retry limits, request budgets, and virtual pacing. The virtual clock tests dispatch behavior without waiting or sending traffic; it is not a live rate limiter.

The parser keeps requested-currency listing prices separate from sellers' original currencies and shipping. Used-condition scenarios retain AbeBooks' native grades rather than translating them into eBay grades. They never assign a grade to the owned book. New offers, uncertain identities, special copies and conflicting records are held separately or excluded. Search plans cap results at ten, ordered by ascending price: these are bounded low-price samples, not representative market distributions.

AbeBooks listing identity uses the stable book ID. Its documented BookDetailsPL URLs identify listings through a query parameter, which the older comparison URL normalizer removes. The new preview groups by stable ID before invoking the existing matcher, preserving distinct offers without changing the frozen eBay review rules.

## Verification

The laptop and Mini each passed all 811 tests, including 57 adapter tests. A five-offer invented fixture produced three distinct Good paperback used offers at $14.25–$16.00, rejected the wrong ISBN, and kept the new offer separate. The replay verified saved-review protection and unchanged canonical file hashes, with zero live requests and zero estimate changes.

Private replay receipts are under `output/valuation_review_20261106/abebooks_sws_offline_demo_20261109_v2/` on each machine. Synthetic fixture and adapter tests are committed; private library hashes and outputs are not.

Run the demo with a new output directory:

```sh
.venv/bin/python -m operations.abebooks_sws_offline_demo --project . --output output/valuation_review_20261106/abebooks_sws_offline_demo_NEW
```

## Affiliate application status — November 9, 2026

The AbeBooks Affiliate Program application was submitted through Impact. The confirmation screen displayed **In Review** and stated that a response notification would follow. Affiliate approval has not yet been received.

The application identifies Pops' Edge at https://tomsullivanuk.substack.com/ as the publication: approaches to gaming, occasional book reviews and other topics. Library Valuation remains a separate private application. Affiliate enrollment does not establish approval for its API or data-retention use. The November 8 inquiry about those uses remains pending; no new email was sent for this status update.

Next steps:

1. Await the affiliate application response; address any requested publication or account information accurately.
2. If approved, obtain the Affiliate ID and request an SWS Client Key, supplying the required site, technical contact and request-origin information.
3. Obtain explicit confirmation that private valuation research, retained comparisons and derived value ranges are permitted. Do not treat affiliate acceptance or a key alone as confirmation of these uses.
4. Once access and use permissions are confirmed, validate real responses with a small approved probe, then run the bounded 30-book pilot before expanding collection.

Keep live requests disabled, estimates unchanged and physical grading deferred while waiting. Do not place credentials, personal account details or private library records in the PR.

## Before live use

Confirm approved credentials and written permission for automated valuation, comparison retention and derived value ranges. Validate the real response envelope and parameter semantics with a small approved probe: the fixture's `SearchResults` wrapper is provisional, although its Book fields follow the published guide. Implement a separately reviewed live transport with real pacing and secure credential handling. Then run a bounded 30-book pilot and inspect identity, coverage and condition scenarios before expanding. Keep estimates unchanged until the results are explicitly reviewed.

## Primary documentation

- [SWS overview](https://www.abebooks.com/developer/search-web-services/overview)
- [Parameters and result fields](https://www.abebooks.com/developer/search-web-services/parameters)
- [Errors](https://www.abebooks.com/developer/search-web-services/errors)
- [End-user guide, version 2.7, March 2025](https://www.abebooks.com/docs/AffiliateProgram/WebServices/end-user-guide.pdf)
