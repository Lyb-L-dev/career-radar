"""本地语义向量与相似岗位测试（离线，不依赖任何嵌入模型）。"""

from pathlib import Path

from career_radar.embeddings import (
    VECTOR_DIMENSION,
    cosine_similarity,
    feature_hash_vector,
    job_embedding_text,
    pack_vector,
    unpack_vector,
)
from career_radar.models import JobPosting
from career_radar.storage import JobStorage, compute_job_hashes
from career_radar.web_repository import WebRepository


def _settings_yaml(tmp_path: Path) -> Path:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
app:
  database_path: data/test.db
  output_dir: output
  log_dir: logs
crawler:
  render_mode: never
  request_delay_min_seconds: 0
  request_delay_max_seconds: 0
  user_agent: Mozilla/5.0 test browser agent
llm:
  provider: openai
  model: test-model
companies:
  - name: 甲公司
    url: https://example.com/
""",
        encoding="utf-8",
    )
    return config_path


def test_feature_hash_vector_is_stable_and_fixed_size() -> None:
    text = "后端开发工程师 负责服务端设计与实现 熟悉 Python 微服务"
    first = feature_hash_vector(text)
    second = feature_hash_vector(text)

    assert first == second
    assert len(first) == VECTOR_DIMENSION


def test_similar_texts_have_higher_cosine() -> None:
    java = feature_hash_vector("Java 后端开发 微服务 分布式系统 数据库")
    java_related = feature_hash_vector("Java 后端开发 微服务 分布式 数据库设计")
    design = feature_hash_vector("平面设计 海报 视觉传达 品牌")

    assert cosine_similarity(java, java_related) > cosine_similarity(java, design)


def test_pack_unpack_roundtrip() -> None:
    values = [0.5, -0.25, 1.0, 0.0]

    assert unpack_vector(pack_vector(values)) == values


def test_job_embedding_text_contains_key_fields() -> None:
    job = JobPosting(
        title="后端开发",
        company="甲公司",
        location="福州",
        description="完整 JD 正文",
    )
    text = job_embedding_text(job)

    assert "甲公司" in text
    assert "后端开发" in text
    assert "福州" in text


def test_storage_embeddings_are_idempotent(tmp_path: Path) -> None:
    storage = JobStorage(tmp_path / "embeddings.db")
    storage.initialize()
    storage.store_jobs(
        [
            JobPosting(
                title="后端开发",
                company="甲公司",
                description="JD 正文" * 20,
            )
        ],
        "2026-08-07T00:00:00+08:00",
    )

    assert storage.ensure_job_embeddings("test", 32, feature_hash_vector) == 1
    assert storage.ensure_job_embeddings("test", 32, feature_hash_vector) == 0
    vectors = storage.load_job_embeddings()
    assert len(vectors) == 1

    assert storage.reset_job_embeddings() == 1
    assert storage.load_job_embeddings() == {}


def test_similar_jobs_ranks_semantic_matches(tmp_path: Path) -> None:
    config_path = _settings_yaml(tmp_path)
    repository = WebRepository(config_path)
    repository.initialize()
    storage = JobStorage(repository.settings.app.database_path)

    target = JobPosting(
        title="后端开发工程师",
        company="甲公司",
        location="福州",
        description=(
            "负责公司核心业务系统的设计与开发，参与 Java 微服务与分布式系统建设。"
            + "详细技术要求。" * 10
        ),
    )
    related = JobPosting(
        title="Java 后端开发",
        company="甲公司",
        location="厦门",
        description=(
            "负责微服务与分布式系统的开发维护，使用 Java、Spring Boot 与数据库。"
            + "详细技术要求。" * 10
        ),
    )
    unrelated = JobPosting(
        title="平面设计师",
        company="甲公司",
        location="深圳",
        description="负责品牌海报、视觉传达与活动物料设计。" + "设计说明。" * 10,
    )
    storage.store_jobs(
        [target, related, unrelated],
        "2026-08-07T00:00:00+08:00",
    )
    target_key = compute_job_hashes(target)[0]

    similar = repository.similar_jobs(target_key, limit=2)

    assert similar
    assert similar[0]["similarity"] > 0.3
    assert "后端" in similar[0]["title"] or "Java" in similar[0]["title"]
    assert "平面设计" not in similar[0]["title"]
