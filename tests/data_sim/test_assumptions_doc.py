from data_sim import ASSUMPTIONS, SIM_AS_OF, assumptions_markdown, assumptions_sections


def _vn(x: float) -> str:
    return f"{x:.1f}".replace(".", ",").replace("-", "−")


def test_markdown_mentions_key_assumptions():
    text = assumptions_markdown()
    for needle in ("GEN_PROGRAM_V1", "20 km/h", "1,3", "30–60 phút", "KiotViet", "Sapo", "2–3 mini-mart",
                   SIM_AS_OF.isoformat(), "OpenStreetMap", "Open-Meteo", "docs/data-provenance.md"):
        assert needle in text, needle


def test_markdown_elasticities_match_constant():
    text = assumptions_markdown()
    for category, e in ASSUMPTIONS["markdown_elasticity"].items():
        assert f"| {category} | {_vn(e)} |" in text, category


def test_sections_are_structured():
    sections = assumptions_sections()
    titles = [s["title"] for s in sections]
    assert len(sections) >= 6
    assert "Lộ trình chuyển sang dữ liệu thật" in titles
    assert all(s["body_md"] for s in sections)
