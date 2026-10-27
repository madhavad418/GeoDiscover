"""Compare a Google/Grab provider extract (area_collection workbook) with a HERE baseline.

Outputs New / Update / Delete / Matched / Review lists in memory and as one Excel workbook. Nothing is stored:
provider rows stay out of the database, comparison runs and HERE delivery packages.
"""
import io
import json
import re
from collections import Counter
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font, PatternFill

from .area_collection import HEADERS
from .reference import chain_ids, chain_names
from .matching import GENERIC_TOKENS, _ratio, attribute_differences, compare, here_record, norm_name

PROVIDERS = {'Google': ('google', 'Google Places'), 'Grab': ('grab', 'GrabMaps')}
KINDS = {
    'new': 'New — in Google/Grab, not in HERE',
    'update': 'Update — matched HERE POI with different attributes',
    'delete': 'Delete candidates — closed per provider, or not found in Google/Grab',
    'matched': 'Matched — no change',
    'review': 'Needs review — identity unclear',
}
# Provider pins are often 50-250 m from the HERE pin: within this radius a single same-name HERE POI is the match.
SAME_NAME_RADIUS_M = 250.0
CLOSE_NAME = 0.75             # whole-name similarity a 'same name' match within 250 m needs
BRANCH_CLEAR_M = 60.0         # among several same-name HERE branches, the nearest wins if this close and 2x nearer
GENERIC_MIN_NAMES, GENERIC_SHARE = 4, 0.001  # a word in this many HERE names of the area is generic
LOCATION_UPDATE_M = 100.0     # provider geocodes are coarser than HERE; smaller offsets are not proposed
STREET_WORDS = [(r'\bstreet\b', 'St'), (r'\bavenue\b', 'Ave'), (r'\broad\b', 'Rd'), (r'\bboulevard\b', 'Blvd'),
                (r'\bdrive\b', 'Dr'), (r'^jl\.?\s*', 'Jalan '), (r'^gg\.?\s*', 'Gang ')]
UPDATE_FIELDS = ('name', 'category', 'phone', 'website', 'opening_hours', 'address', 'location')
EXTRA = {
    'new': ['comparison_id', 'sources', 'source_place_ids', 'reason'],
    'update': ['here_placeid', 'changed_fields', *[f'{p}_{f}' for f in UPDATE_FIELDS for p in ('here', 'proposed')],
               'sources', 'source_place_ids', 'distance_m', 'match_level', 'reason'],
    'delete': ['here_placeid', 'delete_basis', 'reason'],
    'matched': ['here_placeid', 'sources', 'source_place_ids', 'distance_m', 'match_level'],
    'review': ['comparison_id', 'sources', 'source_place_ids', 'candidate_here_placeids', 'candidate_here_names', 'reason'],
}


def read_extract(content):
    """Rows per provider from the Google and Grab sheets of a provider extract workbook."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError('Upload the provider extract .xlsx produced by "Collect POIs (APIs)".') from exc
    out = {}
    for sheet in PROVIDERS:
        if sheet not in wb.sheetnames:
            continue
        it = wb[sheet].iter_rows(values_only=True)
        header = [str(h or '').strip() for h in next(it, [])]
        if 'placeid' not in header or 'displaylatitude' not in header:
            raise ValueError(f'Sheet {sheet} does not have the HERE baseline columns.')
        out[sheet] = [dict(zip(header, ('' if v is None else v for v in values))) for values in it if any(v not in (None, '') for v in values)]
    wb.close()
    if not out:
        raise ValueError('The workbook has no Google or Grab sheet.')
    return out


def street(value):
    """Provider street names in HERE's style (St, Ave, Jalan) so abbreviations are not reported as address changes."""
    text = str(value or '').strip()
    for pattern, short in STREET_WORDS:
        text = re.sub(pattern, short, text, flags=re.I)
    return re.sub(r'\s+', ' ', text).strip() or None


def overlaps(here_rows, extract, margin_deg=0.01, share=0.5):
    """True when at least half the extract's POIs fall in the HERE baseline's bounding box (plus ~1 km)."""
    if not here_rows:
        return True
    lats, lons = [float(r['latitude']) for r in here_rows], [float(r['longitude']) for r in here_rows]
    s, n, w, e = min(lats) - margin_deg, max(lats) + margin_deg, min(lons) - margin_deg, max(lons) + margin_deg
    points = []
    for rows in extract.values():
        for r in rows:
            try:
                points.append((float(r['displaylatitude']), float(r['displaylongitude'])))
            except (TypeError, ValueError):
                continue
    return not points or sum(s <= lat <= n and w <= lon <= e for lat, lon in points) >= share * len(points)


