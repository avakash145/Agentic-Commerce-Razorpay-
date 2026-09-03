"""Multimodal product embeddings.

CLIP places text and images in the same 512-dimensional space. Product
documents are fused from a concise text representation (title, category,
specifications, features, and review summary), product images, and video
preview frames. The resulting vector can still be queried with plain user
text while using visual/video evidence for ranking.

OpenCLIP is used when available because it has a stable image/text API and
can load a local safetensors checkpoint. SentenceTransformers remains a
fallback for environments that already have the original CLIP model cached.
"""

import hashlib
import io
import os
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
import requests
from PIL import Image, UnidentifiedImageError
from langchain_huggingface import HuggingFaceEmbeddings

from dotenv import load_dotenv


load_dotenv()

MODEL_NAME = os.getenv(
    "MULTIMODAL_EMBEDDING_MODEL",
    "ViT-B-16",
)
SENTENCE_TRANSFORMER_MODEL_NAME = os.getenv(
    "SENTENCE_TRANSFORMER_EMBEDDING_MODEL",
    "clip-ViT-B-32",
)
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "open_clip").lower()
MULTIMODAL_DIMENSION = 512
IMAGE_LIMIT = int(os.getenv("EMBEDDING_IMAGE_LIMIT", "4"))
IMAGE_TIMEOUT = float(os.getenv("EMBEDDING_IMAGE_TIMEOUT", "12"))
MAX_IMAGE_BYTES = int(os.getenv("EMBEDDING_MAX_IMAGE_BYTES", "8000000"))
CACHE_DIR = Path(
    os.getenv(
        "EMBEDDING_IMAGE_CACHE_DIR",
        "/tmp/agentic-commerce-image-cache",
    )
)


def _local_openclip_checkpoint(model_name):
    """Find an already-cached OpenCLIP safetensors checkpoint."""

    explicit_path = os.getenv("OPENCLIP_CHECKPOINT")
    if explicit_path and Path(explicit_path).is_file():
        return Path(explicit_path)

    cache_root = Path(
        os.getenv(
            "HF_HOME",
            str(Path.home() / ".cache" / "huggingface"),
        )
    ) / "hub"
    model_dirs = {
        "ViT-B-16": "models--timm--vit_base_patch16_clip_224.openai",
        "ViT-B-32": "models--timm--vit_base_patch32_clip_224.openai",
    }
    model_dir = cache_root / model_dirs.get(model_name, "")
    if not model_dir.exists():
        return None

    checkpoints = sorted(
        model_dir.glob("snapshots/*/open_clip_model.safetensors")
    )
    return checkpoints[-1] if checkpoints else None


class _OpenClipBackend:

    def __init__(self):
        import open_clip
        import torch

        self.torch = torch
        self.device = os.getenv("EMBEDDING_DEVICE", "cpu")
        checkpoint = _local_openclip_checkpoint(MODEL_NAME)
        pretrained = str(checkpoint) if checkpoint else os.getenv(
            "OPENCLIP_PRETRAINED",
            "openai",
        )
        self.model, _, self.preprocess = (
            open_clip.create_model_and_transforms(
                MODEL_NAME,
                pretrained=pretrained,
                device=self.device,
            )
        )
        self.model.eval()
        self.tokenizer = open_clip.get_tokenizer(MODEL_NAME)

    def encode_text(self, values):
        tokens = self.tokenizer(values).to(self.device)
        with self.torch.no_grad():
            vectors = self.model.encode_text(tokens)
        return vectors.float().cpu().numpy()

    def encode_images(self, values):
        tensors = self.torch.stack(
            [self.preprocess(image) for image in values]
        ).to(self.device)
        with self.torch.no_grad():
            vectors = self.model.encode_image(tensors)
        return vectors.float().cpu().numpy()


