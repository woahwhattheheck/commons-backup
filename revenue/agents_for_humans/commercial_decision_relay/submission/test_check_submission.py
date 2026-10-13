from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

from submission import check_submission as check

FIXTURE_ROOT = Path(__file__).resolve().parents[1]


def load_manifest():
    return json.loads((FIXTURE_ROOT / "submission" / "manifest.json").read_text(encoding="utf-8"))


def complete_video(manifest, *, url="https://www.youtube.com/watch?v=example", duration=225, public=True):
    target = next(x for x in manifest["external_requirements"] if x["id"] == "public_demo_video")
    target["status"] = "COMPLETE"
    target["value"] = url
    target["duration_seconds"] = duration
    target["public_confirmed"] = public
    return target


class SubmissionCheckTests(unittest.TestCase):
    def test_real_packet_is_internal_ready_external_pending(self):
        result = check.validate(load_manifest(), FIXTURE_ROOT)
        self.assertEqual(result["state"], "INTERNAL_READY_EXTERNAL_PENDING")
        self.assertEqual(result["pending_required_external"], ["aws_builder_id", "devpost_submission", "public_demo_video"])
        self.assertFalse(result["devpost_submission_authorized"])
        self.assertFalse(result["prize_awarded"])
        self.assertFalse(result["revenue_recognized"])

    def test_all_required_external_complete_can_be_submission_ready(self):
        manifest = load_manifest()
        for item in manifest["external_requirements"]:
            if item["id"] == "aws_builder_id":
                item["status"] = "COMPLETE"; item["value"] = "builder-id-entered"
            elif item["id"] == "public_demo_video":
                complete_video(manifest)
            elif item["id"] == "devpost_submission":
                item["status"] = "COMPLETE"; item["value"] = "https://devpost.com/software/example"
        result = check.validate(manifest, FIXTURE_ROOT)
        self.assertEqual(result["state"], "SUBMISSION_READY")
        self.assertEqual(result["pending_required_external"], [])
        self.assertFalse(result["devpost_submission_authorized"])

    def assert_video_accepts(self, url):
        manifest=load_manifest(); complete_video(manifest,url=url)
        result=check.validate(manifest,FIXTURE_ROOT)
        self.assertNotIn("public_demo_video",result["pending_required_external"])

    def assert_video_rejects(self, url, message="video"):
        manifest=load_manifest(); complete_video(manifest,url=url)
        with self.assertRaisesRegex(check.SubmissionError,message):
            check.validate(manifest,FIXTURE_ROOT)

    def test_youtube_watch_video_can_be_complete(self): self.assert_video_accepts("https://www.youtube.com/watch?v=example")
    def test_youtu_be_video_can_be_complete(self): self.assert_video_accepts("https://youtu.be/abc_DEF-123?t=3")
    def test_youtube_shorts_video_can_be_complete(self): self.assert_video_accepts("https://youtube.com/shorts/abc_DEF-123")
    def test_youtube_embed_video_can_be_complete(self): self.assert_video_accepts("https://www.youtube.com/embed/abc_DEF-123")
    def test_youtube_live_video_can_be_complete(self): self.assert_video_accepts("https://m.youtube.com/live/abc_DEF-123")
    def test_vimeo_video_can_be_complete(self): self.assert_video_accepts("https://vimeo.com/123456789")
    def test_vimeo_channel_video_can_be_complete(self): self.assert_video_accepts("https://vimeo.com/channels/staffpicks/123456789")
    def test_vimeo_group_video_can_be_complete(self): self.assert_video_accepts("https://vimeo.com/groups/demo/videos/123456789")
    def test_vimeo_player_video_can_be_complete(self): self.assert_video_accepts("https://player.vimeo.com/video/123456789")

    def test_video_complete_rejects_non_video_host(self): self.assert_video_rejects("https://example.com/video/demo", "supported")
    def test_video_complete_rejects_host_suffix_spoof(self): self.assert_video_rejects("https://youtube.com.evil.example/watch?v=demo", "supported")
    def test_video_complete_rejects_arbitrary_youtube_subdomain(self): self.assert_video_rejects("https://evil.youtube.com/watch?v=demo", "supported")
    def test_video_complete_requires_specific_video_path(self): self.assert_video_rejects("https://www.youtube.com/", "concrete")
    def test_youtube_watch_requires_v(self): self.assert_video_rejects("https://www.youtube.com/watch", "exactly one")
    def test_youtube_watch_rejects_blank_v(self): self.assert_video_rejects("https://www.youtube.com/watch?v=", "video id")
    def test_youtube_watch_rejects_duplicate_v(self): self.assert_video_rejects("https://www.youtube.com/watch?v=a&v=b", "exactly one")
    def test_youtube_channel_is_not_video(self): self.assert_video_rejects("https://www.youtube.com/channel/example", "concrete")
    def test_youtube_playlist_is_not_video(self): self.assert_video_rejects("https://www.youtube.com/playlist?list=example", "concrete")
    def test_youtube_search_is_not_video(self): self.assert_video_rejects("https://www.youtube.com/results?search_query=example", "concrete")
    def test_youtu_be_rejects_extra_path(self): self.assert_video_rejects("https://youtu.be/abc/extra", "one YouTube")
    def test_video_id_rejects_encoded_separator(self): self.assert_video_rejects("https://youtu.be/abc%2Fextra", "unescaped")
    def test_vimeo_channel_page_is_not_video(self): self.assert_video_rejects("https://vimeo.com/channels/staffpicks", "concrete")
    def test_vimeo_profile_is_not_video(self): self.assert_video_rejects("https://vimeo.com/example", "valid video id")
    def test_vimeo_player_root_is_not_video(self): self.assert_video_rejects("https://player.vimeo.com/video/", "one Vimeo")
    def test_video_rejects_userinfo(self): self.assert_video_rejects("https://user@youtube.com/watch?v=example", "userinfo")
    def test_video_rejects_non_default_port(self): self.assert_video_rejects("https://youtube.com:444/watch?v=example", "port")

    def test_video_complete_requires_duration(self):
        manifest=load_manifest(); target=complete_video(manifest); del target["duration_seconds"]
        with self.assertRaisesRegex(check.SubmissionError,"duration_seconds"): check.validate(manifest,FIXTURE_ROOT)
    def test_video_complete_rejects_duration_over_five_minutes(self):
        manifest=load_manifest(); complete_video(manifest,duration=301)
        with self.assertRaisesRegex(check.SubmissionError,"1 through 300"): check.validate(manifest,FIXTURE_ROOT)
    def test_video_complete_rejects_zero_duration(self):
        manifest=load_manifest(); complete_video(manifest,duration=0)
        with self.assertRaisesRegex(check.SubmissionError,"1 through 300"): check.validate(manifest,FIXTURE_ROOT)
    def test_video_complete_rejects_bool_duration(self):
        manifest=load_manifest(); complete_video(manifest,duration=True)
        with self.assertRaisesRegex(check.SubmissionError,"duration_seconds"): check.validate(manifest,FIXTURE_ROOT)
    def test_video_complete_requires_public_confirmation(self):
        manifest=load_manifest(); complete_video(manifest,public=False)
        with self.assertRaisesRegex(check.SubmissionError,"public_confirmed"): check.validate(manifest,FIXTURE_ROOT)
    def test_pending_video_must_not_carry_proof(self):
        manifest=load_manifest(); target=next(x for x in manifest["external_requirements"] if x["id"]=="public_demo_video")
        target["duration_seconds"]=225; target["public_confirmed"]=True
        with self.assertRaisesRegex(check.SubmissionError,"must not carry video proof"): check.validate(manifest,FIXTURE_ROOT)

    def test_complete_requires_value(self):
        manifest=load_manifest(); target=next(x for x in manifest["external_requirements"] if x["id"]=="aws_builder_id")
        target["status"]="COMPLETE"; target["value"]=None
        with self.assertRaisesRegex(check.SubmissionError,"COMPLETE requires"): check.validate(manifest,FIXTURE_ROOT)
    def test_pending_must_not_smuggle_value(self):
        manifest=load_manifest(); target=next(x for x in manifest["external_requirements"] if x["id"]=="aws_builder_id")
        target["value"]="secret-ish-surprise"
        with self.assertRaisesRegex(check.SubmissionError,"non-COMPLETE"): check.validate(manifest,FIXTURE_ROOT)
    def test_repo_url_must_be_repository_root(self):
        manifest=load_manifest(); manifest["public_code_repo_url"] += "/tree/main/revenue"
        with self.assertRaisesRegex(check.SubmissionError,"repository-root URL"): check.validate(manifest,FIXTURE_ROOT)
    def test_project_source_must_be_under_repo(self):
        manifest=load_manifest(); manifest["project_source_url"]="https://github.com/other/repo/tree/main"
        with self.assertRaisesRegex(check.SubmissionError,"must be under"): check.validate(manifest,FIXTURE_ROOT)
    def test_unknown_external_requirement_rejected(self):
        manifest=load_manifest(); manifest["external_requirements"].append({"id":"invented","required":False,"status":"OPTIONAL_PENDING","value":None})
        with self.assertRaisesRegex(check.SubmissionError,"ids mismatch"): check.validate(manifest,FIXTURE_ROOT)
    def test_duplicate_external_requirement_rejected(self):
        manifest=load_manifest(); manifest["external_requirements"].append(copy.deepcopy(manifest["external_requirements"][0]))
        with self.assertRaisesRegex(check.SubmissionError,"duplicate external requirement"): check.validate(manifest,FIXTURE_ROOT)
    def test_missing_required_artifact_rejected(self):
        manifest=load_manifest(); manifest["required_artifacts"].append("does-not-exist.txt")
        with self.assertRaisesRegex(check.SubmissionError,"required artifact missing"): check.validate(manifest,FIXTURE_ROOT)
    def test_path_escape_rejected(self):
        manifest=load_manifest(); manifest["required_artifacts"].append("../README.md")
        with self.assertRaisesRegex(check.SubmissionError,"under project root"): check.validate(manifest,FIXTURE_ROOT)
    def test_authority_escalation_rejected(self):
        manifest=load_manifest(); manifest["authority"]["devpost_submission_authorized"]=True
        with self.assertRaisesRegex(check.SubmissionError,"authority block"): check.validate(manifest,FIXTURE_ROOT)
    def test_bool_is_not_accepted_as_required_string(self):
        manifest=load_manifest(); manifest["project_name"]=True
        with self.assertRaisesRegex(check.SubmissionError,"non-empty string"): check.validate(manifest,FIXTURE_ROOT)
    def test_deadline_must_have_timezone(self):
        manifest=load_manifest(); manifest["competition"]["deadline"]="2026-09-14T17:00:00"
        with self.assertRaisesRegex(check.SubmissionError,"include timezone"): check.validate(manifest,FIXTURE_ROOT)

if __name__ == "__main__": unittest.main()
