"""Follow official Crossref links and search public supporting-information metadata."""

import json

from scripts.check_material_refresh_access import LOG, OUT, fetch


def main():
    output = OUT / "supporting-access.json"
    if output.exists():
        raise SystemExit("Do not overwrite previous access attempts")
    previous = json.loads((OUT / "public-access-metadata.json").read_text())
    for paper in previous["papers"]:
        links = (paper["crossref"] or {}).get("link") or []
        for url in sorted({item["URL"] for item in links}):
            fetch("Official Crossref full-text link: " + paper["doi"], url)
            print(
                paper["doi"], LOG[-1]["status"], LOG[-1].get("http_status"), flush=True
            )
    results = []
    for term in ("Carnosic", "4c00957", "Corilagin"):
        response = fetch(
            "Public Figshare metadata search: " + term,
            "https://api.figshare.com/v2/articles/search",
            {"search_for": term, "limit": 100},
        )
        results.append({"term": term, "response": response})
        print(term, len(response) if isinstance(response, list) else None, flush=True)
    output.write_text(
        json.dumps({"attempts": LOG, "search_results": results}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
