"""Offline regression checks for cache layout, bounded continuity and old saves. No models or network."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from astra_mind.agent import BridgeAgent
from astra_mind.initiative import Watch, watch_prompt, watch_system
from astra_mind.local_ship import LocalShip
from astra_mind.memory import MemoryKeeper
from astra_mind.openrouter import Completion, ToolCall
from astra_mind.prompt_layout import cached_prompt


class ContextTests(unittest.TestCase):
    def test_changing_data_never_changes_the_instruction_prefix_or_loses_values(self):
        template = 'Rules stay literal. Role: {role}. Orders: {orders}. Picture: {state}. End rule.'
        first = dict(role='crew', orders='Protect Alpha until recovered', state='Aquila hull 74; contact T-31')
        second = dict(role='crew', orders='Protect Bravo until recovered', state='Aquila hull 68; contact T-32')
        a, ac = cached_prompt(template, first, ('orders', 'state'))
        b, bc = cached_prompt(template, second, ('orders', 'state'))
        self.assertEqual(a, b)
        for fields, context in ((first, ac), (second, bc)):
            for key in ('orders', 'state'):
                self.assertIn(fields[key], context)
                self.assertEqual(context.count(fields[key]), 1)
        self.assertIn('End rule.', a)

    def test_the_watch_keeps_the_complete_console_and_ship_picture(self):
        state = LocalShip(stations=True, fight=True).snapshot()
        a, ac = watch_prompt('it', state, 'Hold fire until told', 'Prefers standoff', 'Recall Bravo')
        changed = copy.deepcopy(state)
        changed['hull_pct'] = 23
        b, bc = watch_prompt('it', changed, 'Protect Alpha', 'Prefers standoff', 'Recall Alpha')
        self.assertEqual(a, b)
        self.assertIn('Hold fire until told', ac)
        self.assertIn('Recall Alpha', bc)
        # The old formatter's actual variable fields survive, not merely their heading.
        old = watch_system('it', state, 'Hold fire until told', 'Prefers standoff', 'Recall Bravo')
        self.assertIn(old.split('\nShip state\n')[1], ac)
        self.assertIn(old.split('\nConsoles now\n')[1].split('\n\nShip state')[0], ac)

    def test_a_quiet_watch_waits_and_does_not_keep_waking_without_change(self):
        state = LocalShip(stations=True, fight=False).snapshot()
        w = Watch()
        args = dict(flags=[], picture=None, captain_t=0, busy=False)
        self.assertIsNone(w.tick(state, 100, **args))
        self.assertIsNone(w.tick(state, 174, **args))
        check = w.tick(state, 175, **args)
        self.assertIsNotNone(check)
        w.ran(check, False, now=175)
        self.assertIsNone(w.tick(state, 1000, **args))
        state['hull_pct'] = 50
        self.assertIsNotNone(w.tick(state, 1001, **args))

    def test_a_long_watch_keeps_whole_tool_exchanges_bounded(self):
        agent = BridgeAgent(None, LocalShip(), None)
        for i in range(10000):
            agent.history.extend([{'role': 'user', 'content': f'Captain order {i}'},
                                  {'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(i)}]},
                                  {'role': 'tool', 'tool_call_id': str(i), 'content': 'ok'}])
            agent._trim_history()
        self.assertLessEqual(len(agent.history), 32 * 3)
        self.assertEqual(agent.history[0]['role'], 'user')
        for i in range(0, len(agent.history), 3):
            self.assertEqual(agent.history[i+1]['tool_calls'][0]['id'], agent.history[i+2]['tool_call_id'])
        self.assertEqual(agent.history[-3]['content'], 'Captain order 9999')


class LargeHistoryTests(unittest.TestCase):
    def test_large_exchanges_keep_recent_complete_turns_without_clipping_their_text(self):
        agent = BridgeAgent(None, LocalShip(), None)
        for i in range(14):
            agent.history.extend([{'role': 'user', 'content': str(i) + 'x' * 15000},
                {'role': 'assistant', 'content': None, 'tool_calls': [{'id': str(i)}]},
                {'role': 'tool', 'tool_call_id': str(i), 'content': 'ok'}])
        agent._trim_history()
        self.assertLess(len(agent.history), 14 * 3)
        self.assertGreaterEqual(len(agent.history), 8 * 3)
        self.assertEqual(agent.history[-3]['content'], '13' + 'x' * 15000)
        for i in range(0,len(agent.history),3):
            self.assertEqual(agent.history[i+1]['tool_calls'][0]['id'],agent.history[i+2]['tool_call_id'])


class DelegationMigrationTests(unittest.TestCase):
    def test_legacy_default_migrates_but_explicit_current_advice_survives(self):
        from astra_mind.delegation import Delegation
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'delegation.json'
            path.write_text(json.dumps({'flight': 'advise', 'helm': 'advise'}))
            d = Delegation(str(path)); d.begin(new=False)
            self.assertEqual(d.levels, {'flight': 'auto', 'helm': 'advise'})
            d.set('flight', 'advise')
            restored = Delegation(str(path)); restored.begin(new=False)
            self.assertEqual(restored.levels, {'flight': 'advise', 'helm': 'advise'})
            path.write_text(json.dumps({'flight': 'manual', 'helm': 'auto'}))
            restored.begin(new=False)
            self.assertEqual(restored.levels, {'flight': 'manual', 'helm': 'auto'})


class MemoriesTests(unittest.IsolatedAsyncioTestCase):
    async def test_professional_learning_does_not_evict_personal_memories(self):
        class Model:
            async def chat(self, **kw):
                self.messages = kw['messages']
                await kw['on_tool_call'](ToolCall('remember', json.dumps({'officer': 'flight', 'kind': 'lesson',
                    'memory': 'Price knows the Captain wants damaged Falcons recalled before another sortie.'}), 'lesson'))
                return Completion()
        model = Model()
        personal = [{'kind': 'personal', 'memory': f'Personal fact {i}'} for i in range(14)]
        store = {'flight': copy.deepcopy(personal)}
        saved = []
        keeper = MemoryKeeper(model, store, lambda _: None, save=lambda: saved.append(copy.deepcopy(store)))
        await keeper._read(['Captain: Recall damaged Falcons before another sortie.'])
        self.assertEqual(store['flight'][:14], personal)
        self.assertEqual(store['flight'][-1]['kind'], 'lesson')
        self.assertEqual(saved[-1], store)
        self.assertIn('damaged Falcons', keeper.lines())
        self.assertIn('Captain: Recall damaged Falcons', model.messages[-1]['content'])

    async def test_the_record_belongs_only_to_the_person_and_side_who_lived_it(self):
        from bench.war_minds_unit import AstraTests
        rig = AstraTests(methodName='test_the_picket_has_a_commander_with_a_voice_and_the_chain_of_command')
        await rig.asyncSetUp()
        war = rig.minds
        war.remember_person('astra', 'Captain Test', 'The Captain asked for cover.')
        self.assertIn('asked for cover', war.person_history('astra', 'Captain Test'))
        self.assertEqual(war.person_history('mandate', 'Captain Test'), '')
        self.assertEqual(war.person_history('astra', 'Someone Else'), '')
        war.reset()
        rig.doCleanups()
        self.assertIn('asked for cover', war.person_history('astra', 'Captain Test'))

