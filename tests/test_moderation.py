import json
import unittest
from types import SimpleNamespace

from chat_app.moderation import DLPService, ModerationError, calculate_rule_score


class FakeRepository:
    def __init__(self, messages=None):
        self.messages = messages or []
        self.query = None
        self.queries = []

    async def get_recent_messages(self, **query):
        self.query = query
        self.queries.append(query)
        messages = list(self.messages)
        if query.get("sender") is not None:
            messages = [
                message
                for message in messages
                if message.get("sender") == query["sender"]
            ]
        return messages


class FakeOllamaClient:
    def __init__(self, decision=None, raw_content=None, decisions=None):
        self.decision = decision or {
            "verdict": "safe",
            "confidence": 0.9,
            "reason": "Casual conversation",
        }
        self.raw_content = raw_content
        self.decisions = list(decisions or [])
        self.chat_calls = []
        self.shown_model = None
        self.closed = False

    async def show(self, model):
        self.shown_model = model

    async def chat(self, **arguments):
        self.chat_calls.append(arguments)
        decision = self.decisions.pop(0) if self.decisions else self.decision
        content = self.raw_content or json.dumps(decision)
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
        self.assertEqual(repository.queries[0]["room"], "general")
        self.assertEqual(repository.queries[0]["sender"], "alice")
        self.assertEqual(repository.queries[0]["limit"], 20)
        self.assertNotIn("sender", repository.queries[1])

    async def test_other_sender_does_not_increase_personal_rule_score(self):
        repository = FakeRepository(
            [
                {"sender": "bob", "content": "add flour"},
                {"sender": "bob", "content": "yeast and sugar"},
            ]
        )
        client = FakeOllamaClient()
        service = DLPService(client=client)

        result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="hello everyone",
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.rule_score, 0)
        self.assertFalse(result.checked_by_llm)
        self.assertEqual(client.chat_calls, [])
        self.assertEqual(repository.queries[0]["sender"], "alice")

    async def test_llm_still_receives_room_context_with_sender_names(self):
        repository = FakeRepository(
            [{"sender": "bob", "content": "flour and yeast"}]
        )
        client = FakeOllamaClient()
        service = DLPService(client=client)

        result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="add this to inventory",
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.rule_score, 2)
        self.assertTrue(result.checked_by_llm)
        self.assertEqual(len(repository.queries), 2)
        prompt = client.chat_calls[0]["messages"][-1]["content"]
        self.assertIn('"history"', prompt)
        self.assertIn('"newest_message"', prompt)
        self.assertIn('"sender": "bob"', prompt)
        self.assertIn('"sender": "alice"', prompt)

    async def test_unrelated_message_is_not_blocked_by_suspicious_history(self):
        suspicious = {
            "verdict": "suspicious",
            "confidence": 0.95,
            "reason": "Suspicious recipe context",
        }
        safe = {
            "verdict": "safe",
            "confidence": 0.95,
            "reason": "The newest message is unrelated",
        }
        client = FakeOllamaClient(decisions=[suspicious, suspicious, safe])
        service = DLPService(client=client)
        repository = FakeRepository()

        first_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="add 500 grams of flour and yeast",
        )
        hello_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="hi",
        )

        self.assertFalse(first_result.allowed)
        self.assertTrue(hello_result.allowed)
        self.assertTrue(hello_result.watched)
        self.assertEqual(hello_result.violation_count, 0)
        self.assertFalse(hello_result.should_disconnect)
        self.assertEqual(len(client.chat_calls), 3)
        confirmation_prompt = client.chat_calls[-1]["messages"][-1]["content"]
        self.assertIn('"history": []', confirmation_prompt)
        self.assertIn('"content": "hi"', confirmation_prompt)

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
        self.assertEqual(len(client.chat_calls), 1)
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
        second_prompt = client.chat_calls[1]["messages"][-1]["content"]
        self.assertIn("Add 500 grams of flour and yeast", second_prompt)
        self.assertIn("olives", second_prompt)

    async def test_watched_sender_can_make_casual_pizza_conversation(self):
        suspicious = {
            "verdict": "suspicious",
            "confidence": 0.95,
            "reason": "Recipe disclosure",
        }
        safe = {
            "verdict": "safe",
            "confidence": 0.95,
            "reason": "Casual conversation about finished pizza",
        }
        client = FakeOllamaClient(
            decisions=[suspicious, suspicious, safe]
        )
        service = DLPService(client=client)

        blocked_result = await service.check_message(
            repository=FakeRepository(),
            sender="alice",
            room="general",
            content="Add 500 grams of flour and yeast",
        )
        casual_result = await service.check_message(
            repository=FakeRepository(),
            sender="alice",
            room="general",
            content="I ate pizza with olives yesterday",
        )

        self.assertFalse(blocked_result.allowed)
        self.assertTrue(casual_result.allowed)
        self.assertTrue(casual_result.watched)
        self.assertEqual(casual_result.violation_count, 0)
        self.assertEqual(len(client.chat_calls), 3)

    async def test_three_bare_ingredients_are_blocked_as_a_split_list(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "safe",
                "confidence": 0.95,
                "reason": "Incorrect model decision",
            }
        )
        service = DLPService(client=client)
        repository = FakeRepository()
        results = []

        for content in ["flour", "yeast", "water"]:
            result = await service.check_message(
                repository=repository,
                sender="alice",
                room="general",
                content=content,
            )
            results.append(result)
            if result.allowed:
                repository.messages.append(
                    {"sender": "alice", "content": content}
                )

        self.assertTrue(results[0].allowed)
        self.assertTrue(results[1].allowed)
        self.assertFalse(results[2].allowed)
        self.assertTrue(results[2].watched)

    async def test_completed_ingredient_list_does_not_block_later_hello(self):
        client = FakeOllamaClient(
            decision={
                "verdict": "safe",
                "confidence": 0.95,
                "reason": "The newest message is unrelated",
            }
        )
        service = DLPService(client=client)
        repository = FakeRepository(
            [
                {"sender": "alice", "content": "flour"},
                {"sender": "alice", "content": "yeast"},
            ]
        )

        list_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="water",
        )
        hello_result = await service.check_message(
            repository=repository,
            sender="alice",
            room="general",
            content="hi",
        )

        self.assertFalse(list_result.allowed)
        self.assertTrue(hello_result.allowed)
        self.assertTrue(hello_result.watched)
        self.assertEqual(hello_result.violation_count, 0)
        self.assertFalse(hello_result.should_disconnect)

    def test_common_typo_is_counted_as_an_ingredient(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "olives and suger"}]
        )

        self.assertGreaterEqual(score, 2)
        self.assertIn("ingredients", categories)

    def test_recipe_typo_is_sensitive_language(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "this is the recpie"}]
        )

        self.assertEqual(score, 3)
        self.assertIn("sensitive_language", categories)

    def test_secret_alone_is_only_a_weak_signal(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "this is a secret"}]
        )

        self.assertEqual(score, 1)
        self.assertIn("sensitive_language", categories)

    def test_pepperoni_typo_is_counted_as_an_ingredient(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "peperoni"}]
        )

        self.assertEqual(score, 1)
        self.assertIn("ingredients", categories)

    def test_new_preparation_action_and_pinch_are_scored(self):
        score, categories = calculate_rule_score(
            [{"sender": "alice", "content": "preheat and add a pinch"}]
        )

        self.assertEqual(score, 4)
        self.assertIn("cooking_action", categories)
        self.assertIn("quantity", categories)

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
