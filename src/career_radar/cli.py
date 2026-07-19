"""Career Radar 命令行入口。"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from . import __version__
from .config import ConfigError, load_settings
from .logging_setup import configure_logging
from .pipeline import MonitorService
from .storage import JobStorage


def _parser() -> argparse.ArgumentParser:
    """构造子命令；所有路径默认指向当前目录的 config.yaml。"""

    parser = argparse.ArgumentParser(
        prog="career-radar",
        description="企业官网招聘信息自动监控与完整 JD 提取工具",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-c", "--config", default="config.yaml", help="YAML 配置文件路径")

    run = subparsers.add_parser("run", parents=[common], help="执行一次完整监控")
    run.add_argument(
        "--company",
        action="append",
        default=[],
        help="只运行指定公司；可重复传入，默认运行所有 enabled 公司",
    )

    serve = subparsers.add_parser(
        "serve",
        parents=[common],
        help="启动仅监听本机的 FastAPI 与 Web 管理端",
    )
    serve.add_argument("--host", default="127.0.0.1", help="监听地址；默认仅本机")
    serve.add_argument("--port", type=int, default=8000, help="监听端口")
    serve.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )
    run.add_argument("--dry-run", action="store_true", help="抓取并分析，但不写数据库/报表/邮件")
    run.add_argument("--no-email", action="store_true", help="本次运行禁止邮件通知")
    run.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
    )

    subparsers.add_parser("check-config", parents=[common], help="只校验配置，不访问网络")
    subparsers.add_parser("init-db", parents=[common], help="初始化 SQLite 数据库")
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析参数并返回适合 cron/任务计划判断的退出码。"""

    args = _parser().parse_args(argv)
    try:
        settings = load_settings(Path(args.config))
        if args.command == "check-config":
            enabled = sum(company.enabled for company in settings.companies)
            print(f"配置有效：共 {len(settings.companies)} 家公司，启用 {enabled} 家。")
            return 0
        if args.command == "init-db":
            JobStorage(settings.app.database_path).initialize()
            print(f"数据库已初始化：{settings.app.database_path}")
            return 0
        if args.command == "serve":
            if args.host not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Web 管理端默认只允许监听本机地址；如需远程访问请先配置认证和 HTTPS")
            configure_logging(settings.app.log_dir, args.log_level)
            os.environ["CAREER_RADAR_CONFIG"] = str(Path(args.config).resolve())
            try:
                import uvicorn
            except ImportError as exc:
                raise RuntimeError("未安装 FastAPI Web 依赖，请执行 pip install -e .") from exc
            from .api import create_app

            web_app = create_app(os.environ["CAREER_RADAR_CONFIG"])

            uvicorn.run(
                web_app,
                host="127.0.0.1" if args.host == "localhost" else args.host,
                port=args.port,
                log_level=args.log_level.casefold(),
            )
            return 0

        configure_logging(settings.app.log_dir, args.log_level)
        result = MonitorService(settings).run(
            company_names=set(args.company) or None,
            dry_run=args.dry_run,
            disable_email=args.no_email,
        )
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        # 单个站点失败不会让整批中止；只要主流程完成就返回 0，异常详情在 JSON/日志中。
        return 0
    except (ConfigError, ValueError, RuntimeError) as exc:
        logging.getLogger(__name__).error("运行失败：%s", exc)
        print(f"错误：{exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        # 文件权限、SQLite 驱动等环境问题也应给定时任务明确的非零退出码。
        logging.getLogger(__name__).exception("未预期的运行失败")
        print(f"未预期错误：{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已由用户中断。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
