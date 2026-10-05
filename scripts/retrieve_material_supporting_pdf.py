"""Retrieve the publicly advertised ACS supplement for private scientific reading."""

import hashlib
import json
import tempfile
import urllib.request

from scripts.check_material_refresh_access import LOG, OUT, fetch


def main():
    output = OUT / "carnosic-supporting-access.json"
    if output.exists():
        raise SystemExit("Preserve the previous receipt")
    article = fetch(
        "ACS public Figshare supplement",
        "https://api.figshare.com/v2/articles/26326955",
    )
    if not article or article.get("resource_doi") != "10.1021/acs.jafc.4c00957":
        raise SystemExit("Supporting-information identity not established")
    files = []
    for item in article.get("files", []):
        url = item["download_url"]
        response = urllib.request.urlopen(url, timeout=25)
        raw = response.read()
        if not raw.startswith(b"%PDF-"):
            raise SystemExit("Public download is not a PDF")
        with tempfile.NamedTemporaryFile(
            prefix="axis-carnosic-si-", suffix=".pdf", delete=False
        ) as handle:
            handle.write(raw)
            print("Reading source:", handle.name, flush=True)
        files.append(
            {
                "name": item["name"],
                "url": url,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "status": "retrieved_outside_repository_for_reading",
                "cache_is_not_replay_input": True,
            }
        )
    output.write_text(
        json.dumps(
            {
                "metadata_attempts": LOG,
                "doi": article["doi"],
                "resource_doi": article["resource_doi"],
                "license": article.get("license"),
                "files": files,
            },
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
