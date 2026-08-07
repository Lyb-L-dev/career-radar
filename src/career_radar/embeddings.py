"""本地岗位语义向量：中文特征哈希 + 余弦相似度，零依赖、离线可用。

没有引入 sqlite-vec/嵌入模型，而是用“字符 n-gram 特征哈希”生成固定维度向量：
- 同一段岗位文本每次生成完全相同的向量（基于 SHA-256，不受进程随机种子影响）；
- 中文无需分词，按字符/词滑窗即可；
- 向量列以 float32 二进制存入 SQLite，后续若替换为 sqlite-vec 只需改存取层。
"""

from __future__ import annotations

import hashlib
import math
import re
from array import array

from .models import JobPosting

VECTOR_DIMENSION = 1024
PROVIDER_NAME = "char-hash-v1"
_MAX_EMBEDDING_CHARS = 4000
_TOKEN_RUN = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+")
_LATIN_RUN = re.compile(r"[a-z0-9]+")


def _char_ngrams(text: str, n: int = 2) -> list[str]:
    """英文/数字按词（并补充单字符），中文按 n-gram 滑窗，避免依赖分词。"""

    compact = "".join(text.split()).casefold()
    tokens: list[str] = []
    for run in _TOKEN_RUN.findall(compact):
        if _LATIN_RUN.fullmatch(run):
            tokens.append(run)
            tokens.extend(run[index : index + 1] for index in range(len(run)))
        else:
            tokens.extend(
                run[index : index + n] if index + n <= len(run) else run[index:]
                for index in range(len(run))
            )
    return tokens


def _stable_index_and_sign(token: str, dimension: int) -> tuple[int, float]:
    digest = hashlib.sha256(token.encode("utf-8")).digest()
    index = int.from_bytes(digest[:4], "big") % dimension
    sign = 1.0 if digest[4] & 1 else -1.0
    return index, sign


def feature_hash_vector(
    text: str,
    dimension: int = VECTOR_DIMENSION,
) -> list[float]:
    """把文本哈希成有符号向量，向量间可用余弦相似度直接比较。"""

    vector = [0.0] * dimension
    for token in _char_ngrams(text):
        index, sign = _stable_index_and_sign(token, dimension)
        vector[index] += sign
    return vector


def pack_vector(values: list[float]) -> bytes:
    """float32 小端二进制，方便存入 SQLite BLOB。"""

    return array("f", values).tobytes()


def unpack_vector(blob: bytes) -> list[float]:
    """把 BLOB 还原为向量。"""

    return list(array("f", blob))


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """余弦相似度；任一向量为零向量时返回 0。"""

    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for lv, rv in zip(left, right, strict=False):
        dot += lv * rv
        left_norm += lv * lv
        right_norm += rv * rv
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot / (math.sqrt(left_norm) * math.sqrt(right_norm))


def job_embedding_text(job: JobPosting) -> str:
    """用于相似度比较的岗位文本：公司 + 标题 + 地点 + JD 开头。"""

    parts = [
        job.company,
        job.title,
        job.location or "",
        (job.description or "")[: _MAX_EMBEDDING_CHARS],
    ]
    return "\n".join(parts)


def _char_bigrams(text: str) -> set[str]:
    """去掉空白后按字符滑窗生成二元组，中文无需分词。"""

    compact = re.sub(r"\s+", "", text).casefold()
    if not compact:
        return set()
    result = {compact[index : index + 2] for index in range(len(compact) - 1)}
    result.add(compact)
    return result


def jaccard_similarity(left: str, right: str) -> float:
    """字符二元组 Jaccard 相似度，用于“同一岗位换标题重发”的保守判定。

    实测：同岗位变体（换前缀/加急招后缀、JD 相同）约 0.68~0.87，
    不同岗位（即使共享公司福利样板文本）低于 0.05，0.6 阈值可安全区分。
    """

    left_grams = _char_bigrams(left)
    right_grams = _char_bigrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return len(left_grams & right_grams) / len(left_grams | right_grams)
