from langchain_core.documents import Document

from app.core.image_vectorstore import _image_doc_id


def test_image_doc_id_prefers_block_id_when_present():
    doc = Document(
        page_content="image",
        metadata={
            "doc_id": "doc-1",
            "page": 3,
            "chunk": 9,
            "block_id": "p3:i2",
        },
    )

    assert _image_doc_id(doc) == "doc-1:bp3:i2:img"


def test_image_doc_id_falls_back_to_page_chunk_when_block_id_missing():
    doc = Document(
        page_content="image",
        metadata={
            "doc_id": "doc-2",
            "page": 5,
            "chunk": 12,
        },
    )

    assert _image_doc_id(doc) == "doc-2:p5:c12:img"
