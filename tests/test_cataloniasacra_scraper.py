from datetime import datetime, timezone

from bs4 import BeautifulSoup

from scraping.cataloniasacra import CataloniaSacraScraper

def load_listing() -> BeautifulSoup:
    html = """
    <html>
      <body>
        <article class="et_pb_post">
          <h2 class="entry-title">
            <a href="https://www.cataloniasacra.cat/presentacio-de-lagenda-dactivitats-2026-de-catalonia-sacra/">
              Presentacio de l'Agenda d'Activitats 2026 de Catalonia Sacra
            </a>
          </h2>
          <p class="post-meta"><span class="published">08/02/2026</span></p>
          <div class="post-content">
            <div class="post-content-inner">
              <p>La cripta de la Colonia Guell acull l'acte de presentacio de l'agenda.</p>
            </div>
          </div>
        </article>
      </body>
    </html>
    """
    return BeautifulSoup(html, "lxml")


def test_extract_items_from_listing():
    scraper = CataloniaSacraScraper()
    soup = load_listing()

    items = list(scraper.extract_items(soup))

    assert items
    first = items[0]
    assert first.title == "Presentacio de l'Agenda d'Activitats 2026 de Catalonia Sacra"
    assert first.url == "https://www.cataloniasacra.cat/presentacio-de-lagenda-dactivitats-2026-de-catalonia-sacra"
    assert first.summary.startswith("La cripta de la Colonia Guell")
    assert first.published_at == datetime(2026, 2, 8, tzinfo=timezone.utc)