def observations(extract):
    obs, rows = [], {}
    for sheet, provider_rows in extract.items():
        provider, name = PROVIDERS[sheet]
        for r in provider_rows:
            try:
                lat, lon = float(r['displaylatitude']), float(r['displaylongitude'])
            except (TypeError, ValueError):
                continue
            oid = len(obs) + 1
            rows[oid] = (sheet, r)
            status = {'ACTIVE': 'open', 'CLOSED': 'permanently_closed'}.get(str(r.get('status') or '').upper(), 'unknown')
            obs.append({
                'id': oid, 'batch_id': provider, 'source_type': 'map_provider', 'source_name': name,
                'source_record_id': str(r['placeid']), 'name': str(r.get('name1') or ''), 'alt_names': [],
                # Provider categories are mapped heuristically, so they never drive identity or category updates.
                'category_code': None, 'category_name': None, 'latitude': lat, 'longitude': lon,
                'phones': [p for f in ('phone_numbers', 'mobile_numbers') for p in str(r.get(f) or '').split(',') if p],
                'website': str(r.get('webaddress') or '') or None, 'social_url': None,
                'house_number': str(r.get('hno') or '') or None, 'street_name': street(r.get('streetname')),
                'unit': None, 'postal_code': str(r.get('postalcode') or '') or None, 'business_status': status,
                'opening_hours': str(r.get('opening_hours') or '') or None, 'address': str(r.get('upaddress') or '') or None,
                'here_place_id': None, 'observed_on': None, 'source_url': None,
            })
    return obs, rows


def _merged(members, rows):
    """HERE-column row for a discovered POI: Google values first (richer attributes), blanks filled from Grab."""
    ranked = sorted(members, key=lambda o: (o['batch_id'] != 'google', o['id']))
    out = {h: '' for h in HEADERS}
    for o in ranked:
        for h, v in rows[o['id']][1].items():
            if h in out and out[h] in ('', None) and v not in ('', None):
                out[h] = v
    out['placeid'] = ''
    out['suppliers'] = '[' + ', '.join(dict.fromkeys(rows[o['id']][1].get('suppliers', '').strip('[]') for o in ranked)) + ']'
    return out


def _here_row(here):
    raw = dict(here['raw'] or {})
    return {h: raw.get(h, '') for h in HEADERS} | {'placeid': here['place_id']}


def _value(v):
    if isinstance(v, list):
        return ', '.join(_value(x.get('value') if isinstance(x, dict) else x) for x in v)
    return '' if v is None else str(v)


def generic_words(names, country):
    """Words common to many names in this area (Trading, Grocery, Clinic...): they don't identify a business.

    Brand words from the HERE chain lists (Indomaret, BRI, Mandiri) stay identifying even when common.
    """
    df = Counter(w for n in names for w in set(norm_name(n).split()))
    floor = max(GENERIC_MIN_NAMES, GENERIC_SHARE * len(names))
    brands = {w for c in [*chain_names(country), *chain_ids(country)] for w in norm_name(c).split()} - GENERIC_TOKENS
    return ({w for w, n in df.items() if n >= floor} - brands) | GENERIC_TOKENS


def _shares_identity(m, c, here_names, generic):
    if c['M3'] or c['M5']:
        return True
    words = {w for n in m['names'] for w in n.split()} - generic
    return bool(words & ({w for w in here_names[c['here_id']].split()} - generic))


def _close_name(m, c, here_names):
    """Whole-name closeness: stops a one-word HERE name ('mandiri') matching any longer name that contains it."""
    here = here_names[c['here_id']]
    return any(_ratio(n, here) >= CLOSE_NAME or (min(len(n), len(here)) >= 0.6 * max(len(n), len(here)) and (n in here or here in n))
               for n in m['names'])


def _nearest_clear(same):
    """Nearest same-name HERE POI when it is clearly the closest of several (chain branches)."""
    same = sorted(same, key=lambda c: c['distance_m'])
    if same and same[0]['distance_m'] <= BRANCH_CLEAR_M and (len(same) == 1 or same[0]['distance_m'] * 2 < same[1]['distance_m']):
        return same[0]
    return None


