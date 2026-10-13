from pathlib import Path
import unittest


DOCKERFILE = Path(__file__).with_name("Dockerfile")


class DockerfileContractTests(unittest.TestCase):
    def test_runtime_stage_copies_challenge_context_before_build_artifacts(self):
        lines = DOCKERFILE.read_text(encoding="utf-8").splitlines()

        self.assertEqual(
            lines.count("COPY . /home/"),
            1,
            "the official challenge-context copy must appear exactly once",
        )

        runtime_stage = lines.index("FROM ubuntu:24.04")
        context_copy = lines.index("COPY . /home/")
        build_artifact_copies = [
            index for index, line in enumerate(lines) if line.startswith("COPY --from=build ")
        ]

        self.assertTrue(build_artifact_copies, "runtime stage must copy built artifacts")
        self.assertGreater(context_copy, runtime_stage)
        self.assertLess(context_copy, min(build_artifact_copies))


if __name__ == "__main__":
    unittest.main()
