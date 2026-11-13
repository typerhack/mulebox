"""A download as `mulebox status` says it, and as a card's fingerprint sees it change."""

from mulebox.client.attention import activity_text, status_lines
from mulebox.common import status

CACHE = {"what": "cache", "name": "pip cache", "step": "Run actions/setup-python@6d4fd22",
         "done_bytes": 1418315, "total_bytes": 9806923, "rate_bytes_s": 104857.6, "as_of_s": 75.0,
         "net_bytes_s": 614400.0, "net_scope": "job", "waiting_on_network": True,
         "quiet_s": 95.0, "stalled": True}


def test_status_says_what_is_downloading_how_far_and_that_it_waits_on_the_network():
    lines = status_lines({"job_id": "job-1", "activity": {"elapsed_s": 300.0, "download": CACHE}})
    assert lines[0].endswith(
        "downloading pip cache: 1.4 MiB of 9.4 MiB (14%) at 102.4 KiB/s, as printed 1m 15s ago, "
        "network 600.0 KiB/s (its own), waiting on the network, stalled: no byte for 1m 35s")


def test_a_download_with_only_a_name_and_a_size_says_so():
    text = activity_text({"download": {"what": "package", "name": "torch.whl",
                                       "total_bytes": 906_400_000, "net_bytes_s": 2048.0,
                                       "net_scope": "machine"}})
    assert text == "downloading torch.whl (864.4 MiB), network 2.0 KiB/s (the machine's)"
    assert activity_text({"download": {"what": "network", "waiting_on_network": True}}) == (
        "downloading, by its own traffic, waiting on the network")


def test_a_cards_fingerprint_follows_the_download_in_steps():
    def card(**download):
        return [{"job_id": "job-1", "state": "running", "doing": {"download": {**CACHE, **download}}}]

    same = status.fingerprint(card(done_bytes=1418315))
    assert status.fingerprint(card(done_bytes=1418315 + 1000)) == same  # under 5 % more
    assert status.fingerprint(card(done_bytes=5612619)) != same
    assert status.fingerprint(card(done_bytes=1418315, stalled=False)) != same
    assert status.fingerprint(card(done_bytes=1418315, rate_bytes_s=1.0)) == same
    assert status.download_mark({"what": "image", "done_bytes": 9 * 1024 * 1024}) == (
        "image", None, 2, None, None)
    assert status.download_mark(None) is None