def _resolve(output, here_rows, country):
    """Provider-specific final call on each discovered business: [outcome, master, here_id, match, diffs, reason, cands, merged].

    The base engine needs a unit-level signal or a 50 m pin to confirm identity. Provider pins are coarser, so a
    single same-name HERE POI within 250 m is accepted as the match, the clearly-nearest branch wins among several,
    and lookalikes that share only words common in the area become New.
    """
    here_by_id = {r['id']: r for r in here_rows}
    here_names = {r['id']: norm_name(r.get('name') or '') for r in here_rows}
    generic = generic_words([r.get('name') or '' for r in here_rows], country)
    masters = {m['master_key']: m for m in output['masters']}
    decided = []
    for res in output['results']:
        if not res['master_key']:
            continue
        m, exp = masters[res['master_key']], res['explanation']
        reason, cands = ' '.join(exp['reasons']), exp['candidates']
        if res['outcome'] in ('potential_new', 'potential_update', 'no_change', 'potential_delete'):
            decided.append([res['outcome'], m, res['here_id'], exp['match'], exp['changed_fields'], reason, cands, []])
            continue
        if reason.startswith('Linked sources disagree'):
            decided.append(['fallout_review', m, None, None, [], reason, cands, []])
            continue
        same = [c for c in cands if c['M1'] and c['distance_m'] <= SAME_NAME_RADIUS_M and _close_name(m, c, here_names)]
        others_signal = lambda pick: any((c['M3'] or c['M5']) for c in cands if c is not pick)  # noqa: E731
        pick = same[0] if len(same) == 1 else _nearest_clear(same)
        if pick and not others_signal(pick):
            level = 'same name within 250 m' if len(same) == 1 else 'nearest same-name branch'
            decided.append(['matched', m, pick['here_id'], pick | {'level': level}, None, f"{level} ({pick['distance_m']} m).", cands, []])
        elif not same and not any(_shares_identity(m, c, here_names, generic) for c in cands):
            decided.append(['potential_new', m, None, None, [], 'Nearby HERE POIs share only common words '
                            f"({', '.join(c['here_name'] for c in cands[:2])}); confirm it is not listed under another name.", cands, []])
        else:
            decided.append(['fallout_review', m, None, None, [], reason, cands, []])
    # A HERE POI is the match for one business. A same-name claimant is the other provider's copy of it: merge.
    claimed = {}
    for d in decided:
        if d[0] in ('potential_update', 'no_change', 'potential_delete', 'matched') and d[2] is not None:
            first = claimed.get(d[2])
            if first is None:
                claimed[d[2]] = d
            elif any(c['here_id'] == d[2] and c['M1'] for c in d[6]) or (d[3] or {}).get('M1'):
                first[7].append(d[1])
                d[0] = 'merged'
            else:
                d[:6] = ['fallout_review', d[1], None, None, [], 'Another discovered business also matches the same HERE POI.']
    here_recs = {}
    for d in decided:
        if d[0] == 'matched':
            here = here_recs.setdefault(d[2], here_record(here_by_id[d[2]], country))
            d[4] = attribute_differences(d[1], here)
            d[0] = 'potential_update'
        if d[0] in ('potential_update', 'no_change'):
            d[4] = [x for x in d[4] or [] if x['field'] != 'location' or x.get('distance_m', 0) > LOCATION_UPDATE_M]
            d[0] = 'potential_update' if d[4] else 'no_change'
    return [d for d in decided if d[0] != 'merged'], set(claimed)


def _address(here):
    raw = here.get('raw') or {}
    street_line = ' '.join(x for x in (str(raw.get('streetname') or ''), str(raw.get('hno') or '')) if x)
    return raw.get('upaddress') or ', '.join(x for x in (street_line, str(raw.get('postalcode') or '')) if x)


