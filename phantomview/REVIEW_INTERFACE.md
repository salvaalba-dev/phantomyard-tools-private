# Private classification review interface

`review_page.py` produces a self-contained local HTML page for an operator reviewing
one exact metadata draft. It adds no dashboard route, assistant capability or
publication permission. The HTML contains private selected-organization metadata;
keep it and downloaded decisions in protected local storage. Never commit real
review pages, drafts or decisions, or publish them on an ordinary web server.

```sh
python review_page.py --draft /private/reviews/current.draft.json --organization /private/organization.json --snapshot /private/selected-export.json --output /private/review.html
```

The organization input is trusted PhantomOrg JSON with explicit scopes. The
collector export may be a snapshot or an envelope containing `snapshot`. All
inputs are bounded and the draft must exactly match the current source adapter.
The output must be a new absolute path under a protected existing directory with
no symlink parents. POSIX creation uses mode 0600; Windows requires restrictive
filesystem ACLs. Open the generated file locally in a modern browser.

## Review workflow

1. Filter the draft by resource type or search its adapted metadata. Select
   individual records or the visible batch. Filters never change the selected set.
2. Inspect record titles to read adapted contents, source fingerprints and
   dependencies. This review covers metadata only, not omitted document or KB bodies.
3. Use **Include source dependencies** explicitly when needed. Added source
   records are selected but do not inherit a classification automatically.
4. Choose an existing information category, an exact existing scope and an explicit
   secret decision. Confirm that the current contents of every selected record
   were reviewed, then apply the assignment to the selected batch. New selections
   require their own review. Category zero is excluded from information labels.
5. Download decisions when all selected records and source dependencies are
   included and classified. Unselected records receive no approval. Decisions
   bind the exact draft and full organization fingerprints.

Assignments exist in page memory only until downloaded; reloading discards them.
There is no hidden browser storage, auto-save, network request or automatic grant.
The export is untrusted input to the independent
[approval and publication workflow](PROJECTION_REVIEW.md). That workflow rechecks
current sources, authority, classifications and dependencies. The browser cannot
publish, authenticate a reviewer or bypass those checks.

The page embeds only adapted metadata and existing category/scope choices, not the
full organization policy or channel identities. Dynamic source text is inserted
as text. Embedded JSON escapes HTML delimiters; a content security policy pins
the application script and stylesheet by hash and blocks network connections,
forms and external resources. These controls do not replace private file access.

## Verification and remaining integration

Node's built-in test runner checks decision behavior without third-party packages:

```sh
node --test test_review_ui.cjs
python -m unittest test_review_page -q
```

The Python integration test executes the actual JavaScript model and feeds its
export into independent approval, including stale-source rejection. Browser
verification uses synthetic data only. The local interface does not yet sit inside
the scoped dashboard or consume its authenticated session. In-dashboard review
requires explicit write authority and separate route integration. AU, native
channels, the public widget and other setups remain unchanged.