class _SentenceTransformerBackend:

    def __init__(self):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(
            SENTENCE_TRANSFORMER_MODEL_NAME,
            device=os.getenv("EMBEDDING_DEVICE", "cpu"),
        )

    def encode_text(self, values):
        return self.model.encode(
            values,
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def encode_images(self, values):
        return self.model.encode(
            values,
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )


class MultimodalEmbeddingModel:

    def __init__(self):
        backend_error = None
        if EMBEDDING_BACKEND in {"open_clip", "auto"}:
            try:
                self.backend = _OpenClipBackend()
            except Exception as exc:
                backend_error = exc

        if not hasattr(self, "backend"):
            if EMBEDDING_BACKEND == "open_clip":
                raise RuntimeError(
                    "OpenCLIP could not be loaded. Install open_clip_torch "
                    "or set OPENCLIP_CHECKPOINT to a local safetensors file."
                ) from backend_error
            self.backend = _SentenceTransformerBackend()

        dimension = self.backend.encode_text(["dimension check"]).shape[-1]
        if dimension != MULTIMODAL_DIMENSION:
            raise ValueError(
                f"{MODEL_NAME} returned {dimension} dimensions; "
                f"expected {MULTIMODAL_DIMENSION}"
            )
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "AgenticCommerce/2.0 image embedding worker",
            "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
        })

    @staticmethod
    def _normalize(vector):
        vector = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(vector)
        return vector if norm == 0 else vector / norm

    @staticmethod
    def _cache_path(url):
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return CACHE_DIR / f"{digest}.img"

    def _load_image(self, url):
        if not url:
            return None

        cache_path = self._cache_path(url)
        try:
            if cache_path.exists() and cache_path.stat().st_size <= MAX_IMAGE_BYTES:
                return Image.open(cache_path).convert("RGB")
        except (OSError, UnidentifiedImageError):
            cache_path.unlink(missing_ok=True)

        try:
            response = self.session.get(url, timeout=IMAGE_TIMEOUT)
            response.raise_for_status()
            if len(response.content) > MAX_IMAGE_BYTES:
                return None
            image = Image.open(io.BytesIO(response.content)).convert("RGB")
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(response.content)
            return image
        except (requests.RequestException, OSError, UnidentifiedImageError):
            return None

    def _video_frame(self, url):
        """Read one frame from a local/direct video when no preview exists.

        Amazon HLS URLs are intentionally not downloaded here; the crawler's
        previewImageUrl is the stable, lightweight representation for those
        streams. OpenCV remains optional for local or direct MP4 files.
        """

        if not url:
            return None
        parsed = urlparse(url)
        if parsed.scheme in {"http", "https"}:
            return None
        try:
            import cv2
            capture = cv2.VideoCapture(url)
            ok, frame = capture.read()
            capture.release()
            if not ok:
                return None
            return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        except (ImportError, OSError, ValueError):
            return None

    def _visual_inputs(self, document):
        image_urls = list(dict.fromkeys(document.get("image_urls") or []))
        preview_urls = list(dict.fromkeys(document.get("video_preview_urls") or []))
        images = [
            image
            for url in image_urls[:IMAGE_LIMIT]
            if (image := self._load_image(url)) is not None
        ]
        video_frames = [
            image
            for url in preview_urls[:IMAGE_LIMIT]
            if (image := self._load_image(url)) is not None
        ]

        if not video_frames:
            for url in (document.get("video_urls") or [])[:IMAGE_LIMIT]:
                frame = self._video_frame(url)
                if frame is not None:
                    video_frames.append(frame)

        return images, video_frames

    def embed_query(self, query):
        vector = self.backend.encode_text([query])[0]
        return self._normalize(vector).tolist()

    def embed_documents(self, documents):
        texts = [
            document.get("embedding_text")
            or document.get("content")
            or ""
            for document in documents
        ]
        text_vectors = self.backend.encode_text(texts)

        visual_inputs = []
        video_inputs = []
        visual_ranges = []
        video_ranges = []
        for document in documents:
            images, video_frames = self._visual_inputs(document)
            visual_ranges.append((len(visual_inputs), len(images)))
            video_ranges.append((len(video_inputs), len(video_frames)))
            visual_inputs.extend(images)
            video_inputs.extend(video_frames)

        visual_vectors = []
        if visual_inputs:
            visual_vectors = self.backend.encode_images(visual_inputs)

        video_vectors = []
        if video_inputs:
            video_vectors = self.backend.encode_images(video_inputs)

        vectors = []
        for index, (document, text_vector) in enumerate(zip(documents, text_vectors)):
            image_start, image_count = visual_ranges[index]
            video_start, video_count = video_ranges[index]
            image_vector = None
            video_vector = None

            if image_count:
                image_vector = self._normalize(
                    visual_vectors[image_start:image_start + image_count].mean(axis=0)
                )
            if video_count:
                video_vector = self._normalize(
                    video_vectors[video_start:video_start + video_count].mean(axis=0)
                )

            # Text is always present and carries exact product specs. Visual
            # and video evidence influence ranking when available.
            fused = 0.60 * self._normalize(text_vector)
            if image_vector is not None:
                fused += 0.25 * image_vector
            if video_vector is not None:
                fused += 0.15 * video_vector

            fused = self._normalize(fused)
            document["embedding_modalities"] = {
                "text": True,
                "images": image_count,
                "video_frames": video_count,
            }
            vectors.append(fused.tolist())

        return vectors


def get_embedding_model():
    global _multimodal_model, _multimodal_error
    if _multimodal_model is not None:
        return _multimodal_model
    if _multimodal_error is not None:
        raise _multimodal_error
    try:
        _multimodal_model = MultimodalEmbeddingModel()
        return _multimodal_model
    except Exception as exc:
        _multimodal_error = exc
        raise


_multimodal_model = None
_multimodal_error = None
_legacy_model = None


def get_legacy_embedding_model():
    global _legacy_model
    if _legacy_model is None:
        _legacy_model = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={
                "device": os.getenv("EMBEDDING_DEVICE", "cpu")
            },
            encode_kwargs={"normalize_embeddings": True},
        )
    return _legacy_model
