from __future__ import annotations
import json, os, pathlib, tempfile, unittest
from unittest import mock
from revenue.opportunity_identity_alias import registry as g
from revenue.opportunity_identity_alias import strict as s
from revenue.opportunity_identity_alias.aliases import normalize_alias

def url(v): return {"type":"authority_url","value":v}
def obs(label): return {"schema":s.OBSERVATION_SCHEMA,"buyer_organization_key":"buyer-one","aliases":[{"type":"official_id","value":label}]}
class RecoveryHostiles(unittest.TestCase):
    def test_ip_and_special_use_hosts_rejected(self):
        bad=(
            "https://127.0.0.1/x", "https://192.168.1.1/x", "https://127.1/x",
            "https://foo.localhost/x", "https://foo.local/x", "https://foo.internal/x",
            "https://foo.invalid/x", "https://foo.test/x", "https://foo.home.arpa/x", "https://foo.onion/x",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(s.IdentityAliasError): normalize_alias(url(value))
    def test_percent_encoded_path_ambiguity_rejected(self):
        bad=(
            "https://a.example.org/a/%2e%2e/b", "https://a.example.org/a/%2E/b",
            "https://a.example.org/a%2fb", "https://a.example.org/a%2Fb",
            "https://a.example.org/a%5cb", "https://a.example.org/%252e%252e/x",
        )
        for value in bad:
            with self.subTest(value=value), self.assertRaises(s.IdentityAliasError): normalize_alias(url(value))
    def test_path_replacement_cannot_substitute_open_generation(self):
        if not hasattr(os, "O_NOFOLLOW"): self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td:
            d=pathlib.Path(td); target=d/"input.json"; replacement=d/"replacement.json"
            target.write_text(json.dumps(obs("ORIGINAL"))); replacement.write_text(json.dumps(obs("REPLACED")))
            original_read=os.read; swapped=False
            def racing_read(fd,n):
                nonlocal swapped
                if not swapped:
                    swapped=True; os.replace(replacement,target)
                return original_read(fd,n)
            with mock.patch.object(g.os,"read",side_effect=racing_read):
                with self.assertRaisesRegex(s.IdentityAliasError,"generation changed"):
                    g.read_json_file_no_follow(target,label="race input")
            self.assertEqual(json.loads(target.read_text())["aliases"][0]["value"],"REPLACED")
    def test_same_inode_mutation_during_read_fails_closed(self):
        if not hasattr(os, "O_NOFOLLOW"): self.skipTest("O_NOFOLLOW unavailable")
        with tempfile.TemporaryDirectory() as td:
            target=pathlib.Path(td)/"input.json"; target.write_text(json.dumps(obs("ORIGINAL")))
            original_read=os.read; mutated=False
            def racing_read(fd,n):
                nonlocal mutated
                chunk=original_read(fd,n)
                if chunk and not mutated:
                    mutated=True; target.write_text(json.dumps(obs("MUTATED-LONGER")))
                return chunk
            with mock.patch.object(g.os,"read",side_effect=racing_read):
                with self.assertRaisesRegex(s.IdentityAliasError,"generation changed"):
                    g.read_json_file_no_follow(target,label="race input")
if __name__=="__main__": unittest.main()
