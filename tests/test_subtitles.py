from core import subtitles


def test_srt_numbers_cues_and_formats_times():
    srt = subtitles.to_srt([{"start": 1.5, "end": 3.25, "text": "Hello there.", "kind": "say"},
                            {"start": 61.0, "end": 63.0, "text": "Forty winters.", "kind": "think"}])
    assert srt == ("1\n00:00:01,500 --> 00:00:03,250\nHello there.\n\n"
                   "2\n00:01:01,000 --> 00:01:03,000\n<i>Forty winters.</i>\n\n")


def test_vtt_has_a_header_and_dot_milliseconds():
    vtt = subtitles.to_vtt([{"start": 0.0, "end": 1.0, "text": "Hi", "kind": "narrate"}])
    assert vtt.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.000\n<i>Hi</i>")


def test_long_lines_wrap_and_split_without_overlap():
    text = ("I can't do what I used to do, but this year, this year I should do something for the children "
            "down in the valley who never stop waiting for me to come back.")
    cues = subtitles.cues([{"start": 10.0, "end": 18.0, "text": text, "kind": "say"}])
    assert len(cues) >= 2
    assert all(len(rows) <= subtitles.ROWS and all(len(r) <= subtitles.WIDTH for r in rows) for _, _, rows, _ in cues)
    assert cues[0][0] == 10.0
    assert all(a[1] <= b[0] for a, b in zip(cues, cues[1:]))
    assert cues[-1][1] <= 18.0 + 1e-6


def test_short_cues_stay_readable_but_never_overlap_the_next():
    cues = subtitles.cues([{"start": 0.0, "end": 0.2, "text": "Oh!", "kind": "say"},
                           {"start": 0.5, "end": 2.0, "text": "What?", "kind": "say"}])
    assert cues[0][1] == 0.5 - subtitles.GAP
    cues = subtitles.cues([{"start": 0.0, "end": 0.2, "text": "Oh!", "kind": "say"}])
    assert cues[0][1] == subtitles.MIN_SECONDS


def test_lines_without_text_are_skipped():
    assert subtitles.to_srt([{"start": 0, "end": 1, "text": "  ", "kind": "say"}]) == ""
