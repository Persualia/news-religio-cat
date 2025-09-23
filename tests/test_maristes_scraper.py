from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from scraping.maristes import MaristesScraper

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> BeautifulSoup:
    html = (FIXTURES / name).read_text(encoding="utf-8")
    return BeautifulSoup(html, "lxml")


def test_extract_article_urls():
    scraper = MaristesScraper()
    soup = load_fixture("maristes_listing.html")
    urls = list(scraper.extract_article_urls(soup))
    assert urls == [
        "https://www.maristes.cat/noticies/primera-noticia/",
        "https://www.maristes.cat/noticies/segona-noticia/",
    ]


def test_parse_article_success_with_elementor_heading():
    scraper = MaristesScraper()
    soup = load_fixture("maristes_article.html")
    article = scraper.parse_article(
        soup,
        "https://www.maristes.cat/noticies/un-exemple-damor-i-servei-el-germa-marista-licario-ja-es-beat",
    )

    assert article.site == "maristes"
    assert article.base_url == scraper.base_url
    assert article.lang == "ca"
    assert article.title == "“Un exemple d’amor i servei”: el germà marista Licarió ja és beat"
    assert "Primer paràgraf" in article.content
    assert article.description is None
    assert article.author is None
    assert article.published_at == datetime(2024, 9, 3, 8, 0, tzinfo=timezone.utc)


def test_parse_article_fallback_title_from_meta():
    scraper = MaristesScraper()
    soup = BeautifulSoup(
        """
        <html lang='ca'>
          <head>
            <meta charset='utf-8' />
            <meta property='og:title' content='Relleu a la direcció general de la Fundació Champagnat-Maristes Catalunya' />
          </head>
          <body>
            <div class='field-item even' property='dc:title'>
              <span>Relleu a la direcció general de la Fundació Champagnat-Maristes Catalunya</span>
            </div>
            <article>
              <div class='elementor-widget-theme-post-content'>
                <p>Text sense capçalera principal.</p>
              </div>
            </article>
          </body>
        </html>
        """,
        "lxml",
    )
    article = scraper.parse_article(soup, "https://www.maristes.cat/noticies/relleu-la-direccio-general-de-la-fundacio-champagnat-maristes-catalunya")

    assert article.title == "Relleu a la direcció general de la Fundació Champagnat-Maristes Catalunya"
    assert article.content.startswith("Text sense capçalera")
