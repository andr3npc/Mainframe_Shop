import contextlib, io, json, os, struct, sys, tempfile, unittest

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

    def test_multi_block(self):
        b1 = blockof(mkrec('PAYROLL', 3960000, 3600000, 250000, 1500))
        b2 = blockof(mkrec('BACKUP', 3972000, 3960000, 9999, 1))
        rows = M.parse(b1 + b2)
        self.assertEqual(rows, [('PAYROLL', 251500, 360000),
                                ('BACKUP', 10000, 12000)])

    def test_truncated_record_raises(self):
        rec = mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)[:100]
        bad = struct.pack('>HH', 104, 0) + rec
        with self.assertRaises(M.ParseError):
            M.parse(bad)

    def _tmpfile(self, data):
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write(data)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_main_rc4(self):
        # A well-framed file with no type-30 subtype-5 records -> RC 4.
        path = self._tmpfile(blockof(mkrec('NOPE', 100, 0, 1, 1, rty=70)))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = M.main([path])
        self.assertEqual(rc, 4)
        self.assertIn('no type 30 subtype 5 records', err.getvalue())

    def test_main_rc8_short_record(self):
        # A type-30 subtype-5 record that ends before the triplet
        # headers (len 30 < COF_AT+8) must be RC 8, not a traceback.
        r = bytearray(30)
        struct.pack_into('>H', r, 0, 30)              # RDW
        r[5] = 30                                     # SMF type 30
        struct.pack_into('>H', r, 22, 5)              # subtype 5
        path = self._tmpfile(blockof(bytes(r)))
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            rc = M.main([path])
        self.assertEqual(rc, 8)
        self.assertIn('SMFRPT30PY ERROR:', err.getvalue())

    def test_main_json(self):
        path = self._tmpfile(
            blockof(mkrec('PAYROLL', 3960000, 3600000, 250000, 1500)))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = M.main(['--json', path])
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue()),
                         [{'job': 'PAYROLL',
                           'cpu_sec': 2515.0, 'elapsed_sec': 3600.0}])


if __name__ == '__main__':
    unittest.main()
