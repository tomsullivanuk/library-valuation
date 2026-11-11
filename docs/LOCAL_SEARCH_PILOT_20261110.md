# Private local search comparison

The owner-only prototype is at https://library-pilot.wearyfather.org/owner/search-pilot. It compares ranked keyword results against keyword plus local AI results. The linked 42-query report is also owner-only. Ordinary family search remains unchanged pending relevance review; this is an evaluation surface, not a second operational owner workspace.

## Behavior and privacy

The prototype indexes only the explicit family projection: opaque reference, title, author, publisher, year, ISBN, availability and book description. It rejects additional fields and duplicate references. No purchase history, valuations, locations, private notes, recipient identities, saved messages or request histories enter the search corpus. Original source descriptions provide excerpts; no model generates book claims or invents catalog records. Exact title and ISBN matches take priority. An absent precise ISBN produces no results instead of loose numerical matches.

Keyword search uses SQLite FTS5 with title/author weighting and typo alternatives from title/author vocabulary. Multiword queries require sufficient term coverage; this prevents an unrelated long query matching just one incidental word. Hybrid ranking combines lexical and embedding ranks with a minimum semantic similarity of 0.40. These are experimental relevance thresholds, not probability/confidence measures. Semantic matches are labelled Related topics and are not evidence that every part of a natural-language query is satisfied.

AI encoding uses sentence-transformers/all-MiniLM-L6-v2 pinned to Hugging Face revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41. Only JSON/text configuration and safetensors weights were downloaded from the official model repository; remote model code is disabled. Runtime uses CPU with two PyTorch threads, local-files-only loading, offline Hub mode and telemetry disabled. Model setup accessed the package/model registries, but catalog text and reader queries are not sent to them. No hosted AI API or per-query API charge is introduced.

The Mini runs the model in its own ~/library-access-pilot/search-venv (Python 3.14), separate from the application environment. The optional requirements-search.txt and resolved requirements-search-lock.txt record dependencies. The private search-pilot directory contains the derived vectors, fingerprint/hash manifest, comparison results, report and worker token; these are not Git artifacts or public static assets.

Descriptions are split into overlapping chunks, with metadata repeated as context. Each description is bounded to its first 1,320 words; keyword search still covers the entire description. The model has a 256-word-piece input limit, so exceptionally long titles/metadata or unusual tokenization can still truncate chunk inputs. Missing descriptions rely on metadata. The initial index covers 2,565 records with 5,803 chunks; 2,306 records have descriptions. Embeddings and the manifest are private files; loading disables pickle and checks the corpus fingerprint, model revision, vector hash and finite values.

## Availability, access and recovery

The family gateway authenticates the owner before serving any preview page, script, report or query. Tests reject the guest identity on all four routes. Existing two-address Cloudflare/local allowlists are unchanged. Queries use POST bodies rather than URLs and are not logged by the application/worker.

A fixed loopback worker listens on 127.0.0.1:8878, accepts only /search with the expected Host and a private random token, and checks the corpus fingerprint. The gateway supplies current available references, then filters the worker response again. Reserved/transferred copies are handled by the existing live availability rules. The static 42-query report is a dated snapshot; live preview results apply current availability.

Worker failure, a stale fingerprint, timeout or corrupted index cannot broaden access; the gateway returns keyword results with an explicit fallback notice. The worker is a user LaunchAgent, local.library-search-pilot, with offline environment settings and existing automatic-login startup. An isolated installer configures only the owner-preview path; it preserves family allowlists and the original configuration in a private backup. Family main-page search is not redirected to this worker.

To rebuild, run family_search_pilot build and evaluate with the same pinned model path and current private catalog snapshot, then run operations.family_access_pilot.install_search_pilot. This validates the snapshot fingerprint before enabling the preview. Restart the worker when the snapshot is rebuilt. To disable the preview, remove search_pilot_dir from the private family-service config, restart the family service, and unload local.library-search-pilot. The existing library and family services do not depend on the optional search environment.

## Evaluation and observed results

