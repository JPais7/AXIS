import json
from datetime import UTC, datetime
from urllib.parse import parse_qs

import httpx
import pytest

from axis.ingestion import GeoApiError, GeoClient, GeoIngestionService
from axis.storage import EvidenceStore

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=UTC)

SUMMARY = {
    "uid": "200234339",
    "accession": "GSE234339",
    "title": "RIOK3 in ankylosing spondylitis",
    "summary": "RNA-seq of whole blood from patients and healthy controls.",
    "gpl": "24676",
    "taxon": "Homo sapiens",
    "entrytype": "GSE",
    "gdstype": "Expression profiling by high throughput sequencing",
    "pdat": "2024/01/12",
    "n_samples": 8,
    "pubmedids": ["38974235"],
    "bioproject": "PRJNA982001",
}


def mock_geo(request: httpx.Request) -> httpx.Response:
    params = parse_qs(request.url.query.decode())
    if request.url.path.endswith("/esearch.fcgi"):
        assert params["db"] == ["gds"]
        return httpx.Response(
            200,
            json={
                "esearchresult": {
                    "count": "1",
                    "retmax": "1",
                    "retstart": "0",
                    "idlist": ["200234339"],
                }
            },
        )
    if request.url.path.endswith("/esummary.fcgi"):
        assert params["id"] == ["200234339"]
        return httpx.Response(
            200,
            json={
                "result": {
                    "uids": ["200234339"],
                    "200234339": SUMMARY,
                }
            },
        )
    raise AssertionError(f"unexpected request: {request.url}")


def make_client(handler: httpx.MockTransport | None = None) -> GeoClient:
    transport = handler or httpx.MockTransport(mock_geo)
    return GeoClient(
        http_client=httpx.Client(transport=transport),
        clock=lambda: NOW,
    )


def test_search_restricts_results_to_series_and_parses_metadata() -> None:
    seen_search_term: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            params = parse_qs(request.url.query.decode())
            seen_search_term.extend(params["term"])
        return mock_geo(request)

    client = make_client(httpx.MockTransport(capture))

    page = client.search("axial spondyloarthritis[All Fields]", limit=1)

    assert page.total == 1
    assert seen_search_term == [
        "(axial spondyloarthritis[All Fields]) AND gse[Entry Type]"
    ]
    study = page.studies[0]
    assert study.identifier == "GSE234339"
    assert study.organisms == ("Homo sapiens",)
    assert study.platform_ids == ("GPL24676",)
    assert study.publication_ids == ("PMID:38974235",)
    assert study.sample_count == 8
    assert study.provenance.retrieved_at == NOW
    assert study.provenance.checksum.startswith("sha256:")


def test_metadata_normalizes_and_deduplicates_accessions() -> None:
    client = make_client()

    studies = client.metadata(["gse234339", "GSE234339"])

    assert tuple(study.identifier for study in studies) == ("GSE234339",)


def test_invalid_accession_is_rejected_before_network_request() -> None:
    def fail_on_request(_: httpx.Request) -> httpx.Response:
        raise AssertionError("network should not be called")

    client = make_client(httpx.MockTransport(fail_on_request))

    with pytest.raises(ValueError, match="invalid GEO Series"):
        client.metadata(["GDS123"])


def test_malformed_ncbi_response_has_a_domain_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"unexpected": {}}))
    )

    with pytest.raises(GeoApiError, match="esearchresult"):
        client.search("axSpA")


def test_ingestion_persists_discovered_study_and_is_repeatable() -> None:
    client = make_client()

    with EvidenceStore() as store:
        service = GeoIngestionService(client, store.studies)

        page = service.discover("ankylosing spondylitis", limit=1)
        service.discover("ankylosing spondylitis", limit=1)

        assert store.studies.list_all() == page.studies


def test_study_metadata_checksum_changes_with_source_record() -> None:
    changed_summary = {**SUMMARY, "summary": "Changed by submitter."}
    responses = iter((SUMMARY, changed_summary))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/esearch.fcgi"):
            return mock_geo(request)
        summary = next(responses)
        return httpx.Response(
            200,
            content=json.dumps(
                {
                    "result": {
                        "uids": ["200234339"],
                        "200234339": summary,
                    }
                }
            ),
        )

    client = make_client(httpx.MockTransport(handler))

    first = client.search("axSpA", limit=1).studies[0]
    second = client.search("axSpA", limit=1).studies[0]

    assert first.provenance.checksum != second.provenance.checksum
