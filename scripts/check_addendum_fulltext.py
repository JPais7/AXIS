"""Inspect canonical public TDM links without redistributing article content."""

import hashlib
import json
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

PACKAGE = (
    Path(__file__).resolve().parents[1]
    / "axis/resources/evidence-addendum/erap1-axspa/2020-2026/v1"
)


def main():
    destination = PACKAGE / "material-access-check.json"
    if destination.exists():
        raise SystemExit("Refusing to overwrite access snapshot")
    context = json.loads((PACKAGE / "context-access.json").read_text())
    rows = []
    for source in context:
        if "crossref" not in source["url"]:
            continue
        for link in source["response"]["message"].get("link", [])[:1]:
            url = link["URL"]
            row = {"url": url, "access_date": "2026-10-05"}
            try:
                with urllib.request.urlopen(url, timeout=45) as response:
                    raw = response.read()
                    row.update(
                        status=response.status,
                        bytes=len(raw),
                        sha256=hashlib.sha256(raw).hexdigest(),
                    )
                if "xml" in url:
                    tree = ET.fromstring(raw)
                    tags = [x.tag.rsplit("}", 1)[-1] for x in tree.iter()]
                    row["element_tags"] = sorted(set(tags))
                    row["scientific_body_present"] = any(
                        t in {"body", "sections"} for t in tags
                    )
                    if row["scientific_body_present"]:
                        cache = Path(tempfile.mkdtemp(prefix="axis-addendum-tdm-"))
                        (cache / "article.xml").write_bytes(raw)
                        print("BODY_CACHE", cache)
            except Exception as exc:
                row["error"] = str(exc)
            rows.append(row)
            print(json.dumps(row), flush=True)
    destination.write_text(json.dumps(rows, indent=2) + "\n")


if __name__ == "__main__":
    main()
