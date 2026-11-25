"""A run's peaks (common/usage.py): highest of each, its stage, unknown left out."""

from mulebox.common.usage import Peaks, average_cores, clean


def test_peaks_keep_the_highest_of_each_with_its_stage():
    peaks = Peaks()
    assert peaks.as_dict() is None  # nothing measured yet
    peaks.add(None, 1_000, "prepare")  # a first reading has memory, no cores yet
    peaks.add(2.5, 3_000, "install", cpu_s=25.0)
    peaks.add(6.0, 2_000, "command", cpu_s=60.0)
    peaks.add(None, None, "command")  # unknown: not a reading
    assert peaks.as_dict() == {"peak_cores": 6.0, "peak_cores_stage": "command",
                               "peak_memory": 3_000, "peak_memory_stage": "install",
                               "cpu_s": 85.0, "samples": 3}


def test_a_short_run_has_memory_and_no_cores():
    peaks = Peaks()
    peaks.add(None, 5_000, "command")
    assert peaks.as_dict()["peak_cores"] is None and peaks.as_dict()["peak_memory"] == 5_000


def test_clean_keeps_only_known_keys_of_the_right_type():
    got = clean({"peak_cores": 3, "peak_memory": 10, "samples": 2, "cpu_s": 1.5,
                 "peak_cores_stage": "x" * 200, "peak_memory_stage": 7, "other": "no",
                 })
    assert got == {"peak_cores": 3.0, "peak_memory": 10, "samples": 2, "cpu_s": 1.5,
                   "peak_cores_stage": "x" * 80}
    assert clean({"peak_cores": True, "samples": 1}) == {"samples": 1}
    assert clean({"peak_cores": -1, "samples": 0}) is None  # no reading: not a measurement
    assert clean("text") is None and clean(None) is None


def test_average_cores_is_cpu_over_run_time():
    assert average_cores({"cpu_s": 120.0}, 60.0) == 2.0
    assert average_cores({}, 60.0) is None and average_cores({"cpu_s": 1.0}, None) is None
