import struct
import unittest
from quest_resources import localized_quest_name


def fstring(key):
    encoded = key.encode() + b'\0'
    return struct.pack('<I', len(encoded)) + encoded


class QuestNameTests(unittest.TestCase):
    def test_reads_unique_serialized_localization_key(self):
        data = b'prefix' + fstring('QuestRumor_026') + b'suffix'
        self.assertEqual(localized_quest_name(data, {'QuestRumor_026':'见习医师'}), '见习医师')

    def test_does_not_guess_from_bare_or_ambiguous_keys(self):
        loc = {'QuestRumor_026':'见习医师', 'QuestRumor_001':'凶斧'}
        self.assertEqual(localized_quest_name(b'QuestRumor_026\0', loc), '')
        self.assertEqual(localized_quest_name(fstring('QuestRumor_026')+fstring('QuestRumor_001'), loc), '')


if __name__ == '__main__':
    unittest.main()
