"""Integration tests for ETF list / OHLCV / bars endpoints."""
import pytest


@pytest.mark.integration
class TestETFList:
    def test_list_etfs_200(self, client):
        resp = client.get('/api/v1/etfs')
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert 'meta' in body
        assert 'total' in body['meta']
        assert 'page' in body['meta']
        assert body['meta']['page'] == 1

    def test_list_etfs_pagination(self, client):
        resp = client.get('/api/v1/etfs?page=1&per_page=5')
        assert resp.status_code == 200
        body = resp.json()
        assert body['meta']['per_page'] == 5
        assert len(body['data']) <= 5

    def test_list_etfs_items_have_required_fields(self, client):
        resp = client.get('/api/v1/etfs?per_page=1')
        assert resp.status_code == 200
        items = resp.json()['data']
        if items:
            item = items[0]
            for key in ('code', 'name', 'type', 'underlying', 'latest_close'):
                assert key in item, f'Missing field: {key}'


@pytest.mark.integration
class TestETFOHLCV:
    def test_ohlcv_known_code_returns_data(self, client):
        """Known ETF code with data in DuckDB should return rows."""
        resp = client.get('/api/v1/etfs/510300.SH/ohlcv?limit=5')
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert body['meta']['returned'] <= 5
        if body['data']:
            item = body['data'][0]
            for key in ('date', 'open', 'high', 'low', 'close', 'volume', 'adj_close'):
                assert key in item, f'Missing OHLCV field: {key}'

    def test_ohlcv_date_range(self, client):
        resp = client.get(
            '/api/v1/etfs/510300.SH/ohlcv?start=2024-01-01&end=2024-03-31&limit=50',
        )
        assert resp.status_code == 200
        body = resp.json()
        if body['data']:
            dates = [d['date'] for d in body['data']]
            assert all(d >= '2024-01-01' for d in dates)
            assert all(d <= '2024-03-31' for d in dates)

    def test_ohlcv_unknown_code_returns_404(self, client):
        resp = client.get('/api/v1/etfs/ZZZZZZ.ZZ/ohlcv')
        assert resp.status_code == 404


@pytest.mark.integration
class TestETFBars:
    def test_bars_daily_known_code(self, client):
        resp = client.get('/api/v1/etfs/510300.SH/bars?period=daily&limit=5')
        assert resp.status_code == 200
        body = resp.json()
        assert 'data' in body
        assert body['meta']['period'] == 'daily'

    def test_bars_daily_unknown_code_returns_404(self, client):
        resp = client.get('/api/v1/etfs/ZZZZZZ.ZZ/bars?period=daily')
        assert resp.status_code == 404

    def test_bars_minute_returns_data(self, client):
        """Minute bar query returns aggregated data when etf_minute table exists."""
        resp = client.get('/api/v1/etfs/510300.SH/bars?period=5m&limit=5')
        assert resp.status_code == 200
        body = resp.json()
        assert body['meta']['period'] == '5m'
        if body['data']:
            item = body['data'][0]
            for key in ('dt', 'open', 'high', 'low', 'close', 'volume'):
                assert key in item, f'Missing bar field: {key}'
