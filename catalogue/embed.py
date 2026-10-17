"""Embed every catalogue item once. Writes embeddings.npy and embedding_ids.json.

Uses fastembed (ONNX, CPU, no torch). On an AMD GPU, swap the provider here.
If the model cannot be downloaded, falls back to a hashed bag-of-words vector and says so.
Run: python catalogue/embed.py
"""

import json
import sys
import zlib
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
MODEL = "BAAI/bge-small-en-v1.5"


def item_text(item: dict) -> str:
    parts = [
        item["name"], item["category"], item["description"],
        "colours: " + ", ".join(item["colours"]),
        "materials: " + ", ".join(item["materials"]),
        "formality: " + item["formality"].replace("_", " "),
        "occasions: " + ", ".join(item["occasions"]),
    ]
    if item.get("vision_tags"):
        parts.append("looks like: " + json.dumps(item["vision_tags"]))
    return ". ".join(parts)


def hashed_bow(texts: list[str], dim: int = 512) -> np.ndarray:
    out = np.zeros((len(texts), dim), dtype=np.float32)
    for i, t in enumerate(texts):
        for w in t.lower().replace(",", " ").replace(".", " ").split():
            out[i, zlib.crc32(w.encode()) % dim] += 1.0  # stable across runs
    return out


def embed(texts: list[str]) -> tuple[np.ndarray, str]:
    try:
        from fastembed import TextEmbedding

        model = TextEmbedding(MODEL)
        vecs = np.array(list(model.embed(texts)), dtype=np.float32)
        backend = f"fastembed {MODEL} (CPU)"
    except Exception as e:  # network or model download failure
        print(f"fastembed unavailable ({e.__class__.__name__}: {e}); using hashed bag-of-words", file=sys.stderr)
        vecs = hashed_bow(texts)
        backend = "hashed bag-of-words fallback"
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9
    return vecs, backend


def main() -> None:
    data = json.loads((HERE / "catalogue.json").read_text())
    tags_path = HERE / "vision_tags.json"
    tags = json.loads(tags_path.read_text()) if tags_path.exists() else {}
    for item in data["items"]:
        item["vision_tags"] = tags.get(item["id"], item.get("vision_tags"))
    vecs, backend = embed([item_text(i) for i in data["items"]])
    np.save(HERE / "embeddings.npy", vecs)
    meta = {"model": MODEL, "backend": backend, "dim": int(vecs.shape[1]), "ids": [i["id"] for i in data["items"]]}
    (HERE / "embedding_ids.json").write_text(json.dumps(meta, indent=2))
    print(f"embedded {len(data['items'])} items, dim {vecs.shape[1]}, backend: {backend}")


if __name__ == "__main__":
    main()
