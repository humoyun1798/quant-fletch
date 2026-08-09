"""Unit tests for data/sources/shenwan.py — sector data mapping accuracy.

Ponytail: 纯单元测试, 不调 AkShare API。映射准确性手工核对。
"""
import polars as pl
import pytest

from data.sources.shenwan import ETF_TO_SW_INDUSTRY, ShenwanSource, SourceStatus


# ── ETF → Industry Mapping ─────────────────────────────────────────────────


@pytest.mark.unit
class TestETFToSWMapping:
    def test_all_11_sector_etfs_mapped(self):
        """12 只行业 ETF 中 11 只入表 (510880.SH 红利ETF 排除)"""
        assert len(ETF_TO_SW_INDUSTRY) == 11
        # 红利ETF 不在映射中
        assert '510880.SH' not in ETF_TO_SW_INDUSTRY

    def test_all_mapped_etfs_are_sector_type(self):
        """验证所有映射的 ETF code 格式正确"""
        for etf_code in ETF_TO_SW_INDUSTRY:
            assert '.' in etf_code  # code format: XXXXXX.SH or XXXXXX.SZ
            assert ETF_TO_SW_INDUSTRY[etf_code]  # non-empty industry name

    def test_industry_names_are_valid(self):
        """所有映射的行业名称为有效字符串"""
        seen = set()
        for industry_name in ETF_TO_SW_INDUSTRY.values():
            assert isinstance(industry_name, str)
            assert len(industry_name) >= 2
            seen.add(industry_name)

        # 9 个不同的行业 (医药生物出现 2 次: 516020 + 512010)
        # 传媒出现 2 次: 512980 + 159869, 11 - 2 = 9
        assert len(seen) == 9

    def test_sector_etf_count_matches_etf_config(self):
        """验证行业 ETF 映射数量与 etf_config 中 sector=12 一致。
        12 只 sector ETF → 11 只入映射表, 1 只 (510880 红利) 排除。
        """
        from data.seed.etf_config import ETF_POOL
        sector_codes = [e.code for e in ETF_POOL if e.type == 'sector']
        assert len(sector_codes) == 12

        mapped = set(ETF_TO_SW_INDUSTRY.keys())
        unmapped = set(sector_codes) - mapped
        assert unmapped == {'510880.SH'}  # 仅红利ETF不在映射中


# ── build_etf_sector_map ──────────────────────────────────────────────────


@pytest.mark.unit
class TestBuildETFSectorMap:
    def test_builds_map_from_industry_list(self):
        """用模拟的行业列表构建 ETF 映射表"""
        sw = ShenwanSource()
        industry_df = pl.DataFrame({
            'industry_code': ['801790', '801120', '801150'],
            'industry_name': ['非银金融', '食品饮料', '医药生物'],
        })

        map_df = sw.build_etf_sector_map(industry_df)

        assert not map_df.is_empty()
        assert 'etf_code' in map_df.columns
        assert 'industry_code' in map_df.columns
        assert 'industry_name' in map_df.columns
        assert 'verified' in map_df.columns

        # 至少有一条映射 (512880 → 非银金融)
        securities_map = map_df.filter(pl.col('etf_code') == '512880.SH')
        assert not securities_map.is_empty()
        assert securities_map['industry_code'][0] == '801790'

    def test_empty_industry_df_returns_empty_map(self):
        """行业列表为空时返回空 DataFrame"""
        sw = ShenwanSource()
        industry_df = pl.DataFrame(schema={
            'industry_code': pl.Utf8, 'industry_name': pl.Utf8,
        })
        map_df = sw.build_etf_sector_map(industry_df)
        assert map_df.is_empty()

    def test_partial_match_skips_unmapped(self):
        """行业列表只有部分匹配时, 跳过未匹配的 ETF"""
        sw = ShenwanSource()
        # 只提供 1 个行业 (非银金融), 其他 10 个 ETF 映射不到
        industry_df = pl.DataFrame({
            'industry_code': ['801790'],
            'industry_name': ['非银金融'],
        })

        map_df = sw.build_etf_sector_map(industry_df)

        assert not map_df.is_empty()
        assert len(map_df) == 1  # 只有 512880 能映射到非银金融
        assert map_df['etf_code'][0] == '512880.SH'


# ── SourceStatus ──────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSourceStatus:
    def test_available_status(self):
        status = SourceStatus(name='shenwan', available=True)
        assert status.name == 'shenwan'
        assert status.available is True
        assert status.message == ''

    def test_unavailable_status(self):
        status = SourceStatus(name='shenwan', available=False, message='连接超时')
        assert status.available is False
        assert status.message == '连接超时'

    def test_frozen_prevents_mutation(self):
        status = SourceStatus(name='shenwan', available=True)
        with pytest.raises(Exception):
            status.available = False  # type: ignore[misc]
