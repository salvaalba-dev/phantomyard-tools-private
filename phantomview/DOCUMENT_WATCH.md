# Periodic document-matrix observation

`document_watch.py` compares the selected native manifest, reviewed document
matrix and existing bindings on each invocation. It reuses batch validation and
writes one producer-private `document-watch.json` report. It never changes
bindings, stages originals, modifies native history, approves records or publishes
content. A detected change is not permission to display it.

Use the existing collector timer or scheduler. No additional daemon, timer,
service or package dependency is required. A systemd collector drop-in can append
an observation before its existing collection command:

```ini
[Service]
ExecStartPre=-/usr/bin/python3 /opt/phantomview/document_watch.py --manifest /protected/store/manifest.yaml --matrix /protected/document-matrix.json --snapshot /protected/reader/index.json --config /protected/collector/config.json --report-dir /protected/document-observations --organization example
```

Use the installation's verified Python and release paths. Preserve all existing
`ExecStartPre` entries and sandbox settings. Pre-create the report directory for
the producer, normally mode `0700`; reports use `0600`. Keep it outside web assets,
reader projections and original-document storage. The observer must be able to
read the existing protected inputs and local blobs; it needs no new network or
reader permissions. Bootstrap requires an existing successful persona snapshot.
Both an exported index envelope and a plain snapshot with `actors` are accepted.

The leading `-` leaves the normal collector running when observation fails, so an
observation problem does not disable the collector's independent invalidation and
ACL checks. The observer returns exit code 1 and prints only a fixed summary on
validation failure. Inspect its private report or the existing service journal;
do not treat a successful collector unit as proof of a successful observation.

Reports contain the check time, a stable comparison revision, last change time
and the current preparation plan. Prepared rows distinguish additions, refreshes
and unchanged bindings. Pending, removed and excluded selections remain explicit.
Changing a structured input during the scan invalidates that observation.
Incidental persona observation clocks do not create document-change alerts;
persona identity, organization, role and eligibility still affect comparison.
Repeated observations of the same inputs update the check time without creating
another change. A missing or invalid source replaces the successful report with
`unavailable`, without retaining its old plan as current evidence.

This is an operator report, not a new public API or reader document. It can include
native document identities and must remain private. It contains no document body
or source path. An unreadable report destination is an operational failure; the
previous file's timestamp must not be interpreted as a fresh observation.

The existing sixteen selected binding limit still applies. Discovery can report
other eligible native documents as `not-in-matrix`, but automatic classification,
remote Drive retrieval and publication remain separate work. Organization and
project matrices must use separate source-bound invocations and report directories.
