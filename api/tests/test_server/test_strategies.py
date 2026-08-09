"""Integration tests for strategy endpoints."""
import pytest


@pytest.mark.integration
class TestStrategyListEndpoint:
    def test_strategies_list_200(self, client):
        resp = client.get('/api/v1/strategies')
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert isinstance(body['data'], list)
        assert len(body['data']) >= 3  # At least 3 strategies registered

    def test_strategies_have_required_fields(self, client):
        resp = client.get('/api/v1/strategies')
        assert resp.status_code == 200
        for item in resp.json()['data']:
            assert 'name' in item
            assert 'version' in item
            assert 'params' in item
            assert 'factors' in item
            assert 'min_bars' in item
            assert 'rebalance_freq' in item
            # params have required fields
            for p in item['params']:
                assert 'name' in p
                assert 'type' in p
            # factors have required fields
            for f in item['factors']:
                assert 'name' in f
                assert 'category' in f

    def test_strategies_include_momentum_rotate(self, client):
        resp = client.get('/api/v1/strategies')
        names = {item['name'] for item in resp.json()['data']}
        assert '双均线动量轮动' in names
        assert '波动率加权风险平价' in names  # RiskParity
