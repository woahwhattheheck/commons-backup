"""Provider adapter contracts against controlled transport; no real network calls."""
import asyncio
import unittest
from types import SimpleNamespace

from autopsy_agent.models import BudgetedModel, RelayModel, RequestBudget, ScriptedModel


def relay_model(response, budget=None):
    instance = RelayModel.__new__(RelayModel)
    instance.config = {'model_id': 'CONTROLLED_TRANSPORT', 'max_tokens': 100}
    instance.session_id = 'test-session'
    instance.budget = budget or RequestBudget(1)
    instance.client = SimpleNamespace(stream_generate=lambda *args: response)
    return instance


async def consume(model):
    return [event async for event in model.stream([{'role': 'user', 'content': [{'text': 'test'}]}], system_prompt='Application instruction')]


class ModelTests(unittest.TestCase):
    def test_normal_relay_response_becomes_strands_events(self):
        model = relay_model(({'role': 'model', 'parts': [{'text': '{}'}]}, ['STOP']))
        events = asyncio.run(consume(model))
        self.assertEqual(events[-1], {'messageStop': {'stopReason': 'end_turn'}})
        self.assertEqual(model.budget.requests[0]['status'], 'SUCCEEDED')
        self.assertIsNone(model.budget.requests[0]['token_usage'])

    def test_empty_or_truncated_finish_is_never_accepted(self):
        for finish in ([], ['MAX_TOKENS'], ['STOP', 'SAFETY']):
            model = relay_model(({'role': 'model', 'parts': [{'text': '{}'}]}, finish))
            with self.assertRaises(RuntimeError):
                asyncio.run(consume(model))
            self.assertEqual(model.budget.requests[0]['status'], 'FAILED')

    def test_provider_tool_call_is_rejected_without_execution(self):
        model = relay_model(({'parts': [{'functionCall': {'name': 'commons_comment', 'args': {}}}]}, ['STOP']))
        with self.assertRaises(RuntimeError):
            asyncio.run(consume(model))

    def test_request_allowance_counts_failed_attempts(self):
        model = relay_model(({'parts': []}, ['STOP']))
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                asyncio.run(consume(model))
        self.assertEqual(len(model.budget.requests), 1)

    def test_standard_provider_is_also_budgeted(self):
        budget = RequestBudget(1)
        first = BudgetedModel(ScriptedModel({}), budget)
        second = BudgetedModel(ScriptedModel({}), budget)
        asyncio.run(consume(first))
        with self.assertRaises(RuntimeError):
            asyncio.run(consume(second))
        self.assertEqual(len(budget.requests), 1)
        self.assertEqual(budget.requests[0]['provider'], 'BEDROCK')

    def test_application_instructions_and_text_reach_existing_client(self):
        seen = []
        model = relay_model(({'parts': [{'text': '{}'}]}, ['STOP']))
        def transport(*args):
            seen.append(args)
            return {'parts': [{'text': '{}'}]}, ['STOP']
        model.client.stream_generate = transport
        asyncio.run(consume(model))
        contents = seen[0][2]
        self.assertIn('Application instruction', contents[0]['parts'][0]['text'])
        self.assertEqual(contents[0]['parts'][1]['text'], 'test')


if __name__ == '__main__':
    unittest.main()
