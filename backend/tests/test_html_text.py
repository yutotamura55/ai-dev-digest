from __future__ import annotations

from ai_dev_digest.html_text import html_to_text


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


def test_fragment_on_a_non_heading_element_ends_at_the_next_heading() -> None:
    html = '<p>intro</p><div id="note"><p>note 1</p></div><p>note 2</p><h3>Next</h3><p>after</p>'

    assert html_to_text(html, 500, "note") == "note 1\nnote 2"


def test_fragment_not_found_or_empty_falls_back_to_the_whole_page() -> None:
    assert html_to_text(RELEASE_NOTES, 500, "december-1-2026") == html_to_text(RELEASE_NOTES, 500)
    assert html_to_text(RELEASE_NOTES, 500, "") == html_to_text(RELEASE_NOTES, 500)
    assert html_to_text(RELEASE_NOTES, 500).startswith("Release notes\nNovember 3, 2026")


def test_fragment_section_skips_scripts_and_cuts_at_the_limit() -> None:
    html = '<h3 id="x">X</h3><script>var y;</script><p>body</p><h3>Y</h3>'

    assert html_to_text(html, 500, "x") == "X\nbody"
    assert html_to_text(html, 3, "x") == "X\nb"


def test_unbalanced_end_tags_do_not_break_extraction() -> None:
    assert html_to_text("</article></script><p>ok</p>", 100) == "ok"
