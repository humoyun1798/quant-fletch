"""Unit tests for reserved data sources (stub interfaces for v3.0)."""
import pytest

from data.sources.reserved import Level2Source, TickSource


class TestTickSource:
    def test_subscribe_raises_not_implemented(self):
        ts = TickSource()
        with pytest.raises(NotImplementedError, match='v3.0'):
            ts.subscribe(['510300.SH'])

    def test_unsubscribe_raises_not_implemented(self):
        ts = TickSource()
        with pytest.raises(NotImplementedError, match='v3.0'):
            ts.unsubscribe(['510300.SH'])

    def test_name_constant(self):
        assert TickSource.NAME == 'tick'


class TestLevel2Source:
    def test_subscribe_orderbook_raises_not_implemented(self):
        l2 = Level2Source()
        with pytest.raises(NotImplementedError, match='v3.0'):
            l2.subscribe_orderbook(['510300.SH'])

    def test_subscribe_trades_raises_not_implemented(self):
        l2 = Level2Source()
        with pytest.raises(NotImplementedError, match='v3.0'):
            l2.subscribe_trades(['510300.SH'])

    def test_name_constant(self):
        assert Level2Source.NAME == 'level2'
