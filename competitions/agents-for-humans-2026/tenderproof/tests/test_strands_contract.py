import pathlib
import unittest


class StrandsSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = pathlib.Path("strands_agent.py").read_text(encoding="utf-8")

    def test_uses_official_agent_and_tool_interfaces(self):
        self.assertIn("from strands import Agent, tool", self.text)
        self.assertGreaterEqual(self.text.count("@tool"), 3)
        self.assertIn("Agent(**kwargs)", self.text)

    def test_prompt_has_explicit_commercial_truth_boundary(self):
        self.assertIn("Never invent certifications", self.text)
        self.assertIn("buyer_send_authorized=false", self.text)
        self.assertIn("A human must approve", self.text)


if __name__ == "__main__":
    unittest.main()
