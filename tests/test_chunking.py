from chunking import chunk_text


def test_chunk_text_basic_split():
    text = " ".join(str(i) for i in range(100))
    chunks = chunk_text(text, max_words=20, overlap=5)
    assert len(chunks) > 1
    assert "0" in chunks[0]
    assert "99" in chunks[-1]


def test_chunk_text_overlap_validation():
    try:
        chunk_text("hola", max_words=10, overlap=15)
    except ValueError as err:
        assert "max_words" in str(err)
    else:
        raise AssertionError("Expected ValueError for invalid overlap")
