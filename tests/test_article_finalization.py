from axis.analysis import ArticleFinalizer


def test_article_reference_library_contains_primary_sources() -> None:
    references = ArticleFinalizer._references()

    assert "Ma2013DDX24" in references
    assert "Alber2022CITEseq" in references
    assert "Tang2025CD8" in references
    assert "Page2021PRISMA" in references
