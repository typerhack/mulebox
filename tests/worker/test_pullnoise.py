"""What is left of an image pull in a job's log. Samples are as Compose printed them."""

from mulebox.common.protocol import MessageType
from mulebox.worker.link import request
from mulebox.worker.logtail import LogTailer
from mulebox.worker.pullnoise import EVERY_BYTES, PullNoise
from mulebox.worker.steps import StepTracker

# docker compose 5.6, no terminal, two real images
COMPOSE_5 = """\
 Image busybox:1.36.1-musl Pulling
 Image memcached:1.6.32-alpine Pulling
 a12bd3844df3 Pulling fs layer 0B
 9986a736f7d3 Pulling fs layer 0B
 58c798e0a9cb Download complete 0B
 a12bd3844df3 Pull complete 0B
 Image busybox:1.36.1-musl Pulled
 9986a736f7d3 Downloading 1.049MB
 9986a736f7d3 Downloading 1.049MB
 9986a736f7d3 Downloading 4.088MB
 9986a736f7d3 Download complete 0B
 9986a736f7d3 Extracting 1B
 9986a736f7d3 Pull complete 0B
 88054760825e Downloading 122B
 Image memcached:1.6.32-alpine Pulled
 Network mulebox-probe-a_default Created
 Container mulebox-probe-a-a-1 Started
"""
KEPT = """\
 Image busybox:1.36.1-musl Pulling
 Image memcached:1.6.32-alpine Pulling
 Image busybox:1.36.1-musl Pulled
mulebox: at least 4 MB of image layers downloaded
 Image memcached:1.6.32-alpine Pulled
 Network mulebox-probe-a_default Created
 Container mulebox-probe-a-a-1 Started
"""


def through(noise, text):
    return "".join(piece for line in text.splitlines(keepends=True) for piece in noise.line(line))


def test_compose_5_keeps_outcome_lines_and_the_amount():
    noise = PullNoise()
    assert through(noise, COMPOSE_5) == KEPT
    assert noise.total == 4_088_122


def test_compose_2_gives_totals():
    noise = PullNoise()
    text = (" 6e909acdb790 Downloading [=>      ]  1.5MB/3.4MB\n"
            " 6e909acdb790 Verifying Checksum \n"
            " 6e909acdb790 Download complete \n")
    assert through(noise, text) == ""
    assert noise.total == 3_400_000


def test_buildkit_layers():
    noise = PullNoise()
    layer = "ab" * 32
    text = (f"#5 sha256:{layer} 1.05MB / 3.40MB 0.2s\n"
            f"#5 sha256:{layer} 3.40MB / 3.40MB 0.4s done\n"
            f"#5 extracting sha256:{layer} 0.1s\n"
            f"#5 extracting sha256:{layer} 0.2s done\n")
    assert through(noise, text).endswith(f"\n#5 extracting sha256:{layer} 0.2s done\n")
    assert noise.total == 3_400_000


def test_kibibytes_and_gigabytes():
    noise = PullNoise()
    through(noise, "0123456789ab Downloading 2KiB\nabcdef012345 Downloading 1.5GB\n")
    assert noise.total == 2048 + 1_500_000_000


def test_a_layer_counts_once_across_images():
    noise = PullNoise()
    through(noise, " a12bd3844df3 Downloading 3MB\n a12bd3844df3 Downloading 3MB\n")
    assert noise.total == 3_000_000


def test_a_long_pull_says_how_far_it_has_come():
    noise = PullNoise()
    lines = "".join(f" 0123456789ab Downloading {mb}MB\n" for mb in range(1, 250))
    said = through(noise, lines).splitlines()
    assert said == ["mulebox: at least 100 MB of image layers downloaded",
                    "mulebox: at least 200 MB of image layers downloaded"]
    assert EVERY_BYTES == 100_000_000


def test_what_goes_wrong_stays():
    noise = PullNoise()
    text = (" Image example-app/api:1 Error failed to resolve reference\n"
            "error pulling image configuration: download failed after attempts=6\n"
            " 0123456789ab Retrying in 5 seconds\n")
    assert through(noise, text) == text


def test_ordinary_output_is_not_touched():
    noise = PullNoise()
    text = ("Downloading 905 packages\n"
            "Progress: resolved 905, reused 0, downloaded 12, added 12\n"
            "abc123 Pull complete\n"
            "#5 DONE 0.3s\n")
    assert through(noise, text) == text


