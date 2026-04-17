import types
import unittest

from text_to_garmin.parser import _collect_response


class _FakeSession:
    def __init__(self, content):
        self.content = content
        self.prompts = []

    async def send_and_wait(self, prompt, timeout):
        self.prompts.append((prompt, timeout))
        return types.SimpleNamespace(data=types.SimpleNamespace(content=self.content))


class ParserResponseTests(unittest.IsolatedAsyncioTestCase):
    async def test_collect_response_uses_send_and_wait(self) -> None:
        session = _FakeSession("```json\n{}\n```")

        response = await _collect_response(session, "Parse this workout")

        self.assertEqual(response, "```json\n{}\n```")
        self.assertEqual(session.prompts, [("Parse this workout", 120.0)])


if __name__ == "__main__":
    unittest.main()
