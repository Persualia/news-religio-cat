"""Initialize OpenSearch templates and monthly indices."""
from opensearch_client import get_client
from pipeline.opensearch_ops import ensure_monthly_indices, ensure_templates


def main() -> None:
    client = get_client()
    ensure_templates(client)
    articles_index, chunks_index = ensure_monthly_indices(client)
    print(f"Ensured indices: {articles_index}, {chunks_index}")


if __name__ == "__main__":
    main()
