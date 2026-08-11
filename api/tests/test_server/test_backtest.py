"""Integration tests for backtest endpoints — validation + result query."""
import time
from unittest import mock

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
        fields = {e['field'] for e in detail['error']['details']}
        assert 'rebalance' in fields

    def test_valid_request_returns_run_id(self, client):
        """A valid request should return a run_id."""
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

    def test_float_param_out_of_range(self, client):
        """int param above max should fail validation."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 2000, 'top_n': 3, 'rebalance': 'weekly'},
        })
        assert resp.status_code == 422

    def test_missing_strategy_name(self, client):
        """Empty strategy name should return 422."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '',
            'params': {},
        })
        assert resp.status_code == 422


@pytest.mark.integration
class TestBacktestResultQuery:
    def test_unknown_run_id_returns_404(self, client):
        resp = client.get('/api/v1/backtest/00000000-0000-0000-0000-000000000000')
        assert resp.status_code == 404
        detail = resp.json()['detail']
        assert detail['error']['code'] == 'not_found'

    def test_queued_result_returns_running_status(self, client):
        """Query a just-created run before it completes."""
        start = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 20, 'top_n': 3, 'rebalance': 'weekly'},
            'start_date': '2024-01-01',
            'end_date': '2024-03-31',
        })
        run_id = start.json()['data']['run_id']

        # Immediately query — should be queued or running
        resp = client.get(f'/api/v1/backtest/{run_id}')
        assert resp.status_code == 200
        body = resp.json()
        assert body['data']['status'] in ('running', 'queued')


@pytest.mark.integration
class TestBacktestFullRun:
    def test_backtest_runs_to_completion(self, client):
        """Run a short backtest and poll until completed."""
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 10, 'top_n': 2, 'rebalance': 'daily'},
            'start_date': '2025-06-01',
            'end_date': '2025-06-30',
        })
        assert resp.status_code == 200
        run_id = resp.json()['data']['run_id']

        # Poll for completion (max 30 seconds)
        for _ in range(60):
            r = client.get(f'/api/v1/backtest/{run_id}')
            status = r.json()['data']['status']
            if status in ('completed', 'failed'):
                break
            time.sleep(0.5)

        final = client.get(f'/api/v1/backtest/{run_id}')
        assert final.status_code == 200
        data = final.json()['data']
        assert data['status'] == 'completed', f'Expected completed, got {data}'
        assert 'metrics' in data
        assert 'equity_curve' in data
        assert len(data['equity_curve']) > 0
        # Verify key metrics exist
        for key in ('sharpe_ratio', 'max_drawdown', 'annual_return', 'total_return'):
            assert key in data['metrics'], f'Missing metric: {key}'

    def test_pg_fallback_after_memory_clear(self, client):
        """PG fallback: clear memory store, query from PostgreSQL."""
        from server.routes.backtest import _run_store

        # Run a backtest
        resp = client.post('/api/v1/backtest', json={
            'strategy': '双均线动量轮动',
            'params': {'lookback': 10, 'top_n': 2, 'rebalance': 'daily'},
            'start_date': '2025-06-01',
            'end_date': '2025-06-30',
        })
        run_id = resp.json()['data']['run_id']

        # Wait for completion
        for _ in range(60):
            r = client.get(f'/api/v1/backtest/{run_id}')
            if r.json()['data']['status'] in ('completed', 'failed'):
                break
            time.sleep(0.5)

        # Clear in-memory store to force PG fallback
        _run_store.pop(run_id, None)

        # Query should now hit PG
        final = client.get(f'/api/v1/backtest/{run_id}')
        data = final.json()['data']
        assert 'metrics' in data or 'status' in data


@pytest.mark.unit
class TestBacktestStatusFormatting:
    """Test response formatting for different _run_store statuses."""

    def test_failed_status_from_memory(self, client):
        """Query a failed backtest from memory store."""
        import uuid as _uuid
        import datetime as _dt
        from server.routes.backtest import _run_store

        rid = str(_uuid.uuid4())
        _run_store[rid] = {
            'status': 'failed',
            'strategy': '双均线动量轮动',
            'params': {'lookback': 10},
            'error': {'code': 'backtest_error', 'message': '除数不能为零'},
            'created_at': _dt.datetime.now(_dt.UTC).isoformat(),
            'finished_at': _dt.datetime.now(_dt.UTC).isoformat(),
        }
        try:
            resp = client.get(f'/api/v1/backtest/{rid}')
            assert resp.status_code == 200
            data = resp.json()['data']
            assert data['status'] == 'failed'
            assert 'error' in data
            assert data['error']['code'] == 'backtest_error'
        finally:
            _run_store.pop(rid, None)

    def test_running_status_from_memory(self, client):
        """Query a running backtest from memory store."""
        import uuid as _uuid
        from server.routes.backtest import _run_store

        rid = str(_uuid.uuid4())
        _run_store[rid] = {'status': 'running'}
        try:
            resp = client.get(f'/api/v1/backtest/{rid}')
            assert resp.status_code == 200
            data = resp.json()['data']
            assert data['status'] == 'running'
            assert 'run_id' in data
        finally:
            _run_store.pop(rid, None)


@pytest.mark.integration
class TestBacktestCompare:
    """Test compare endpoint validation."""

    def test_compare_no_strategies_returns_422(self, client):
        resp = client.post('/api/v1/backtest/compare', json={
            'strategies': [],
            'start_date': '2024-01-01',
            'end_date': '2024-03-31',
        })
        assert resp.status_code == 422
        detail = resp.json()['detail']
        assert '至少指定一个策略' in detail['error']['message']

    def test_compare_too_many_strategies_returns_422(self, client):
        resp = client.post('/api/v1/backtest/compare', json={
            'strategies': [{'name': '双均线动量轮动', 'params': {'lookback': 10, 'top_n': 2, 'rebalance': 'daily'}}] * 11,
            'start_date': '2024-01-01',
            'end_date': '2024-03-31',
        })
        assert resp.status_code == 422
        detail = resp.json()['detail']
        assert '最多比较 10 个' in detail['error']['message']
