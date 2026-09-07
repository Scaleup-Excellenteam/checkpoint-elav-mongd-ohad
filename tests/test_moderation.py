import json
import unittest
from types import SimpleNamespace

from chat_app.moderation import DLPService, ModerationError, calculate_rule_score


class FakeRepository:
    def __init__(self, messages=None):
        self.messages = messages or []
        self.query = None

    async def get_recent_messages(self, **query):
        self.query = query
        return list(self.messages)


class FakeOllamaClient:
    def __init__(self, decision=None, raw_content=None):
        self.decision = decision or {
            "verdict": "safe",
            "confidence": 0.9,
            "reason": "Casual conversation",
        }
        self.raw_content = raw_content
        self.chat_calls = []
        self.shown_model = None
        self.closed = False

    async def show(self, model):
        self.shown_model = model

    async def chat(self, **arguments):
        self.chat_calls.append(arguments)
        content = self.raw_content or json.dumps(self.decision)
        return SimpleNamespace(message=SimpleNamespace(content=content))

    async def close(self):
        self.closed = True


class DLPServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_casual_pizza_message_skips_llm(self):
        client = FakeOllamaClient()
        service = DLPService(client=client)

        result = await service.check_message(
            repository=FakeRepository(),
            sender="alice",
            room="general",
            content="I ate pizza with basil in Tel Aviv yesterday and it was delicious",
        )

        self.assertTrue(result.allowed)
        self.assertFalse(result.checked_by_llm)
        self.assertEqual(client.chat_calls, [])

    async def test_split_ingredients_are_checked_and_can_be_blocked(self):
        repository = FakeRepository(
            [
                {"sender": "alice", "content": "flour"},
                {"sender": "alice", "content": "yeast"},
            ]
        )
        client = FakeOllamaClient(
            decision={
                "verdict": "suspicious",
                "confidence": 0.95,
                "reason": "Recipe fragments across messages",
            }
        )
        service = DLPService(client=client)

        result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="basil",
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.checked_by_llm)
        self.assertGreaterEqual(result.rule_score, 3)
        self.assertEqual(result.reason_code, "RECIPE_RISK")
        self.assertEqual(len(client.chat_calls), 1)
        self.assertEqual(repository.query["room"], "general")
        self.assertEqual(repository.query["limit"], 20)

    async def test_invalid_model_response_fails_the_check(self):
        client = FakeOllamaClient(raw_content="not json")
        service = DLPService(client=client, rule_threshold=0)

        with self.assertRaises(ModerationError):
            await service.check_message(
                repository=FakeRepository(),
                sender="alice",
                room="general",
                content="hello",
            )

    async def test_readiness_checks_configured_model(self):
        client = FakeOllamaClient()
        service = DLPService(model="qwen3:4b", client=client)

        await service.check_ready()
        await service.close()

        self.assertEqual(client.shown_model, "qwen3:4b")
        self.assertTrue(client.closed)

    async def test_watched_sender_is_checked_even_with_low_new_message_score(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "suspicious",
                "confidence": 0.95,
                "reason": "Recipe disclosure",
            }
        )
        service = DLPService(client=client)
        repository = FakeRepository()

        first_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="Add 500 grams of flour and yeast",
        )
        client.decision = {
            "verdict": "safe",
            "confidence": 0.95,
            "reason": "Model missed the continuation",
        }
        second_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="olives",
        )

        self.assertFalse(first_result.allowed)
        self.assertTrue(first_result.watched)
        self.assertFalse(second_result.allowed)
        self.assertTrue(second_result.watched)
        self.assertEqual(len(client.chat_calls), 2)
        second_prompt = client.chat_calls[1]["messages"][1]["content"]
        self.assertIn("Add 500 grams of flour and yeast", second_prompt)
        self.assertIn("olives", second_prompt)

    def test_common_typo_is_counted_as_an_ingredient(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "olives and suger"}]
        )

        self.assertGreaterEqual(score, 2)
        self.assertIn("ingredients", categories)

    async def test_clear_recipe_is_blocked_even_when_model_returns_safe(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "safe",
                "confidence": 0.95,
                "reason": "Incorrect model decision",
            }
        )
        service = DLPService(client=client)

        result = await service.check_message(
            repository=FakeRepository(),
            sender="alice",
            room="general",
            content=(
                "Add 500 grams of flour and yeast, then knead and bake "
                "for 12 minutes at 220 degrees"
            ),
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.watched)
        self.assertGreaterEqual(result.rule_score, 7)

    async def test_split_recipe_is_blocked_by_accumulated_rule_score(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "safe",
                "confidence": 0.95,
                "reason": "Incorrect model decision",
            }
        )
        service = DLPService(client=client)
        repository = FakeRepository()
        result = None

        for content in ["pizza", "yeast", "sugar", "add", "some", "olives"]:
            result = await service.check_message(
                repository=repository,
                sender="alice",
                room="general",
                content=content,
            )
            if result.allowed:
                repository.messages.append(
                    {"sender": "alice", "content": content}
                )

        self.assertIsNotNone(result)
        self.assertFalse(result.allowed)
        self.assertTrue(result.watched)
        self.assertGreaterEqual(result.rule_score, 6)

    async def test_third_blocked_attempt_requests_disconnect(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "suspicious",
                "confidence": 0.95,
                "reason": "Recipe disclosure",
            }
        )
        service = DLPService(client=client, max_violations=3)
        results = []

        for content in ["add flour", "add yeast", "add cheese"]:
            results.append(
                await service.check_message(
                    repository=FakeRepository(),
                    sender="alice",
                    room="general",
                    content=content,
                )
            )

        self.assertEqual(
            [result.violation_count for result in results],
            [1, 2, 3],
        )
        self.assertFalse(results[0].should_disconnect)
        self.assertFalse(results[1].should_disconnect)
        self.assertTrue(results[2].should_disconnect)


if __name__ == "__main__":
    unittest.main()
