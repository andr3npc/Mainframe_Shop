import json, os, struct, sys, unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import smfrpt30 as M


def mkrec(jbn, tme, rst, cpt, cps, rty=30, stp=5):
    r = bytearray(316)
    struct.pack_into('>H', r, 0, 316)                 # RDW
    r[5] = rty
    struct.pack_into('>I', r, 6, tme)
    struct.pack_into('>H', r, 22, stp)
    struct.pack_into('>IHH', r, M.IOF_AT, 228, 72, 1)  # ID triplet
    struct.pack_into('>IHH', r, M.COF_AT, 300, 16, 1)  # CAS triplet
    r[228:236] = jbn.ljust(8).encode('cp1047')
    struct.pack_into('>I', r, 228 + M.RST_AT, rst)
    struct.pack_into('>I', r, 300 + M.CPT_AT, cpt)
    struct.pack_into('>I', r, 300 + M.CPS_AT, cps)
    return bytes(r)


def blockof(*recs):
    body = b''.join(recs)
    return struct.pack('>HH', len(body) + 4, 0) + body


class TestParse(unittest.TestCase):
    def test_golden_row(self):
        rec = mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)
        rows = M.parse(blockof(rec))
        self.assertEqual(rows, [('PAYROLL', 251500, 360000)])

    def test_skips_other_types(self):
        rec = mkrec('NOPE', 100, 0, 1, 1, rty=70)
        self.assertEqual(M.parse(blockof(rec)), [])

    def test_report_matches_golden_format(self):
        rows = [('ANDREJ1', 13023, 50000),
                ('PAYROLL', 251500, 360000),
                ('BACKUP', 10000, 12000)]
        want = (
            '  SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT\n'
            ' JOB NAME        CPU (SEC)    ELAPSED (SEC)\n'
            ' ANDREJ1            130.23          500.00\n'
            ' PAYROLL           2515.00         3600.00\n'
            ' BACKUP             100.00          120.00\n'
        )
        self.assertEqual(M.report(rows), want)

    def test_json(self):
        rows = [('BACKUP', 10000, 12000)]
        got = json.loads(M.to_json(rows))
        self.assertEqual(got, [{'job': 'BACKUP',
                                'cpu_sec': 100.0, 'elapsed_sec': 120.0}])

    def test_truncated_record_raises(self):
        rec = mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)[:100]
        bad = struct.pack('>HH', 104, 0) + rec
        with self.assertRaises(M.ParseError):
            M.parse(bad)


if __name__ == '__main__':
    unittest.main()
