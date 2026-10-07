from pathlib import Path
import shutil

from story_builder.services import video_references as refs


def _configure(monkeypatch, tmp_path: Path):
    out = tmp_path / "out_videos"
    out.mkdir()
    shutil.copy2(Path(__file__).parents[1] / "plan" / "Brother eww what’s that？💀 #meme.mp4", out / "sample.mp4")
    index = tmp_path / "index"
    monkeypatch.setattr(refs, "ROOT", tmp_path)
    monkeypatch.setattr(refs, "VIDEO_ROOT", tmp_path)
    monkeypatch.setattr(refs, "OUT_VIDEOS", out)
    monkeypatch.setattr(refs, "INDEX_ROOT", index)
    monkeypatch.setattr(refs, "MANIFEST_PATH", index / "clips.jsonl")
    monkeypatch.setattr(refs, "INDEX_META_PATH", index / "manifest.json")
    monkeypatch.setattr(refs, "STYLE_PATH", index / "seo_styles.json")
    monkeypatch.setattr(refs, "SESSION_ROOT", index / "search_sessions")


def test_curated_index_creates_playable_clip_and_thumbnail(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    result = refs.index_curated()
    assert result["count"] == 1
    row = refs._load()[0]
    assert row["clip_path"]
    assert row["thumbnail_path"]
    assert (refs.ROOT / row["clip_path"]).is_file()
    assert (refs.ROOT / row["thumbnail_path"]).is_file()


def test_search_filters_and_next_page_are_non_repeating(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    refs.index_curated()
    first = refs.search({"query": "sample", "top_n": 1, "sort_level": "clip"})
    assert first["embedding_version"] == "hash-v1"
    assert len(first["results"]) == 1
    assert refs.search({"query": "sample", "top_n": 1, "filters": {"min_duration_sec": 999}})["results"] == []
    second = refs.next_page(first["search_id"], {"top_n": 1})
    assert set(item["clip_id"] for item in first["results"]).isdisjoint(item["clip_id"] for item in second["results"])
