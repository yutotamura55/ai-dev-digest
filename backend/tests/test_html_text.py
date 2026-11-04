from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from ai_dev_digest.html_text import html_to_text, published_at_from_html


def test_uses_only_the_article_when_the_page_has_one() -> None:
    html = (
        "<html><body><p>Intro</p><article><p>Real</p><p>text</p></article>"
        "<p>Footer</p></body></html>"
    )

    assert html_to_text(html, 100) == "Real\ntext"


def test_falls_back_to_main_and_then_to_the_whole_page() -> None:
    assert html_to_text("<div>Side</div><main>Main <b>text</b></main>", 100) == "Main text"
    assert html_to_text("<p>One</p><p>Two</p>", 100) == "One\nTwo"


def test_skips_scripts_styles_and_navigation() -> None:
    html = (
        "<nav>Menu</nav><header>Head</header><script>var x=1;</script><style>p{}</style>"
        "<p>Kept</p><footer>Foot</footer>"
    )

    assert html_to_text(html, 100) == "Kept"


def test_collapses_whitespace_and_decodes_entities() -> None:
    assert html_to_text("<p>  a &amp;\t b </p>\n\n<p>c</p>", 100) == "a & b\nc"


def test_plain_text_passes_through_and_is_cut_at_the_limit() -> None:
    assert html_to_text("plain summary", 100) == "plain summary"
    assert html_to_text("plain summary", 5) == "plain"


RELEASE_NOTES = (
    "<main><h1>Release notes</h1>"
    '<h3 id="november-3-2026">November 3, 2026</h3><p>Added <b>threads</b>.</p>'
    "<ul><li>Item A</li></ul>"
    '<h3 id="november-2-2026">November 2, 2026</h3><p>Older change.</p>'
    "</main>"
)


def test_fragment_returns_only_the_section_that_starts_at_the_heading() -> None:
    assert html_to_text(RELEASE_NOTES, 500, "november-3-2026") == (
        "November 3, 2026\nAdded threads.\nItem A"
    )
    assert html_to_text(RELEASE_NOTES, 500, "november-2-2026") == "November 2, 2026\nOlder change."


def test_fragment_section_ends_at_a_higher_heading_but_includes_lower_ones() -> None:
    html = '<h2 id="a">A</h2><p>a1</p><h3>A detail</h3><p>a2</p><h2 id="b">B</h2><p>b1</p>'

    assert html_to_text(html, 500, "a") == "A\na1\nA detail\na2"


def test_fragment_on_a_non_heading_element_ends_at_its_end_tag() -> None:
    html = '<p>intro</p><div id="note"><p>note 1</p></div><p>note 2</p><h3>Next</h3><p>after</p>'

    assert html_to_text(html, 500, "note") == "note 1"


def test_fragment_on_an_empty_anchor_adopts_the_next_heading() -> None:
    html = (
        '<p>intro</p><a id="d3"></a><h3>Nov 3</h3><p>today</p><h4>Detail</h4><p>d</p><h3>Nov 2</h3>'
    )

    assert html_to_text(html, 500, "d3") == "Nov 3\ntoday\nDetail\nd"


def test_fragment_not_found_or_empty_falls_back_to_the_whole_page(
    caplog: pytest.LogCaptureFixture,
) -> None:
    assert html_to_text(RELEASE_NOTES, 500, "december-1-2026") == html_to_text(RELEASE_NOTES, 500)
    assert "fragment #december-1-2026 not found" in caplog.text
    assert html_to_text(RELEASE_NOTES, 500, "") == html_to_text(RELEASE_NOTES, 500)
    assert html_to_text(RELEASE_NOTES, 500).startswith("Release notes\nNovember 3, 2026")


def test_fragment_on_a_container_ends_at_its_end_tag_even_with_headings_inside() -> None:
    html = (
        '<main><section id="d3"><h3>Nov 3</h3><p>today<br>more</p></section>'
        '<section id="d2"><h3>Nov 2</h3><p>old</p></section></main>'
    )

    assert html_to_text(html, 500, "d3") == "Nov 3\ntoday\nmore"


def test_fragment_section_does_not_leave_the_main_element() -> None:
    html = (
        '<main><h3 id="d3">Nov 3</h3><p>today</p></main>'
        "<aside><p>Was this helpful?</p><div>cookie banner</div></aside>"
    )

    assert html_to_text(html, 500, "d3") == "Nov 3\ntoday"


def test_fragment_matches_the_name_of_an_anchor() -> None:
    html = '<p>intro</p><a name="2026-11-03"></a><h3>Nov 3</h3><p>today</p><h3>Nov 2</h3>'

    assert html_to_text(html, 500, "2026-11-03") == "Nov 3\ntoday"