The deterministic replay comprises 10 exact titles, 10 ISBNs, 8 title typos, 10 topical/natural-language probes and 4 negative probes: 42 queries. The expected known-item identities are frozen in the private evaluation JSON for this catalog snapshot. Topical probes have candidate results rather than automated relevance labels; the report explicitly calls for human review.

An initial replay exposed irrelevant results for nonsense queries that shared a single word with a description. Added the multiword coverage rule and a regression test, then replayed all 42 queries. Final known-item top-five hit counts are 28/28 for both keyword and hybrid search. All four negative probes return no results in both modes. This small replay does not establish general precision or recall. In observed comparisons AI improves discovery for some science/faith, language-evolution and introductory-philosophy queries; subjective suitability still needs review.

Final warm hybrid median is 19.1 ms and maximum is 115.6 ms across these 42 queries on the Mini. These figures measure the search engine only, not full HTTP, authentication, availability projection or cold model startup. In a live owner Chrome check, both columns rendered and hybrid mode was confirmed for a natural-language query; its worker/gateway search stage displayed 94 ms. No list, request, estimate or inventory decision was changed.

All 847 Python tests pass on laptop and Mini. Coverage includes exact ranking, ISBN normalization/misses, typo recovery, descriptions, SQL-like queries, no-result coverage, excluded references, availability filtering, exception fallback without private errors, source/model/vector integrity, chunk bounds and owner-route access control. Preview JavaScript syntax validation passed. The live worker was deliberately unloaded: the preview fell back to keywords, then recovered to hybrid after reloading its LaunchAgent, with current availability checked. No reboot was performed for this prototype.

## Next review gate

Use the comparison page and report to judge the topical searches, especially introductory-level suitability and weak related-topic matches. Before enabling the family search field, choose relevance thresholds and UI treatment, validate stale-page/list behavior and end-to-end latency, and add a broader judged query set. No external AI integration or family rollout is implied by this prototype.

Sources: https://www.sqlite.org/fts5.html ; https://www.sbert.net/examples/sentence_transformer/applications/semantic-search/README.html ; https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 ; https://pypi.org/project/sentence-transformers/ .

## Preview discoverability and owner identity

Added the authenticated owner's escaped email and Owner label to both the remote owner workspace header and the private preview. Added an explicit AI preview link and a note that main Library search still uses its original rules, following confusion between the operational Library tab and the comparison page. The preview does not silently replace main search. The owner identity badge is generated only after signed identity verification; its escaping test passes. No access policy changed.

Verified the exact owner query “an introduction to medieval philosophy” in the live private comparison page. Signed-in identity was visible, hybrid mode returned results, and its first candidate was the matching introductory medieval-philosophy title. Left the comparison tab open with that query. No main-search behavior, request, estimate or inventory record changed.

## Authorized family rollout

After the owner approved the combined approach, enabled family_search_enabled in the existing private configuration using install_search_pilot --enable-family. The same friends-and-family Browse search field now debounces read-only POST /api/search requests and uses the hybrid ranking and live availability filtering. It shows up to 30 ranked catalog cards, source excerpts and keyword/related-topic labels. Empty queries restore the original Browse order. Clearing or changing a query removes old excerpts; version guards discard stale responses. Search remains hidden in My List.

The endpoint retains verified invited identity, exact Origin, JSON and X-Family-Request checks. It has no draft/submission side effects and exposes only existing recipient-visible fields. The worker, model/index checks and keyword fallback remain unchanged. If the gateway itself is unavailable, the page falls back to its prior basic local keyword matching with an explicit notice. The owner comparison page remains available; the operational owner Library search still uses its established search rules.

All 849 Python tests pass on laptop and Mini. Added HTTP checks for search identity/origin, recipient-only response fields, query-length validation and unchanged draft version. Extended the synthetic JavaScript tests for stale-response suppression, network fallback and absence of draft writes. Live Safari signed in as the recipient returned hybrid results for the exact medieval-philosophy query, with the expected introductory title first, 30 ranked cards and source excerpts. No production lists or requests were changed. The family allowlist remains the same two addresses. To roll back family enhanced search, set family_search_enabled false; the page falls back to basic matching. The comparison worker can remain available to the owner.
