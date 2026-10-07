from video_audio_analyzer.pipeline import AnalyzerOptions, _cut_interval_records


def test_cut_intervals_are_timestamped_virtual_children_without_summaries():
    samples = [
        (0.0, object(), 0.0),
        (1.0, object(), 0.25),
        (1.25, object(), 0.9),  # too close to the previous boundary
        (2.0, object(), 0.30),
        (4.75, object(), 0.8),  # too close to the end
    ]
    cuts = _cut_interval_records("scene_0001", 0.0, 5.0, samples, AnalyzerOptions())
    assert [(item["start_time_sec"], item["end_time_sec"]) for item in cuts] == [
        (0.0, 1.0), (1.0, 2.0), (2.0, 5.0),
    ]
    assert all(item["parent_scene_id"] == "scene_0001" for item in cuts)
    assert all(item["media_storage"] == "virtual_source_interval" for item in cuts)
    assert all(item["requires_summary"] is False for item in cuts)


def test_cut_intervals_can_be_disabled_without_affecting_scene_boundaries():
    options = AnalyzerOptions(extract_cut_clips=False)
    assert _cut_interval_records("scene_0001", 0.0, 5.0, [(0.0, object(), 0.0)], options) == []
