"""The cmsopen command line, called in-process (the subprocess tests are in test_pipeline.py and test_datasets.py)."""

import pytest
from test_datasets import PAYLOAD, PAYLOAD_ADLER, server  # noqa: F401  (server is a pytest fixture)
from test_pipeline import write_z_file

from cmsopen.__main__ import build_parser, main


@pytest.fixture(scope="module")
def zfile(tmp_path_factory):
    return write_z_file(tmp_path_factory.mktemp("cli") / "z.root", 400, seed=6)


def test_analyze_writes_outputs_quietly(tmp_path, zfile, capsys):
    assert main(["analyze", str(zfile), "--outdir", str(tmp_path / "o"), "--no-stability", "--quiet"]) == 0
    assert (tmp_path / "o" / "summary.json").exists() and (tmp_path / "o" / "mass_fit.png").exists()
    assert capsys.readouterr().out == ""


def test_analyze_verbose_prints_summary_and_location(tmp_path, zfile, capsys):
    assert main(["analyze", str(zfile), "--outdir", str(tmp_path / "v"), "--no-stability", "--chunk-size", "100"]) == 0
    out = capsys.readouterr().out
    assert "Cutflow:" in out and "(statistical error only)" in out and f"to {tmp_path / 'v'}" in out


def test_analyze_two_files_and_options(zfile, capsys):
    args = ["analyze", str(zfile), str(zfile), "--n-events", "600", "--model", "gauss_poly", "--no-stability"]
    assert main(args) == 0
    out = capsys.readouterr().out
    assert "Files (2):" in out and "Events processed: 600" in out and "Peak position (gauss_poly)" in out


@pytest.mark.parametrize(
    "args, message",
    [
        (["missing.root"], "file not found"),
        (["{z}", "--channel", "nope"], "unknown channel"),
        (["{z}", "--n-events", "0"], "n_events"),
    ],
)
def test_analyze_errors_return_1(tmp_path, zfile, capsys, args, message):
    args = [a.replace("{z}", str(zfile)) if "{z}" in a else (str(tmp_path / a) if a.endswith(".root") else a)
            for a in args]
    assert main(["analyze", *args, "--quiet", "--no-stability"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: ") and message in err


def test_fetch_in_process(tmp_path, server, capsys):  # noqa: F811
    _, url = server
    args = ["fetch", "--dest", str(tmp_path / "d"), "--url", url]
    args += ["--size", str(len(PAYLOAD)), "--adler32", PAYLOAD_ADLER]
    assert main(args) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "d" / "sample.root")
    assert main([*args[:-1], "00000000"]) == 1  # the file there now fails the (wrong) expected checksum
    assert "fails verification" in capsys.readouterr().err


def test_usage_errors_and_help():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2
    text = build_parser().format_help()
    assert "analyze" in text and "fetch" in text
    sub = build_parser()._subparsers._group_actions[0].choices["analyze"].format_help()
    assert "Jpsi_mumu" in sub and "Z_mumu" in sub and "--workers" in sub
    assert '__name__ == "__main__"' in " ".join(sub.split())  # the macOS guard note of --workers
