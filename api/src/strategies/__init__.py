# 策略发现机制
# 来源: 文档 04-策略系统.md 第 291-354 行
# ponytail: 确定性顺序发现, 单个策略失败不阻塞其余
import importlib
import inspect
import logging
import pkgutil
from pathlib import Path

from .base import BaseStrategy

logger = logging.getLogger(__name__)


def discover_strategies() -> dict[str, type[BaseStrategy]]:
    """发现所有策略。失败不阻塞启动。

    防护层:
        1. 跳过 _ 开头和 base 模块
        2. 单个策略 import 失败不影响其他
        3. 抽象类跳过 (inspect.isabstract)
        4. 缺少 meta ClassVar 跳过
        5. 0 策略时 ERROR 日志告警

    确定顺序:
        sorted() 保证模块导入顺序在不同 OS 上一致
    """
    registry: dict[str, type[BaseStrategy]] = {}
    pkg_dir = Path(__file__).parent

    module_names = sorted(
        name for _, name, _ in pkgutil.iter_modules([str(pkg_dir)])
        if not name.startswith('_') and name != 'base'
    )

    for name in module_names:
        try:
            module = importlib.import_module(f'.{name}', __package__)

            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if not isinstance(attr, type):
                    continue
                if not issubclass(attr, BaseStrategy):
                    continue
                if attr is BaseStrategy:
                    continue
                if inspect.isabstract(attr):
                    logger.warning(
                        f'策略类 {attr.__name__} (模块 {name}) '
                        f'未实现全部抽象方法，跳过注册',
                    )
                    continue
                if not hasattr(attr, 'meta') or attr.meta is None:
                    logger.warning(
                        f'策略类 {attr.__name__} (模块 {name}) '
                        f'缺少 meta ClassVar，跳过注册',
                    )
                    continue

                registry[attr.meta.name] = attr
                logger.info(f'已注册策略: {attr.meta.name} v{attr.meta.version}')

        except ImportError as e:
            logger.warning(f'策略模块 {name} 导入失败 (依赖缺失?): {e}')
        except Exception as e:
            logger.exception(f'策略模块 {name} 加载异常: {e}')

    if not registry:
        logger.error('没有发现任何可用策略！')
    else:
        logger.info(f'策略发现完成，共 {len(registry)} 个: {list(registry.keys())}')

    return registry
