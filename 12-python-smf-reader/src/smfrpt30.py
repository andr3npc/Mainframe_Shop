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

RTY_AT, TME_AT, STP_AT = 5, 6, 22
HDR = '  SMF TYPE 30 SUBTYPE 5 - JOB CPU/ELAPSED RPT'
COLS = ' JOB NAME        CPU (SEC)    ELAPSED (SEC)'


class ParseError(Exception):
    pass


def _records(data):
    """Yield records (incl. RDW) from BDW+RDW blocks or a bare RDW stream."""
    if len(data) < 4:
        raise ParseError('input shorter than one descriptor word')
    first = struct.unpack('>H', data[0:2])[0]
    i = 0
    # A BDW's length field covers the whole block it introduces; the
    # staging file (docs/DESIGN.md) is always exactly one BDW-framed
    # block, so "first halfword equals the total byte count" is a
    # reliable, magnitude-independent way to detect BDW+RDW mode (it
    # also correctly classifies short/truncated test blocks that a
    # fixed size threshold like ">316" would misclassify as a bare
    # RDW stream).
    if first == len(data):                # BDW (includes itself + reserved)
        while i + 4 <= len(data):
            bl = struct.unpack('>H', data[i:i+2])[0]
            if bl < 8 or i + bl > len(data):
                raise ParseError('bad BDW length %d at offset %d' % (bl, i))
            j, end = i + 4, i + bl
            while j + 4 <= end:
                rl = struct.unpack('>H', data[j:j+2])[0]
                if rl < 4 or j + rl > end:
                    raise ParseError('bad RDW length %d at offset %d'
                                     % (rl, j))
                yield data[j:j+rl]
                j += rl
            i = end
    else:                                 # RDW-only stream
        while i + 4 <= len(data):
            rl = struct.unpack('>H', data[i:i+2])[0]
            if rl < 4 or i + rl > len(data):
                raise ParseError('bad RDW length %d at offset %d' % (rl, i))
            yield data[i:i+rl]
            i += rl


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
        ioff, iln, ion = _triplet(rec, IOF_AT)
        coff, cln, con = _triplet(rec, COF_AT)
        if ion == 0 or con == 0:          # absent section: skip, like SMFRPT30
            continue
        if ioff + iln > len(rec) or coff + cln > len(rec):
            raise ParseError('triplet points past record end')
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
        data = open(a.stagefile, 'rb').read()
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
