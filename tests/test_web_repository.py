"""Web 岗位展示文本清洗测试。"""

from career_radar.web_repository import _display_text, _lines


def test_lines_merge_standalone_numbers_and_punctuation() -> None:
    raw = """岗位职责
1、
负责后端接口开发
；
2
参与数据库设计
。
"""

    assert _lines(raw) == ["1、负责后端接口开发；", "2 参与数据库设计。"]


def test_display_text_keeps_sections_but_removes_fragment_lines() -> None:
    raw = "任职要求\n（1）\n熟悉 Python\n，具备项目经验\n。"

    assert _display_text(raw) == "任职要求\n（1） 熟悉 Python，具备项目经验。"
