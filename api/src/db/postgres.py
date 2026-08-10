# PostgreSQL 连接管理
# ponytail: 无连接池, 当并发 > 10 时引入 asyncpg 连接池
import logging
import os

import psycopg

logger = logging.getLogger(__name__)

_DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://quant:changeme@localhost:5432/quant_fletch',
)


def get_conn() -> psycopg.Connection:
    """获取 PostgreSQL 连接。调用方负责关闭。"""
    return psycopg.connect(_DATABASE_URL, connect_timeout=5)


def init_schema(conn: psycopg.Connection) -> None:
    """初始化 PostgreSQL 表结构 (幂等)。"""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS etf_info (
                code         VARCHAR PRIMARY KEY,
                name         VARCHAR NOT NULL,
                type         VARCHAR NOT NULL,
                underlying   VARCHAR,
                inception    DATE,
                expense      NUMERIC(5,4),
                data_until   DATE,
                created_at   TIMESTAMPTZ DEFAULT now(),
                updated_at   TIMESTAMPTZ DEFAULT now()
            )
        """)

        # Phase 2.5: ETF 元数据补全列 (ponytail: ALTER TABLE IF NOT EXISTS 无标准语法, 用信息模式检查)
        cur.execute("""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='etf_info' AND column_name='fund_size') THEN
                    ALTER TABLE etf_info ADD COLUMN fund_size NUMERIC(16,2);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='etf_info' AND column_name='tracking_error') THEN
                    ALTER TABLE etf_info ADD COLUMN tracking_error NUMERIC(7,4);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                               WHERE table_name='etf_info' AND column_name='premium_discount') THEN
                    ALTER TABLE etf_info ADD COLUMN premium_discount NUMERIC(7,4);
                END IF;
            END $$;
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS backtest_run (
                run_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                strategy    VARCHAR NOT NULL,
                params      JSONB NOT NULL,
                start_date  DATE NOT NULL,
                end_date    DATE NOT NULL,
                status      VARCHAR NOT NULL DEFAULT 'queued',
                metrics     JSONB,
                created_at  TIMESTAMPTZ DEFAULT now(),
                finished_at TIMESTAMPTZ
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sector_index (
                industry_code VARCHAR PRIMARY KEY,
                industry_name VARCHAR NOT NULL,
                level         SMALLINT DEFAULT 1,
                created_at    TIMESTAMPTZ DEFAULT now(),
                updated_at    TIMESTAMPTZ DEFAULT now()
            )
        """)
        conn.commit()

    logger.info('PostgreSQL schema 初始化完成')
