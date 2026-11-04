import struct
import unittest
from unittest.mock import patch

from quest_flow_mapping import _nodes, _connected_finishes, derive_flow_rewards


def batch(names):
    encoded = [n.encode('utf8') for n in names]
    return (struct.pack('<IIQ', len(names), sum(map(len, encoded)), 0)
            + bytes(8 * len(names))
            + b''.join(struct.pack('>H', len(n)) for n in encoded)
            + b''.join(encoded))


def synthetic_flow():
    names = ['FinishQuest_C', 'LootItems_C', 'SyntheticFlow', 'Region.AC_Test']
    finish_guid, award_guid = bytes(range(1, 17)), bytes(range(30, 46))
    finish = b'\x01\x03' + struct.pack('<i', -1) + finish_guid + award_guid
    award = b'\x01\x03' + struct.pack('<II', 3, 0) + award_guid + finish_guid
    root = (b'\x00\x02\x01\x03' + bytes(range(60, 76))
            + struct.pack('<II', 0, 2)
            + finish_guid + struct.pack('<i', 1)
            + award_guid + struct.pack('<i', 2))
    data = bytearray(bytes(60) + batch(names))
    imports = len(data)
    data += struct.pack('<Q', 0x8000000000000000)
    exports = len(data)
    data += bytes(72 * 3)
    export_end = len(data)
    packages = len(data)
    data += batch(['/Game/PBZstory/PBZQuest/Branch/Synthetic'])
    body = len(data)
    offset = 0
    for i, raw in enumerate([finish, award, root]):
        struct.pack_into('<QQII', data, exports + i * 72, offset, len(raw), i, 0)
        data += raw
        offset += len(raw)
    for position, value in [(4, body), (28, imports), (32, exports),
                             (36, export_end), (48, packages)]:
        struct.pack_into('<I', data, position, value)
    return bytes(data)


class Store:
    files = ['ProjectPBZ/Content/FlowGraph/QuestFlowGraph/Synthetic.uasset']

    def __init__(self, data=None):
        self.data = synthetic_flow() if data is None else data

    def read_file(self, path):
        return self.data


class FlowMappingTests(unittest.TestCase):
    def setUp(self):
        self.items = [{'id': 'AC_Test', 'name': 'Synthetic accessory', 'category': 'accessory'}]

    def test_resolves_export_guid_and_imported_quest(self):
        nodes = _nodes(synthetic_flow())
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]['refs'], {'/game/pbzstory/pbzquest/branch/synthetic'})
        result = derive_flow_rewards(Store(), self.items)
        reward = result['/game/pbzstory/pbzquest/branch/synthetic']['rewards'][0]
        self.assertEqual(reward['id'], 'AC_Test')
        self.assertEqual(reward['quantity'], 1)

    def test_unconnected_nodes_are_not_combined(self):
        nodes = _nodes(synthetic_flow())
        for i, node in enumerate(nodes):
            node['raw'] = node['raw'].replace(nodes[1 - i]['guid'], bytes(16))
        with patch('quest_flow_mapping._nodes', return_value=nodes):
            self.assertEqual(derive_flow_rewards(Store(), self.items), {})

    def test_shared_reward_node_does_not_choose_a_quest(self):
        nodes = _nodes(synthetic_flow())
        nodes[0]['refs'].add('/game/pbzstory/pbzquest/simple/another')
        with patch('quest_flow_mapping._nodes', return_value=nodes):
            self.assertEqual(derive_flow_rewards(Store(), self.items), {})

    def test_follows_unconditional_helper_but_not_a_condition(self):
        finish, award = _nodes(synthetic_flow())
        finish['raw'] = finish['raw'].replace(award['guid'], bytes(16))
        award['raw'] = award['raw'].replace(finish['guid'], bytes(16))
        middle = {'kind': 'SetTag_C', 'guid': bytes(range(90, 106)),
                  'raw': finish['guid'] + award['guid']}
        self.assertEqual(_connected_finishes(award, [finish, award, middle], [finish]), [finish])
        middle['kind'] = 'IsTagExist_C'
        self.assertEqual(_connected_finishes(award, [finish, award, middle], [finish]), [])

    def test_stackable_amount_is_not_invented_from_row_name(self):
        self.items[0]['category'] = 'goods'
        self.assertEqual(derive_flow_rewards(Store(), self.items), {})

    def test_malformed_layout_does_not_claim_mapping(self):
        self.assertEqual(derive_flow_rewards(Store(bytes(80)), self.items), {})


if __name__ == '__main__':
    unittest.main()
