# Vision

## Library Valuation

**Version:** 1.0  
**Project Owner:** Tom Sullivan

---

## Mission

Library Valuation is an open, reproducible system for cataloging, analyzing, valuing, and ultimately helping families make informed decisions about scholarly and personal libraries.

The project emphasizes transparency, reproducibility, and evidence-based valuation while minimizing manual effort.

Rather than estimating what an entire library is worth, the system helps answer practical questions such as:

- Which books deserve individual research?
- Which books should be sold individually?
- Which books should be sold as subject collections?
- Which books are unlikely to justify the effort of resale?
- Which books have historical or family significance and should be retained?

The objective is to maximize both financial return and informed decision making.

---

# Design Philosophy

The project follows several guiding principles.

## 1. The catalog is the source of truth.

All downstream reports, dashboards, and workbooks are generated from a normalized catalog.

The catalog should never be modified simply to support reporting.

---

## 2. Reproducibility over manual editing.

Every report should be reproducible from the source data.

Generated Excel workbooks are outputs—not the canonical data source.

---

## 3. Separate facts from opinions.

The system distinguishes between:

- bibliographic facts
- market observations
- valuation estimates
- selling recommendations

This allows pricing strategies to evolve without losing underlying research.

---

## 4. Evidence-based valuation.

Estimated values should be supported whenever possible by objective market data, including:

- AbeBooks
- eBay completed sales
- Bookfinder
- Amazon Used
- other reputable secondary-market sources

Heuristic scoring is used only to prioritize research.

---

## 5. Minimize manual effort.

The project should automate repetitive tasks while preserving human judgment where it adds value.

Research time should be directed toward books with the highest expected return.

---

## 6. Build for long-term maintainability.

The architecture should remain understandable years from now.

Business logic should exist in one place.

Configuration should be externalized whenever practical.

Modules should have clearly defined responsibilities.

---

# Long-Term Vision

Over time the project should evolve from a catalog generator into a decision-support system.

```
Book Sources
      │
      ▼
Normalized Library Catalog
      │
      ▼
Analysis Engine
      │
      ▼
Decision Engine
      │
      ├── Valuation Workbook
      ├── Research Queue
      ├── Dealer Prospectus
      ├── Collection Analytics
      ├── Estate Reports
      └── Family Retention Lists
```

---

# Success Criteria

The project succeeds when a user can:

- import a library from one or more sources;
- identify the books most likely to have significant resale value;
- estimate realistic retail and dealer values;
- prioritize research efficiently;
- generate professional reports with minimal manual effort; and
- make informed decisions about selling, donating, or preserving a library.

The software should remain useful even if market sources, pricing models, or acquisition sources change over time.