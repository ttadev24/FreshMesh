import gzip

from data_frn.sums_io import open_text, sums_path


def test_gzipped_sums_read_like_the_csv(tmp_path):
    text = "protocol,store\nfrn-v1,C00:S0\n"
    plain = tmp_path / "frn_x.csv"
    assert sums_path(plain) is None
    with gzip.open(tmp_path / "frn_x.csv.gz", "wt", encoding="utf-8") as fh:
        fh.write(text)
    gz = sums_path(plain)
    assert gz.name == "frn_x.csv.gz"
    with open_text(gz) as fh:
        assert fh.read() == text
    plain.write_text(text, encoding="utf-8")
    assert sums_path(plain) == plain  # the uncompressed bench output wins when both exist
