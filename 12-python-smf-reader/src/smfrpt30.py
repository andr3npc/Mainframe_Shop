"""Python twin of HLASM SMFRPT30: reads BDW/RDW-staged SMF type-30
subtype-5 records and prints the identical CPU/elapsed report.
Stdlib only. Exit codes: 0 report, 4 no subtype-5 records, 8 bad input."""
import argparse, json, struct, sys

# Offsets pinned empirically on ZOS31 (see docs/DESIGN.md).
IOF_AT = 32      # header offset of SMF30IOF triplet
COF_AT = 56      # header offset of SMF30COF triplet
RST_AT = 64      # SMF30RST offset within ID section
CPT_AT = 4       # SMF30CPT offset within CAS section
CPS_AT = 8       # SMF30CPS offset within CAS section

RTY_AT = 5       # SMF record type byte (record-relative, RDW included)
TME_AT = 6       # SMF30TME record write time, hundredths (fullword)
STP_AT = 22      # SMF30 subtype halfword
HDR = '  SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT'
COLS = ' JOB NAME        CPU (SEC)    ELAPSED (SEC)'


class ParseError(Exception):
    pass


def _chain(data, start, end, lo, kind):
    """Validate that length-prefixed chunks EXACTLY tile data[start:end]
    (each descriptor halfword >= lo, chunks sum to end-start with no
    slack); return the (start, end) pair of every chunk, or raise
    ParseError naming the first inconsistency."""
    chunks, i = [], start
    while i < end:
        if i + 4 > end:
            raise ParseError('%s: %d trailing byte(s) at offset %d cannot '
                             'hold a descriptor word' % (kind, end - i, i))
        ln = struct.unpack('>H', data[i:i+2])[0]
        if ln < lo:
            raise ParseError('%s: length %d at offset %d below minimum %d'
                             % (kind, ln, i, lo))
        if i + ln > end:
            raise ParseError('%s: length %d at offset %d overruns end %d'
                             % (kind, ln, i, end))
        chunks.append((i, i + ln))
        i += ln
    return chunks


def _records(data):
    """Return records (incl. RDW) by deterministic validate-by-tiling.

    BDW+RDW framing is committed to when the outer chunks (each >= 8)
    exactly tile the whole file; every block's inner RDWs must then
    exactly tile that block, and any inner inconsistency raises — a
    file whose outer chunks tile but whose block bodies do not is
    corrupt BDW data and is never silently reinterpreted as a bare
    RDW stream (which could drop or fabricate rows). Bare-RDW framing
    is accepted only when the outer BDW tiling is impossible. If
    neither tiling validates, ParseError names the first inconsistency
    found by each attempt. Note: an empty BDW block (length 4, no
    records) fails the outer tiling minimum of 8 by design."""
    if len(data) < 4:
        raise ParseError('input shorter than one descriptor word')
    try:
        blocks = _chain(data, 0, len(data), 8, 'BDW')
    except ParseError as bdw_err:
        try:
            return [data[s:e]
                    for s, e in _chain(data, 0, len(data), 4, 'RDW')]
        except ParseError as rdw_err:
            raise ParseError('no framing tiles the input (%s; %s)'
                             % (bdw_err, rdw_err)) from None
    recs = []
    for s, e in blocks:
        recs.extend(data[a:b] for a, b in _chain(data, s + 4, e, 4, 'RDW'))
    return recs


def _triplet(rec, at):
    off = struct.unpack('>I', rec[at:at+4])[0]
    ln, cnt = struct.unpack('>HH', rec[at+4:at+8])
    return off, ln, cnt


def parse(data):
    """Return [(jobname, cpu_hundredths, elapsed_hundredths), ...]"""
    rows = []
    for rec in _records(data):
        if len(rec) < 24:
            raise ParseError('record shorter than SMF header (%d)' % len(rec))
        if rec[RTY_AT] != 30:
            continue
        if struct.unpack('>H', rec[STP_AT:STP_AT+2])[0] != 5:
            continue
        # COF_AT is the higher of the two triplet offsets, so this one
        # check also guarantees the IOF_AT triplet fits.
        if COF_AT + 8 > len(rec):
            raise ParseError('record too short for triplet headers '
                             '(%d < %d)' % (len(rec), COF_AT + 8))
        ioff, iln, ion = _triplet(rec, IOF_AT)
        coff, cln, con = _triplet(rec, COF_AT)
        if ion == 0 or con == 0:          # absent section: skip, like SMFRPT30
            continue
        if ioff + iln > len(rec) or coff + cln > len(rec):
            raise ParseError('triplet points past record end')
        if iln < RST_AT + 4:
            raise ParseError('ID section too short (%d) for SMF30RST '
                             'at +%d' % (iln, RST_AT))
        if cln < CPS_AT + 4:
            raise ParseError('CAS section too short (%d) for SMF30CPS '
                             'at +%d' % (cln, CPS_AT))
        ids, cas = rec[ioff:ioff+iln], rec[coff:coff+cln]
        jbn = ids[0:8].decode('cp1047').rstrip()
        tme = struct.unpack('>I', rec[TME_AT:TME_AT+4])[0]
        rst = struct.unpack('>I', ids[RST_AT:RST_AT+4])[0]
        cpt = struct.unpack('>I', cas[CPT_AT:CPT_AT+4])[0]
        cps = struct.unpack('>I', cas[CPS_AT:CPS_AT+4])[0]
        rows.append((jbn, cpt + cps, tme - rst))
    return rows


def report(rows):
    out = [HDR, COLS]
    for jbn, cpu, ela in rows:
        out.append(' %-8s%17.2f%16.2f' % (jbn, cpu / 100.0, ela / 100.0))
    return '\n'.join(out) + '\n'


def to_json(rows):
    return json.dumps([{'job': j, 'cpu_sec': c / 100, 'elapsed_sec': e / 100}
                       for j, c, e in rows])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('stagefile', help='USS binary staging file (BDW/RDW)')
    ap.add_argument('--json', action='store_true', dest='as_json')
    a = ap.parse_args(argv)
    try:
        with open(a.stagefile, 'rb') as f:
            data = f.read()
        if not data:
            raise ParseError('staging file is empty')
        rows = parse(data)
    except (OSError, ParseError) as e:
        print('SMFRPT30PY ERROR:', e, file=sys.stderr)
        return 8
    if not rows:
        print('SMFRPT30PY: no type 30 subtype 5 records', file=sys.stderr)
        return 4
    sys.stdout.write(to_json(rows) + '\n' if a.as_json else report(rows))
    return 0


if __name__ == '__main__':
    sys.exit(main())
