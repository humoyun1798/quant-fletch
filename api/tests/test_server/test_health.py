"""Integration tests for health endpoints."""
import pytest


@pytest.mark.integration
class TestHealthEndpoint:
    def test_health_200(self, client):
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.json() == {'status': 'ok'}

    def test_health_detailed_200(self, client):
        resp = client.get('/health/detailed')
        assert resp.status_code == 200
        data = resp.json()['data']
        assert data['duckdb'] == 'ok'
        assert data['postgres'] == 'ok'


@pytest.mark.integration
class TestDocsEndpoint:
    def test_docs_available(self, client):
        resp = client.get('/docs')
        assert resp.status_code == 200

    def test_openapi_json(self, client):
        resp = client.get('/openapi.json')
        assert resp.status_code == 200
        schema = resp.json()
        assert schema['info']['title'] == 'Quant-Fletch API'