def test_the_summary_comes_at_the_end_if_nothing_follows():
    noise = PullNoise()
    through(noise, " 0123456789ab Downloading 3MB\n")
    assert noise.flush() == ["mulebox: at least 3 MB of image layers downloaded\n"]
    assert noise.flush() == []


def test_new_bytes_are_given_once():
    noise = PullNoise()
    through(noise, " 0123456789ab Downloading 3MB\n")
    assert noise.take_new_bytes() == 3_000_000 and noise.take_new_bytes() == 0


# Through the tailer


def run(tmp_path, text, tracker):
    (tmp_path / "out.log").write_text(text)
    tail = LogTailer(tmp_path / "out.log", "job-1", "att-1", request, steps=tracker)
    tail.read_new()
    tail.finish()
    sent = []

    def record(msg):
        sent.append(msg)
        return msg

    tail._send_log(record)
    return "".join(m.body["data"] for m in sent if m.type is MessageType.LOG_CHUNK)


def test_the_stored_log_is_collapsed_and_the_stage_has_the_bytes(tmp_path):
    tracker = StepTracker()
    tracker.begin("images", 1.0)
    logged = run(tmp_path, COMPOSE_5, tracker)
    assert logged == KEPT
    assert tracker.pending()[0]["bytes_downloaded"] == 4_088_122


def test_redaction_still_runs_first(tmp_path):
    text = (" 0123456789ab Downloading 3MB\n"
            "pull from https://alice:hunter2hunter2@registry.example.test failed\n")
    logged = run(tmp_path, text, StepTracker())
    assert "hunter2" not in logged and "alice:[redacted]@" in logged


def test_a_stage_mark_after_a_run_of_layers_still_works(tmp_path):
    tracker = StepTracker()
    tracker.begin("images", 1.0)
    text = f" 0123456789ab Downloading 3MB\n::mulebox-step:{tracker.marker}:5:services\n"
    logged = run(tmp_path, text, tracker)
    assert logged == "mulebox: at least 3 MB of image layers downloaded\n"
    rows = tracker.pending()
    assert [row["stage"] for row in rows] == ["images", "services"]
    assert rows[0]["bytes_downloaded"] == 3_000_000 and rows[1]["bytes_downloaded"] is None


def test_layer_lines_are_never_a_failing_line(tmp_path):
    tracker = StepTracker()
    tracker.begin("images", 1.0)
    run(tmp_path, "real problem\n 0123456789ab Waiting \n", tracker)
    tracker.close(1, 2.0, failed=True)
    assert tracker.pending()[0]["failing_line"] == "real problem"


def test_a_package_download_leaves_only_its_last_line():
    noise = PullNoise()
    kept = [noise.line("Downloading next@16.4.3: 48.31 kB/43.60 MB\n"),
            noise.line("Downloading next@16.4.3: 43.60 MB/43.60 MB, done\n"),
            noise.line("Downloading the pnpm 12.16.1 binary for linux-x64...\n")]
    assert kept == [[], ["Downloading next@16.4.3: 43.60 MB/43.60 MB, done\n"],
                    ["Downloading the pnpm 12.16.1 binary for linux-x64...\n"]]
    assert noise.total == 0


def test_downloading_ends_when_every_layer_has_its_data():
    noise = PullNoise()
    assert noise.downloading is False
    for line in ("9986a736f7d3 Pulling fs layer 0B", "aaaaaaaaaaaa Pulling fs layer 0B",
                 "9986a736f7d3 Downloading 2.097MB", "9986a736f7d3 Download complete 0B"):
        noise.line(line + "\n")
    assert noise.downloading is True  # aaaaaaaaaaaa still to come
    noise.line("aaaaaaaaaaaa Already exists 0B\n")
    assert noise.downloading is False
    noise.line("9986a736f7d3 Extracting 1.2MB\n")
    assert noise.downloading is False
    built = PullNoise()
    built.line("#5 sha256:" + "ab" * 32 + " 12.3MB / 45.6MB 1.2s\n")
    assert built.downloading is True
    built.line("#5 sha256:" + "ab" * 32 + " 45.6MB / 45.6MB 3.0s done\n")
    assert built.downloading is False
