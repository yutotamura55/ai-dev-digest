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


def test_unbalanced_end_tags_do_not_break_extraction() -> None:
    assert html_to_text("</article></script><p>ok</p>", 100) == "ok"
