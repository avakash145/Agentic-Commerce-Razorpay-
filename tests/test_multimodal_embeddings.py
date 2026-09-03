import numpy as np
from PIL import Image

from app.catalog.embeddings import MultimodalEmbeddingModel


class FakeBackend:

    def encode_text(self, values):
        return np.ones((len(values), 512), dtype=np.float32)

    def encode_images(self, values):
        return np.ones((len(values), 512), dtype=np.float32)


def test_product_embedding_fuses_image_and_video_modalities():
    model = object.__new__(MultimodalEmbeddingModel)
    model.backend = FakeBackend()
    model._load_image = lambda url: Image.new("RGB", (8, 8), "white")

    document = {
        "embedding_text": "Laptop with RTX 3050",
        "image_urls": ["https://example.test/product.jpg"],
        "video_preview_urls": ["https://example.test/video-preview.jpg"],
        "video_urls": [],
    }

    vector = model.embed_documents([document])[0]
    query_vector = model.embed_query("RTX laptop")

    assert len(vector) == 512
    assert len(query_vector) == 512
    assert np.isclose(np.linalg.norm(vector), 1.0)
    assert np.isclose(np.linalg.norm(query_vector), 1.0)
    assert document["embedding_modalities"] == {
        "text": True,
        "images": 1,
        "video_frames": 1,
    }
