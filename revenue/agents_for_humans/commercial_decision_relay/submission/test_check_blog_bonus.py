import json
import tempfile
import unittest
from pathlib import Path

import check_blog_bonus as check

HERE = Path(__file__).resolve().parent
FIXTURE_ROOT = HERE.parent


def load_manifest():
    return json.loads((HERE / "blog_bonus_manifest.json").read_text(encoding="utf-8"))


def published(manifest, index, url):
    row = manifest["posts"][index]
    row["status"] = "PUBLIC_URL_RECORDED"
    row["public_url"] = url


class BlogBonusTests(unittest.TestCase):
    def test_real_manifest_is_publication_pending(self):
        result = check.validate(load_manifest(), FIXTURE_ROOT)
        self.assertEqual("PUBLICATION_PENDING", result["state"])
        self.assertEqual(0, result["public_urls_recorded"])
        self.assertEqual(3, result["remaining_publications"])
        self.assertFalse(result["bonus_points_awarded"])

    def test_three_distinct_builder_urls_record_urls_without_awarding_points(self):
        manifest = load_manifest()
        for i in range(3):
            published(manifest, i, f"https://builder.aws.com/content/post-{i}/slug-{i}")
        result = check.validate(manifest, FIXTURE_ROOT)
        self.assertEqual("PUBLICATION_URLS_RECORDED", result["state"])
        self.assertEqual(3, result["public_urls_recorded"])
        self.assertEqual(0.6, result["recorded_url_nominal_bonus_if_eligible"])
        self.assertFalse(result["network_publication_verified"])
        self.assertFalse(result["bonus_points_awarded"])

    def test_wrong_host_is_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://example.com/content/post/slug")
        with self.assertRaisesRegex(check.BonusManifestError, "builder.aws.com"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_builder_subdomain_is_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://fake.builder.aws.com/content/post/slug")
        with self.assertRaisesRegex(check.BonusManifestError, "builder.aws.com"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_host_suffix_spoof_is_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com.evil.example/content/post/slug")
        with self.assertRaisesRegex(check.BonusManifestError, "builder.aws.com"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_builder_root_is_not_a_post(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com/")
        with self.assertRaisesRegex(check.BonusManifestError, "specific public"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_builder_non_content_path_is_not_a_post(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com/connect/space/example")
        with self.assertRaisesRegex(check.BonusManifestError, "specific public"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_duplicate_public_urls_are_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com/content/same/slug")
        published(manifest, 1, "https://builder.aws.com/content/same/slug")
        with self.assertRaisesRegex(check.BonusManifestError, "must be distinct"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_same_post_aliases_are_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com/content/same/original-slug?trk=one")
        published(manifest, 1, "https://builder.aws.com/content/same/different-slug/#fragment")
        with self.assertRaisesRegex(check.BonusManifestError, "must be distinct"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_nonstandard_https_port_is_rejected(self):
        manifest = load_manifest()
        published(manifest, 0, "https://builder.aws.com:444/content/post/slug")
        with self.assertRaisesRegex(check.BonusManifestError, "standard HTTPS port"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_draft_status_cannot_carry_public_url(self):
        manifest = load_manifest()
        manifest["posts"][0]["public_url"] = "https://builder.aws.com/content/fake/slug"
        with self.assertRaisesRegex(check.BonusManifestError, "must not carry"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_authority_escalation_is_rejected(self):
        manifest = load_manifest()
        manifest["authority"]["bonus_points_awarded"] = True
        with self.assertRaisesRegex(check.BonusManifestError, "all-false"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_deadline_drift_is_rejected(self):
        manifest = load_manifest()
        manifest["deadline"] = "2026-09-15T17:00:00-07:00"
        with self.assertRaisesRegex(check.BonusManifestError, "deadline drift"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_duplicate_post_ids_are_rejected(self):
        manifest = load_manifest()
        manifest["posts"][1]["id"] = manifest["posts"][0]["id"]
        with self.assertRaisesRegex(check.BonusManifestError, "unique"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_missing_draft_is_rejected(self):
        manifest = load_manifest()
        manifest["posts"][0]["draft_path"] = "docs/blog-bonus/missing.md"
        with self.assertRaisesRegex(check.BonusManifestError, "does not exist"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_path_escape_is_rejected(self):
        manifest = load_manifest()
        manifest["posts"][0]["draft_path"] = "../README.md"
        with self.assertRaisesRegex(check.BonusManifestError, "inside the project root"):
            check.validate(manifest, FIXTURE_ROOT)

    def test_tiny_draft_is_rejected(self):
        manifest = load_manifest()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "docs/blog-bonus").mkdir(parents=True)
            for row in manifest["posts"]:
                target = root / row["draft_path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("too short", encoding="utf-8")
            with self.assertRaisesRegex(check.BonusManifestError, "substantive"):
                check.validate(manifest, root)


if __name__ == "__main__":
    unittest.main()