def test_fragment_inside_a_skipped_element_is_ignored() -> None:
    html = '<header><h1 id="top">Title</h1></header><p>intro</p><h2>Next</h2>'

    assert html_to_text(html, 500, "top") == html_to_text(html, 500)


def test_headings_inside_skipped_elements_do_not_end_the_section() -> None:
    html = (
        '<main><h3 id="x">X</h3><p>one</p><nav><h2>Navigation</h2></nav><p>two</p><h3>Y</h3></main>'
    )

    assert html_to_text(html, 500, "x") == "X\none\ntwo"


def test_skipped_elements_inside_a_container_do_not_end_the_section() -> None:
    html = '<main><div id="x"><p>one</p><nav>Navigation</nav><p>two</p></div><p>after</p></main>'

    assert html_to_text(html, 500, "x") == "one\ntwo"


def test_fragment_on_an_anchor_inside_a_heading_uses_that_heading_as_the_section() -> None:
    empty = '<h3><a id="x"></a>X</h3><p>today</p><h3>Y</h3><p>yesterday</p>'
    filled = '<h3><a id="x">X</a></h3><p>today</p><h3>Y</h3><p>yesterday</p>'

    assert html_to_text(empty, 500, "x") == "X\ntoday"
    assert html_to_text(filled, 500, "x") == "X\ntoday"


def test_fragment_section_does_not_leave_an_article_nested_in_main() -> None:
    html = (
        '<main><article><h3 id="x">X</h3><p>body</p></article>'
        "<aside>Unrelated sidebar</aside></main>"
    )

    assert html_to_text(html, 500, "x") == "X\nbody"


def test_fragment_prefers_the_heading_over_an_earlier_duplicate_id() -> None:
    html = (
        '<div class="toc"><a id="d3">Nov 3</a><a id="d2">Nov 2</a></div>'
        '<h3 id="d3">November 3</h3><p>today</p><h3 id="d2">November 2</h3><p>old</p>'
    )

    assert html_to_text(html, 500, "d3") == "November 3\ntoday"


def test_fragment_section_skips_scripts_and_cuts_at_the_limit() -> None:
    html = '<h3 id="x">X</h3><script>var y;</script><p>body</p><h3>Y</h3>'

    assert html_to_text(html, 500, "x") == "X\nbody"
    assert html_to_text(html, 3, "x") == "X\nb"


def test_unbalanced_end_tags_do_not_break_extraction() -> None:
    assert html_to_text("</article></script><p>ok</p>", 100) == "ok"


def ld(payload: str) -> str:
    return f'<script type="application/ld+json">{payload}</script>'


def test_published_at_from_json_ld_date_only_is_midnight_utc() -> None:
    html = (
        "<html><head>"
        + ld('{"@type": "Article", "datePublished": "2026-11-03"}')
        + "</head></html>"
    )

    assert published_at_from_html(html) == datetime(2026, 11, 3, tzinfo=UTC)


def test_published_at_from_json_ld_with_time_zone_is_converted_to_utc() -> None:
    html = ld('{"datePublished": "2026-11-03T09:30:00+09:00"}')

    assert published_at_from_html(html) == datetime(2026, 11, 3, 0, 30, tzinfo=UTC)
    assert published_at_from_html(ld('{"datePublished": "2026-11-03T00:30:00Z"}')) == datetime(
        2026, 11, 3, 0, 30, tzinfo=UTC
    )


def test_published_at_assumes_utc_for_a_naive_datetime() -> None:
    assert published_at_from_html(ld('{"datePublished": "2026-11-03T01:00:00"}')) == datetime(
        2026, 11, 3, 1, 0, tzinfo=timezone(timedelta(0))
    )


def test_published_at_searches_nested_graph_and_skips_other_scripts() -> None:
    html = (
        ld('{"@type": "BreadcrumbList", "itemListElement": []}')
        + ld("not json at all")
        + ld(
            '{"@graph": [{"@type": "WebPage"}, '
            '{"@type": "Article", "datePublished": "2026-10-30"}]}'
        )
    )

    assert published_at_from_html(html) == datetime(2026, 10, 30, tzinfo=UTC)


def test_published_at_falls_back_to_meta_tags() -> None:
    html = (
        '<meta property="article:published_time" content="2026-11-02T17:45:00+00:00">'
        '<meta name="published_time" content="2026-11-01">'
    )

    assert published_at_from_html(html) == datetime(2026, 11, 2, 17, 45, tzinfo=UTC)


def test_published_at_is_none_without_a_usable_date() -> None:
    assert published_at_from_html("<p>no metadata</p>") is None
    assert published_at_from_html('<meta name="description" content="2026-11-03">') is None
    assert published_at_from_html(ld('{"datePublished": "yesterday"}')) is None
    assert published_at_from_html('<meta property="article:published_time" content="">') is None
