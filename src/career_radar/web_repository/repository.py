"""WebRepository 门面：组合各领域 Mixin，保持对外 API 不变。"""

from __future__ import annotations

from .base import BaseWebRepository
from .candidates import CandidatesMixin
from .companies import CompaniesMixin
from .jobs import JobsMixin
from .reputation import ReputationMixin
from .runs import RunsMixin
from .wechat import WechatMixin


class WebRepository(
    BaseWebRepository,
    JobsMixin,
    CompaniesMixin,
    CandidatesMixin,
    WechatMixin,
    ReputationMixin,
    RunsMixin,
):
    """围绕单个 config.yaml 的只读业务查询与少量 Web 状态写入。"""
