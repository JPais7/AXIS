"""Retrieve public PMC XML into a temporary cache and print scientific sections."""

import hashlib
import json
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path


def main():
    pmcid = sys.argv[1]
    url = "https://www.ebi.ac.uk/europepmc/webservices/rest/" + pmcid + "/fullTextXML"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
    except Exception:
        url = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id=" + pmcid
        # EFetch is a legitimate public read endpoint, not a paywall workaround.
        url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?"
            "db=pmc&id=" + pmcid.removeprefix("PMC")
        )
        with urllib.request.urlopen(url, timeout=60) as response:
            raw = response.read()
    article = ET.fromstring(raw)
    directory = Path(tempfile.mkdtemp(prefix="axis-addendum-read-"))
    (directory / (pmcid + ".xml")).write_bytes(raw)
    info = {
        "pmcid": pmcid,
        "url": url,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "cache": str(directory),
        "body_present": article.find(".//body") is not None,
    }
    print(json.dumps(info))
    (directory / "access.json").write_text(json.dumps(info, indent=2))
    for section in article.findall(".//body/sec"):
        title = " ".join(section.findtext("title", "").split())
        if len(sys.argv) > 2 and sys.argv[2].lower() not in title.lower():
            continue
        print("\nSECTION", title)
        print(" ".join(" ".join(section.itertext()).split()))


if __name__ == "__main__":
    main()
