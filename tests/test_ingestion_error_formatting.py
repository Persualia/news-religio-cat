import httpx

from pipeline.ingestion import _format_scraper_error


def test_format_scraper_error_for_connect_timeout():
    message = _format_scraper_error("escolapia", httpx.ConnectTimeout("timed out"))

    assert "Timeout de conexion" in message
    assert "'escolapia'" in message


def test_format_scraper_error_for_read_timeout():
    message = _format_scraper_error("peretarres", httpx.ReadTimeout("timed out"))

    assert "Timeout de lectura" in message
    assert "'peretarres'" in message


def test_format_scraper_error_for_tls_connect_error():
    message = _format_scraper_error(
        "gter",
        httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"),
    )

    assert "TLS/certificado" in message
    assert "'gter'" in message


def test_format_scraper_error_for_network_unreachable_connect_error():
    message = _format_scraper_error(
        "islamat",
        httpx.ConnectError("[Errno 101] Network is unreachable"),
    )

    assert "Red inaccesible" in message
    assert "'islamat'" in message
