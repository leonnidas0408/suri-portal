import unittest

from api_client import AuthenticationError, PortalApi, PortalApiError, _items_from_payload


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="", content=b"", headers=None):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.content = content
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.response


class ApiClientTests(unittest.TestCase):
    def test_parses_existing_api_wrapper(self):
        items = [{"tit": "Aviso", "url": "docs/aviso.pdf"}]
        self.assertEqual(_items_from_payload([{"pub": items}]), items)

    def test_parses_data_wrapper(self):
        item = {"tit": "Lista", "url": "/files/lista.pdf"}
        self.assertEqual(_items_from_payload({"data": {"pub": [item]}}), [item])

    def test_empty_and_finance_marker_are_empty(self):
        self.assertEqual(_items_from_payload([]), [])
        self.assertEqual(_items_from_payload([{"des": "Financeiro"}]), [])

    def test_invalid_matricula_fails_before_network(self):
        session = FakeSession(FakeResponse())
        with self.assertRaises(PortalApiError):
            PortalApi(session).fetch_folder_items("12A", "token", "111")
        self.assertEqual(session.calls, [])

    def test_401_is_clear_auth_error(self):
        session = FakeSession(FakeResponse(status_code=401))
        with self.assertRaises(AuthenticationError):
            PortalApi(session).fetch_folder_items("12345", "token", "111")

    def test_uses_expected_api_payload_and_headers(self):
        session = FakeSession(FakeResponse(payload=[{"pub": []}]))
        self.assertEqual(PortalApi(session).fetch_folder_items("12345", "abc", "111"), [])
        args, kwargs = session.calls[0]
        self.assertTrue(args[0].endswith("/publicacoes/ConsultePublicacaoAlunoPasta"))
        self.assertEqual(kwargs["json"], {"Matricula": 12345, "PastaCodigo": 111})
        self.assertEqual(kwargs["headers"]["authorization"], "Bearer abc")

    def test_never_sends_bearer_token_to_external_download_host(self):
        session = FakeSession(FakeResponse(content=b"pdf", headers={"content-type": "application/pdf"}))
        api = PortalApi(session)
        content, content_type = api.download_item_bytes("https://files.example.org/a.pdf", "secret")
        self.assertEqual(content, b"pdf")
        self.assertEqual(content_type, "application/pdf")
        headers = session.calls[0][1]["headers"]
        self.assertNotIn("authorization", headers)


if __name__ == "__main__":
    unittest.main()