def run(here_rows, extract, country, dataset_id):
    obs, rows = observations(extract)
    output = compare(here_rows, obs, country, dataset_id, ())
    decided, matched = _resolve(output, here_rows, country)
    here_by_id = {r['id']: r for r in here_rows}
    referenced = set()
    lists = {k: [] for k in KINDS}
    for outcome, m, here_id, match, diffs, reason, cands, merged in decided:
        members = m['members'] + [o for x in merged for o in x['members']]
        sources = ', '.join(sorted({o['source_name'] for o in members}))
        ids = ', '.join(f"{rows[o['id']][0]}:{rows[o['id']][1]['placeid']}" for o in members)
        here = here_by_id.get(here_id)
        lat, lon = m['lat'], m['lon']
        if outcome == 'potential_new':
            kind = 'new'
            row = _merged(m['members'], rows) | {'comparison_id': m['jsan_id'], 'sources': sources, 'source_place_ids': ids, 'reason': reason}
        elif outcome in ('potential_update', 'no_change'):
            kind = 'matched' if outcome == 'no_change' else 'update'
            lat, lon = here['latitude'], here['longitude']
            row = _here_row(here) | {'here_placeid': str(here['place_id']), 'sources': sources, 'source_place_ids': ids,
                                     'distance_m': match['distance_m'], 'match_level': match['level']}
            if kind == 'update':
                row['changed_fields'] = ', '.join(d['field'] for d in diffs)
                row['reason'] = f"Matched ({match['level']}, {match['distance_m']} m). Differences: {row['changed_fields']}."
                for d in diffs:
                    row[f"here_{d['field']}"] = _address(here) if d['field'] == 'address' else _value(d.get('here'))
                    row[f"proposed_{d['field']}"] = _value(d.get('observed'))
        elif outcome == 'potential_delete':
            kind = 'delete'
            lat, lon = here['latitude'], here['longitude']
            row = _here_row(here) | {'here_placeid': str(here['place_id']), 'delete_basis': 'Closed per provider', 'reason': reason}
        else:
            kind = 'review'
            referenced.update(c['here_id'] for c in cands)
            row = _merged(m['members'], rows) | {'comparison_id': m['jsan_id'], 'sources': sources, 'source_place_ids': ids,
                                                 'candidate_here_placeids': ', '.join(c['place_id'] for c in cands),
                                                 'candidate_here_names': ', '.join(c['here_name'] for c in cands), 'reason': reason}
        row['_lat'], row['_lon'] = float(lat), float(lon)
        lists[kind].append(row)
    for h in here_rows:
        if h['id'] not in matched and h['id'] not in referenced:
            lists['delete'].append(_here_row(h) | {
                'here_placeid': str(h['place_id']), 'delete_basis': 'Not found in Google or Grab',
                'reason': 'Neither provider search returned this POI. Absence alone is not proof of closure (D7): verify before deleting.',
                '_lat': float(h['latitude']), '_lon': float(h['longitude'])})
    stats = {'here_records': len(here_rows), 'provider_records': {s: len(r) for s, r in extract.items()},
             'linked_businesses': len(output['masters']), 'multi_source': output['stats']['multi_source_masters'],
             'counts': {k: len(v) for k, v in lists.items()},
             'delete_breakdown': {b: sum(1 for r in lists['delete'] if r['delete_basis'] == b)
                                  for b in ('Closed per provider', 'Not found in Google or Grab')}}
    return lists, stats


def workbook(lists, stats, meta):
    wb = Workbook()
    ws = wb.active
    ws.title = 'Summary'
    ws.append(['HERE vs Google/Grab comparison', meta.get('aoi', '')])
    ws.append(['HERE dataset', meta.get('dataset', '')])
    ws.append(['Provider extract', meta.get('extract', '')])
    ws.append(['Compared at', datetime.now(timezone.utc).isoformat(timespec='seconds')])
    ws.append(['HERE POIs', stats['here_records']])
    for s, n in stats['provider_records'].items():
        ws.append([f'{s} POIs', n])
    ws.append(['Linked businesses (Google+Grab deduplicated)', stats['linked_businesses']])
    ws.append([])
    for k, label in KINDS.items():
        ws.append([label, stats['counts'][k]])
    for b, n in stats['delete_breakdown'].items():
        ws.append([f'  Delete: {b}', n])
    ws.append([])
    ws.append(['Notes', 'Provider-derived candidates for review, not an approved HERE delivery. "Not found" means neither '
                        'provider search returned the POI; absence alone is not proof of closure (Delete Framework D7).'])
    ws.column_dimensions['A'].width = 62
    ws.column_dimensions['B'].width = 40
    for kind, label in KINDS.items():
        sheet = wb.create_sheet(kind.capitalize())
        columns = HEADERS + EXTRA[kind] + ['map_latitude', 'map_longitude']  # where the row is plotted on the map
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='005B96')
        for r in lists[kind]:
            r = r | {'map_latitude': r.get('_lat', ''), 'map_longitude': r.get('_lon', '')}
            sheet.append([ILLEGAL_CHARACTERS_RE.sub('', v)[:32767] if isinstance(v, str) else v for v in (r.get(c, '') for c in columns)])
            for cell in sheet[sheet.max_row]:
                if isinstance(cell.value, str):
                    cell.data_type = 's'  # never evaluate provider text as a formula
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = 20
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def public_row(row):
    return json.loads(json.dumps(row, default=str))


