"""Counting tokens exactly as the embedding model will see them.

bge-small-en-v1.5 reads at most 512 tokens (2 of them are its [CLS]/[SEP] markers) and silently
ignores the rest, so a chunk measured in characters or words could lose its ending without any
error. Chunk sizes are therefore counted with the model's own WordPiece tokenizer.

Only `tokenizer.json` is loaded (the `tokenizers` library, no PyTorch), from the local Hugging Face
cache that scripts/download_models.py filled in M1.
"""

from __future__ import annotations

import threading
from typing import Protocol

MODEL_MAX_TOKENS = 512
SPECIAL_TOKENS = 2  # [CLS] and [SEP], added by the model around every input
MAX_CONTENT_TOKENS = MODEL_MAX_TOKENS - SPECIAL_TOKENS


class TokenCounter(Protocol):
    def offsets(self, text: str) -> list[tuple[int, int]]:
        """(start, end) character offsets of each token in `text`, without special tokens."""

    def count(self, text: str) -> int: ...


class HuggingFaceTokens:
    def __init__(self, model_name: str, *, local_only: bool = False) -> None:
        """`local_only=True` never touches the network (raises if the file isn't cached)."""
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        try:
            path = hf_hub_download(model_name, "tokenizer.json", local_files_only=True)
        except Exception:  # noqa: BLE001 - not cached yet
            if local_only:
                raise
            path = hf_hub_download(model_name, "tokenizer.json")  # fetch it once
        self._tokenizer = Tokenizer.from_file(path)
        self._tokenizer.no_truncation()  # count everything; never cut silently

    def offsets(self, text: str) -> list[tuple[int, int]]:
        return list(self._tokenizer.encode(text, add_special_tokens=False).offsets)

    def count(self, text: str) -> int:
        return len(self._tokenizer.encode(text, add_special_tokens=False).ids)


_cache: dict[str, HuggingFaceTokens] = {}
_lock = threading.Lock()


def get_tokens(model_name: str) -> HuggingFaceTokens:
    """One tokenizer per process (loading takes a few seconds), safe across worker threads."""
    with _lock:
        if model_name not in _cache:
            _cache[model_name] = HuggingFaceTokens(model_name)
        return _cache[model_name]
