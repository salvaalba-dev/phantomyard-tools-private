from datetime import datetime, timezone
import unittest
import assistant


class AssistantTests(unittest.TestCase):
    def observation(self):
        return dict(persona="lead", org="example", provenance="state", exists=True, served=True,
                    checked_at=datetime.now(timezone.utc).isoformat(), vault="SECRET")

    def test_only_selected_local_actor_and_public_contact(self):
        actor = dict(id="lead", org="example", key="example:lead", channels={"npub":"npub1"+"q"*58})
        result = assistant.attach(self.observation(), [actor])
        self.assertEqual(result["key"], "example:lead")
        self.assertNotIn("vault", result)
        actor["profile_remote"] = True
        with self.assertRaises(ValueError):
            assistant.attach(self.observation(), [actor])
        actor.pop("profile_remote")
        actor["org"] = "foreign"
        with self.assertRaises(ValueError):
            assistant.attach(self.observation(), [actor])

    def test_no_unserved_default_or_private_contact(self):
        report = self.observation()
        report["served"] = False
        with self.assertRaises(ValueError):
            assistant.attach(report, [])
        actor = dict(id="lead", org="example", key="example:lead", channels={"npub":"nsec1SECRET"})
        self.assertEqual(assistant.attach(self.observation(), [actor])["npub"], "")

    def test_no_untrusted_identifier(self):
        report = self.observation()
        report["persona"] = "../../foreign"
        with self.assertRaises(ValueError):
            assistant.attach(report, [])


if __name__ == "__main__":
    unittest.main()
