"""Integration tests for system status endpoint."""
from unittest import mock

import pytest


@pytest.mark.integration
class TestSystemStatus:
    def test_status_200(self, client):
        resp = client.get('/api/v1/system/status')
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert 'status' in body['data']

    def test_status_has_etf_counts(self, client):
        resp = client.get('/api/v1/system/status')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert 'etfs_available' in data
        assert 'etfs_total' in data
        assert isinstance(data['etfs_total'], int)
        assert data['etfs_total'] >= 0


@pytest.mark.unit
class TestSystemStatusMutations:
    """Test status response under different seed_state values."""

    def test_running_status(self, client):
        """When seed_state is 'running', endpoint returns seeding status."""
        import importlib
        from data import seed as seed_mod
        importlib.reload(seed_mod)

        seed_mod._seed_state.update({
            'status': 'running',
            'progress': {'current': 5, 'total': 30, 'step': 'fetching'},
            'success': 5,
            'total_count': 30,
        })
        try:
            resp = client.get('/api/v1/system/status')
            assert resp.status_code == 200
            data = resp.json()['data']
            assert data['status'] == 'seeding'
            assert 'progress' in data
        finally:
            seed_mod._seed_state['status'] = 'ready'

    def test_error_status(self, client):
        """When seed_state is 'error', endpoint returns error status."""
        import importlib
        from data import seed as seed_mod
        importlib.reload(seed_mod)

        seed_mod._seed_state.update({
            'status': 'error',
            'success': 3,
            'total_count': 30,
            'message': 'Seed failed: network error',
        })
        try:
            resp = client.get('/api/v1/system/status')
            assert resp.status_code == 200
            data = resp.json()['data']
            assert data['status'] == 'error'
            assert 'message' in data
        finally:
            seed_mod._seed_state['status'] = 'ready'

    def test_ready_status_has_data_since_until(self, client):
        """When seed_state is 'ready', endpoint returns date range."""
        import importlib
        from data import seed as seed_mod
        importlib.reload(seed_mod)

        seed_mod._seed_state.update({
            'status': 'ready',
            'success': 30,
            'total_count': 30,
            'data_since': '2020-01-02',
            'data_until': '2026-08-07',
        })
        try:
            resp = client.get('/api/v1/system/status')
            assert resp.status_code == 200
            data = resp.json()['data']
            assert data['status'] == 'ready'
            assert data['data_since'] == '2020-01-02'
            assert data['data_until'] == '2026-08-07'
        finally:
            seed_mod._seed_state['status'] = 'ready'


@pytest.mark.integration
class TestSeedEndpoint:
    """Test POST /api/v1/system/seed endpoint."""

    def test_trigger_seed_returns_task_started(self, client):
        """Trigger seed returns ws_url and starts background task."""
        resp = client.post('/api/v1/system/seed', json={'mode': 'full'})
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['message'] == '种子任务已启动'
        assert 'ws_url' in data
        assert '/api/v1/system/seed/ws' in data['ws_url']


@pytest.mark.unit
class TestSystemNotSeeded:
    """Test status when no data exists (not_seeded path)."""

    def test_not_seeded_when_no_data(self, client):
        """When seed state is empty and DuckDB has no data, returns not_seeded."""
        import importlib
        from data import seed as seed_mod
        from unittest import mock as _mock

        importlib.reload(seed_mod)

        # Empty seed state (not 'ready', 'running', or 'error')
        seed_mod._seed_state.clear()
        try:
            with _mock.patch('db.duckdb.get_conn') as mock_conn:
                # Mock: DuckDB has 0 distinct ETF codes
                mock_ddb = _mock.MagicMock()
                mock_ddb.execute.return_value.fetchone.return_value = [0]
                mock_conn.return_value = mock_ddb

                resp = client.get('/api/v1/system/status')
                assert resp.status_code == 200
                data = resp.json()['data']
                assert data['status'] == 'not_seeded'
                assert data['etfs_available'] == 0
        finally:
            seed_mod._seed_state['status'] = 'ready'
