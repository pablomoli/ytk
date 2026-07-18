"""Second-stage reranking with Qwen3-Reranker-0.6B (#86).

The bi-encoder (store) fetches candidates from vector geometry computed
before the query existed; the reranker reads query and document together
and scores how well that document answers that question. Same model family
and size as the v2 embedder, same MPS budget rules (fp16, small batches,
logits_to_keep — see QwenReranker.score).

Pure functions (build_prompt, rerank) are model-free and unit-tested;
QwenReranker loads the model lazily on first score() call. Config knobs
(candidate depth, truncation length) are deliberately parameters, not
constants: the quality/latency tradeoff is measured by
experiments/rerank_bench.py, and production settings follow that data.
"""

from __future__ import annotations

from typing import Callable, Sequence, TypeVar

T = TypeVar("T")

MODEL_NAME = "Qwen/Qwen3-Reranker-0.6B"
MODEL_REVISION = "e61197ed45024b0ed8a2d74b80b4d909f1255473"
# same instruction the v2 embedder's query prefix uses (store._EPOCHS)
INSTRUCT = "Given a web search query, retrieve relevant passages that answer the query"
_PREFIX = (
    "<|im_start|>system\nJudge whether the Document meets the requirements "
    'based on the Query and the Instruct provided. Note that the answer can '
    'only be "yes" or "no".<|im_end|>\n<|im_start|>user\n'
)
_SUFFIX = "<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def build_prompt(query: str, doc: str, instruct: str = INSTRUCT) -> str:
    """Chat-format prompt whose final token's yes/no logits are the score."""
    return f"{_PREFIX}<Instruct>: {instruct}\n<Query>: {query}\n<Document>: {doc}{_SUFFIX}"


def rerank(
    query: str,
    items: Sequence[T],
    texts: Sequence[str],
    scorer: Callable[[str, Sequence[str]], Sequence[float]],
    top_n: int | None = None,
) -> list[T]:
    """Reorder items by scorer(query, texts), descending.

    Ties keep first-stage order: the bi-encoder ranking is the tiebreak.
    """
    if len(items) != len(texts):
        raise ValueError(f"{len(items)} items but {len(texts)} texts")
    if not items:
        return []
    scores = scorer(query, texts)
    order = sorted(range(len(items)), key=lambda i: (-scores[i], i))
    out = [items[i] for i in order]
    return out[:top_n] if top_n is not None else out


class QwenReranker:
    """Lazy-loading cross-encoder scorer; instances are scorer callables."""

    def __init__(self, model_name: str = MODEL_NAME,
                 revision: str | None = MODEL_REVISION,
                 max_length: int = 2560, batch: int = 4,
                 device: str | None = None):
        self._model_name = model_name
        self._revision = revision
        self._max_length = max_length
        self._batch = batch
        self._device = device  # None = MPS if available, else CPU
        self._model = None
        self._tokenizer = None
        self._yes_id: int | None = None
        self._no_id: int | None = None

    def _load(self):
        if self._model is None:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer

            if self._device is None:
                self._device = "mps" if torch.backends.mps.is_available() else "cpu"
            self._tokenizer = AutoTokenizer.from_pretrained(
                self._model_name, revision=self._revision, padding_side="left"
            )
            self._model = AutoModelForCausalLM.from_pretrained(
                self._model_name, revision=self._revision, torch_dtype=torch.float16
            ).to(self._device).eval()
            self._yes_id = self._tokenizer.convert_tokens_to_ids("yes")
            self._no_id = self._tokenizer.convert_tokens_to_ids("no")

    def __call__(self, query: str, docs: Sequence[str]) -> list[float]:
        return self.score(query, docs)

    def score(self, query: str, docs: Sequence[str]) -> list[float]:
        """P(yes) per (query, doc) pair, batched for the MPS budget."""
        import torch

        self._load()
        texts = [build_prompt(query, d) for d in docs]
        scores: list[float] = []
        with torch.no_grad():
            for i in range(0, len(texts), self._batch):
                batch = self._tokenizer(
                    texts[i:i + self._batch], padding=True, truncation=True,
                    max_length=self._max_length, return_tensors="pt",
                ).to(self._device)
                # logits_to_keep=1: full-sequence logits are batch x seq x
                # 152k vocab (~3 GB fp16 at 2560 tokens) and thrash MPS
                # memory; only the final position is needed
                logits = self._model(**batch, logits_to_keep=1).logits[:, -1, :]
                pair = torch.stack(
                    [logits[:, self._no_id], logits[:, self._yes_id]], dim=1
                ).float()
                scores.extend(torch.softmax(pair, dim=1)[:, 1].tolist())
        return scores