SHEETS = {k.capitalize(): k for k in KINDS}


def read_comparison_workbook(content):
    """(meta, lists, stats) from a workbook written by workbook(): Summary plus one sheet per list."""
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError('Upload a comparison workbook downloaded from HERE vs Google/Grab.') from exc
    if 'Summary' not in wb.sheetnames or not set(SHEETS) <= set(wb.sheetnames):
        raise ValueError('The workbook needs Summary, New, Update, Delete, Matched and Review sheets.')
    summary = {str(r[0]).strip(): r[1] for r in wb['Summary'].iter_rows(values_only=True) if r and r[0]}
    lists = {}
    for sheet, kind in SHEETS.items():
        it = wb[sheet].iter_rows(values_only=True)
        header = [str(h or '').strip() for h in next(it, [])]
        items = []
        for values in it:
            if not any(v not in (None, '') for v in values):
                continue
            row = {h: ('' if v is None else v) for h, v in zip(header, values) if h}
            row['_lat'], row['_lon'] = None, None
            for lat, lon in (('map_latitude', 'map_longitude'), ('displaylatitude', 'displaylongitude')):
                try:
                    row['_lat'], row['_lon'] = float(row.pop(lat, None) if lat.startswith('map') else row.get(lat)),                         float(row.pop(lon, None) if lon.startswith('map') else row.get(lon))
                    break
                except (TypeError, ValueError):
                    continue
            items.append(row)
        lists[kind] = items
    wb.close()
    providers = {k[:-5]: v for k, v in summary.items() if k.endswith(' POIs') and k != 'HERE POIs'}
    stats = {'here_records': summary.get('HERE POIs') or 0, 'provider_records': providers,
             'linked_businesses': summary.get('Linked businesses (Google+Grab deduplicated)') or 0,
             'counts': {k: len(v) for k, v in lists.items()},
             'delete_breakdown': {b: sum(1 for r in lists['delete'] if r.get('delete_basis') == b)
                                  for b in ('Closed per provider', 'Not found in Google or Grab')}}
    meta = {'aoi': str(summary.get('HERE vs Google/Grab comparison') or ''), 'dataset': str(summary.get('HERE dataset') or ''),
            'extract': str(summary.get('Provider extract') or ''), 'compared_at': str(summary.get('Compared at') or '')}
    return meta, lists, stats


def save(db, *, aoi, dataset, lists, stats, extract, source_filename='', user=None):
    """Store one comparison and all its rows; returns the ProviderComparison."""
    from sqlalchemy import insert
    from ..models.provider import ProviderComparison, ProviderComparisonRow
    comparison = ProviderComparison(aoi=aoi, dataset_id=dataset.id if dataset else None,
                                    dataset_filename=dataset.filename if dataset else '', extract_filename=extract or '',
                                    source_filename=source_filename, stats=public_row(stats), created_by=user.id if user else None)
    db.add(comparison)
    db.flush()
    rows = []
    for kind, items in lists.items():
        for i, r in enumerate(items):
            data = public_row({k: v for k, v in r.items() if not k.startswith('_') and v not in ('', None)})
            search = ' '.join(str(r.get(c) or '') for c in ('name1', 'here_placeid', 'placeid', 'upaddress', 'primarycategorynm',
                                                            'source_place_ids', 'sources')).lower()
            rows.append({'comparison_id': comparison.id, 'kind': kind, 'position': i, 'name': str(r.get('name1') or '')[:500],
                         'here_placeid': str(r.get('here_placeid') or '')[:120], 'delete_basis': str(r.get('delete_basis') or '')[:60],
                         'search_text': search[:2000], 'latitude': r.get('_lat'), 'longitude': r.get('_lon'), 'data': data})
    for start in range(0, len(rows), 2000):
        db.execute(insert(ProviderComparisonRow), rows[start:start + 2000])
    return comparison
