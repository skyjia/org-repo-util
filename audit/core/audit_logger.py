"""
审计日志记录器 - 记录审计过程中的警告和错误
"""

import logging
import sys
from typing import Optional, List
from pathlib import Path
from datetime import datetime


class AuditLogger:
    """审计日志记录器

    同时输出到控制台和文件，记录 WARNING 及以上级别的日志
    """

    def __init__(self, log_file: Optional[str] = None, verbose: bool = False):
        """
        初始化审计日志记录器

        Args:
            log_file: 日志文件路径，如果为 None 则不写入文件
            verbose: 是否显示详细日志（DEBUG 级别）
        """
        self.log_file = Path(log_file) if log_file else None
        self.verbose = verbose

        # 创建自定义 logger
        self.logger = logging.getLogger('audit.execution')
        self.logger.setLevel(logging.DEBUG if verbose else logging.INFO)

        # 清除已有的 handlers
        self.logger.handlers.clear()

        # 控制台 handler（显示 WARNING 及以上）
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.WARNING)
        console_formatter = logging.Formatter(
            '%(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

        # 文件 handler（如果指定了日志文件）
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(
                str(self.log_file),
                mode='w',
                encoding='utf-8'
            )
            file_handler.setLevel(logging.WARNING)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

    def get_logger(self) -> logging.Logger:
        """获取 logger 实例"""
        return self.logger

    def close(self):
        """关闭日志记录器"""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)


# 全局审计日志记录器实例
_audit_logger: Optional[AuditLogger] = None


def init_audit_logger(log_file: Optional[str] = None, verbose: bool = False) -> AuditLogger:
    """
    初始化全局审计日志记录器

    Args:
        log_file: 日志文件路径
        verbose: 是否显示详细日志

    Returns:
        AuditLogger 实例
    """
    global _audit_logger
    _audit_logger = AuditLogger(log_file=log_file, verbose=verbose)
    return _audit_logger


def get_audit_logger() -> logging.Logger:
    """
    获取全局审计日志记录器的 logger

    Returns:
        logging.Logger 实例
    """
    global _audit_logger
    if _audit_logger is None:
        # 如果未初始化，创建一个默认的（仅控制台输出）
        _audit_logger = AuditLogger()
    return _audit_logger.get_logger()


def close_audit_logger():
    """关闭全局审计日志记录器"""
    global _audit_logger
    if _audit_logger:
        _audit_logger.close()
        _audit_logger = None
