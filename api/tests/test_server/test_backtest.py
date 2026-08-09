"""Integration tests for backtest endpoints — validation paths."""
import pytest


@pytest.mark.integration
class TestBacktestValidation:
    def test_invalid_strategy_returns_422(self, client):
        resp = client.post('/api/v1/backtest', json={
            'strategy': 'nonexistent_strategy',
            'params': {},
        })
        assert resp.status_code == 422
        detail = resp.json()['detail']
        assert detail['error']['code'] == 'strategy_not_found'

    def test_param_out_of_range_returns_422(self, client):
        """lookback=0 is below the minimum valid range."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 0, 'top_n': 1, 'rebalance': 'weekly'},
        })
        assert resp.status_code == 422
        detail = resp.json()['detail']
        assert detail['error']['code'] == 'validation_error'
        assert len(detail['error']['details']) > 0

    def test_invalid_choice_param_returns_422(self, client):
        """rebalance must be one of the defined choices."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 60, 'top_n': 3, 'rebalance': 'hourly'},
        })
        assert resp.status_code == 422
        detail = resp.json()['detail']
        assert detail['error']['code'] == 'validation_error'
        # Check that the invalid choice is flagged
        fields = {e['field'] for e in detail['error']['details']}
        assert 'rebalance' in fields

    def test_valid_request_returns_run_id(self, client):
        """A valid request should return a run_id (even if the backtest itself fails)."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'},
            'start_date': '2024-01-01',
            'end_date': '2024-03-31',
        })
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert 'run_id' in body['data']
        assert body['data']['status'] == 'queued'


@pytest.mark.integration
class TestBacktestResultQuery:
    def test_unknown_run_id_returns_404(self, client):
        resp = client.get('/api/v1/backtest/00000000-0000-0000-0000-000000000000')
        assert resp.status_code == 404
        detail = resp.json()['detail']
        assert detail['error']['code'] == 'not_found'
