"""Remove a merchant at its owner's request, and stop the importer re-adding it.

    python -m server.delist example.com "emailed 2026-08-24, asked to be removed"

Removal is unconditional and this is the only supported way to do it — a raw
sqlite DELETE would drop the record but leave nothing to stop the next importer
run from putting it straight back.
"""
import sys

from .db import DB


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print(__doc__.strip())
        return 2
    domain = argv[0].lower().strip()
    note = argv[1] if len(argv) > 1 else ""
    db = DB()
    existed = db.delist(domain, note)
    if existed:
        print(f"{domain}: removed, products purged, suppressed from future imports")
    else:
        print(f"{domain}: was not listed — suppression recorded anyway, so it can't be imported later")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
