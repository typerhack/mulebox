"""A lost network and a server's refusal are told apart, as only one is worth trying again."""

import urllib.error

from mulebox.common import download


def test_a_refusal_is_not_a_lost_network():
    gone = urllib.error.HTTPError("https://example.com", 404, "Not Found", None, None)
    busy = urllib.error.HTTPError("https://example.com", 503, "Unavailable", None, None)
    assert not isinstance(download._failure("x", gone), download.NetworkLost)
    assert isinstance(download._failure("x", busy), download.NetworkLost)
    assert isinstance(download._failure("x", TimeoutError("timed out")), download.NetworkLost)
