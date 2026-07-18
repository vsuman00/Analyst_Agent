import importlib
import os
import unittest
from types import SimpleNamespace


class FakeCompletions:
    def __init__(self, content="{}", finish_reason="stop"):
        self.content = content
        self.finish_reason = finish_reason
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=self.content),
                    finish_reason=self.finish_reason,
                )
            ],
            usage=SimpleNamespace(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15,
            ),
        )


class LLMClientTests(unittest.TestCase):
    def _load_client(self, model):
        os.environ["OPENAI_API_KEY"] = "sk-test"
        os.environ["OPENAI_MODEL"] = model
        os.environ["OPENAI_MAX_TOKENS"] = "2048"
        os.environ.pop("OPENAI_JSON_MIN_TOKENS", None)
        os.environ.pop("OPENAI_REASONING_EFFORT", None)
        os.environ.pop("OPENAI_VERBOSITY", None)

        import app.utils.llm_client as llm_client

        return importlib.reload(llm_client)

    def _install_fake_client(self, llm_client, fake_completions):
        llm_client._client = SimpleNamespace(
            chat=SimpleNamespace(completions=fake_completions)
        )

    def test_gpt5_json_calls_reserve_visible_output_tokens(self):
        llm_client = self._load_client("gpt-5-mini")
        fake = FakeCompletions(content="{}")
        self._install_fake_client(llm_client, fake)

        llm_client._call_with_retry(
            [{"role": "user", "content": "Return JSON."}],
            response_format={"type": "json_object"},
            max_tokens=80,
        )

        self.assertEqual(fake.kwargs["model"], "gpt-5-mini")
        self.assertEqual(fake.kwargs["max_completion_tokens"], 4096)
        self.assertEqual(fake.kwargs["reasoning_effort"], "minimal")
        self.assertEqual(fake.kwargs["verbosity"], "low")
        self.assertNotIn("temperature", fake.kwargs)

    def test_gpt5_large_json_calls_scale_completion_token_limit(self):
        llm_client = self._load_client("gpt-5-mini")
        fake = FakeCompletions(content="{}")
        self._install_fake_client(llm_client, fake)

        llm_client._call_with_retry(
            [{"role": "user", "content": "Return enterprise artifacts JSON."}],
            response_format={"type": "json_object"},
            max_tokens=1500,
        )

        self.assertEqual(fake.kwargs["max_completion_tokens"], 4500)

    def test_legacy_chat_models_keep_legacy_token_and_temperature_params(self):
        llm_client = self._load_client("gpt-4o-mini")
        fake = FakeCompletions(content="{}")
        self._install_fake_client(llm_client, fake)

        llm_client._call_with_retry(
            [{"role": "user", "content": "Return JSON."}],
            response_format={"type": "json_object"},
            max_tokens=80,
        )

        self.assertEqual(fake.kwargs["max_tokens"], 80)
        self.assertEqual(fake.kwargs["temperature"], 0)
        self.assertNotIn("max_completion_tokens", fake.kwargs)
        self.assertNotIn("reasoning_effort", fake.kwargs)
        self.assertNotIn("verbosity", fake.kwargs)

    def test_empty_response_error_includes_finish_reason_and_token_limit(self):
        llm_client = self._load_client("gpt-5-mini")
        fake = FakeCompletions(content="", finish_reason="length")
        self._install_fake_client(llm_client, fake)

        with self.assertRaisesRegex(
            RuntimeError,
            "OpenAI returned empty content .*finish_reason=length.*token_limit=4096",
        ):
            llm_client._call_with_retry(
                [{"role": "user", "content": "Return JSON."}],
                response_format={"type": "json_object"},
                max_tokens=80,
            )


if __name__ == "__main__":
    unittest.main()
