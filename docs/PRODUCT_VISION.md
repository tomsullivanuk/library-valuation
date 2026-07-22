# Product Vision

## Origins

Library Valuation began as an effort to understand and value one family's
personal library of more than 3,000 books. The library was assembled primarily
for learning and intellectual interest, not as an investment portfolio or a
rare-book collection.

The practical problem is eventual estate stewardship. Understanding the
collection before the owner's death allows the family to make informed choices
later without beginning from scratch under time pressure. What began as a
valuation tool has therefore evolved into a decision-support system for the
stewardship and eventual disposition of a substantial personal library.

The project should remain grounded in solving this real use case well before it
attempts broader generalization.

## Mission

Library Valuation exists to help stewards of large personal libraries make
informed, efficient, and confident decisions throughout the lifecycle of a
collection.

It combines durable cataloging, physical inventory, market evidence,
collection analysis, and intelligent recommendations to reduce the time,
uncertainty, and risk involved in understanding and ultimately dispersing a
personal library.

The objective is not to maximize every possible dollar. The objective is to
maximize **Return on Stewardship Time**.

## The Problem

Responsibility for a substantial personal library creates several connected
challenges:

- determining what is actually present;
- identifying books or collections that deserve special attention;
- understanding potential financial value;
- recognizing coherent subject collections;
- deciding what should be retained, sold, donated, or otherwise removed;
- avoiding accidental disposal of meaningful value; and
- completing the work without becoming a full-time bookseller.

The steward must make good decisions with limited time and imperfect
information. The product should make that practical.

## Who We Serve

The primary user is the **Steward**: the person responsible for understanding,
caring for, or eventually disposing of the collection.

The steward may be the original owner, a spouse, an executor, a trustee, an
adult child, another family member, or someone else entrusted with the
collection. The steward is not necessarily a collector, bookseller, librarian,
or rare-book expert. The product should not assume specialist knowledge or an
unlimited amount of time.

## Product Principles

### 1. Evidence over Opinion

Recommendations should be grounded in durable evidence: physical inventory
observations, catalog metadata, market evidence, subject coherence, collection
characteristics, and explicit confidence or uncertainty. A recommendation
should explain its reasoning and allow the steward to inspect the supporting
evidence.

### 2. Recommendations, Not Decisions

The application advises. The steward decides.

AI may identify opportunities, group books, estimate value or effort,
recommend strategies, and identify potential buyers. Final judgment remains
with the steward. The system should preserve the distinction between evidence,
recommendation, and decision.

### 3. Progressive Disclosure

The primary experience should begin with a concise action plan. The steward
should then be able to inspect, in order:

1. what is recommended;
2. why it is recommended; and
3. the detailed evidence supporting it.

The system should support concise recommendations without withholding complete
underlying reports and data.

### 4. Optimize Return on Stewardship Time

**Return on Stewardship Time** is the value achieved relative to the steward's
personal time and effort. The system should not assume that maximizing gross
sale proceeds is always the best outcome.

Selling a coherent collection, working with a specialist dealer, accepting a
reasonable wholesale discount, using bulk disposition, or donating low-value
material may produce a better overall outcome than managing thousands of
individual listings. The product should show where additional effort is likely
to matter and where it is not.

### 5. Protect Against Regret

The system should help prevent avoidable mistakes, especially:

- overlooking a materially valuable book;
- dispersing a collection that should first be evaluated intact;
- accepting a poor offer because the steward lacks information; or
- spending hundreds of hours pursuing only modest incremental proceeds.

The primary failure to avoid is not leaving a possible dollar unrealized. It is
wasting substantial time for little return or making an uninformed,
irreversible decision.

### 6. Preserve Optionality

Recommendations should identify a preferred initial strategy while preserving
reasonable fallback options. A coherent collection might first be offered
intact, then opened to selective purchase, and only afterward divided into
smaller lots, individual sales, bulk sale, donation, or recycling.

Recommendations should guide the next step without becoming rigid instructions.

### 7. Stewardship over Valuation

Valuation is an important subsystem, but stewardship is the mission. Market
evidence should support triage, prioritization, negotiation, and disposition
strategy. The product should not become narrowly focused on perfect book-level
valuations when a practical collection-level decision would serve the steward
better.

### 8. Use Advanced Tools to Reduce Information Asymmetry

Modern data sources, automation, and AI should help the steward make better
decisions by reducing clerical work, uncertainty, and negotiating disadvantage.
Advanced technology should not introduce unnecessary complexity or create more
work for the steward.

## The Intended Workflow

The long-term product workflow is:

```text
Acquire or Discover
        ↓
Catalog
        ↓
Inventory
        ↓
Analyze
        ↓
Identify Significant Books and Collections
        ↓
Recommend Disposition Strategies
        ↓
Generate Supporting Reports and Buyer Materials
        ↓
Record Final Disposition
```

Dealer emails, negotiations, payments, shipping, and marketplace communication
may occur outside the application. Library Valuation should ultimately know
whether books remain available and their final disposition category, but it
does not need to function as a dealer CRM, marketplace, or accounting system.

## What Success Looks Like

The product succeeds when a steward can confidently answer:

- What do we own?
- Where is it?
- How complete and trustworthy is the inventory?
- Which books deserve individual attention?
- Which books form potentially meaningful or marketable collections?
- What is the likely value?
- What effort is likely to be required to realize that value?
- Which disposition strategy offers the best Return on Stewardship Time?
- What should we do next?
- Which books are still available?
- Which books have been sold, retained, given away, donated, recycled, or
  otherwise removed?

The ultimate outcome is that the library can be dispersed thoughtfully and
efficiently, without major regrets and without consuming an unreasonable
portion of the steward's life.

## What We Intentionally Do Not Build

Library Valuation is not intended to become:

- a reading tracker;
- a lending system;
- a social book catalog;
- a book recommendation engine;
- a general-purpose personal library manager;
- an online marketplace;
- a dealer CRM;
- shipping software;
- payment processing software; or
- estate accounting software.

Existing products already serve many general library-management needs. Library
Valuation should remain focused on estate stewardship and disposition decision
support.

## Scope and Generalization

The current project is intentionally grounded in one real family library and
one steward's needs. The immediate goal is to solve that use case well.

The architecture may later be generalized for other families, executors,
trustees, estates, or professional stewards. Broad productization should follow
additional use cases and evidence rather than assumptions.

## Long-Term Vision

The long-term vision is for Library Valuation to become a trusted
decision-support system for estate stewardship of substantial personal
libraries. It should help stewards understand what they have, identify what
matters, evaluate practical alternatives, find appropriate buyers or
institutions, and develop a disposition plan that balances financial return
with the time and effort required.

Every proposed capability should be tested against one governing question:

> Does this help the steward make a better decision with less time, less
> uncertainty, or less risk?

If the answer is no, the feature likely does not belong in the product.
