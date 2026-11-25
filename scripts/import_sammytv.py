"""Import one URL per line as pending videos. Run on the CXMS Heroku app.

python scripts/import_sammytv.py --file scripts/data/sammytv_links_2026-11-25.txt
Add --dry-run to check metadata and print category suggestions without writing.
No local credential copying or password arguments are needed on Heroku.
"""
import argparse
from collections import Counter
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.sammytv.auth import AccessDenied
from services.sammytv.bulk_import import import_links, normalize_links, select_parent
from services.sammytv.repository import CatalogueRepository, CatalogueUnavailable, ModerationDenied


def terminal_text(value):
    # Provider titles are untrusted, including terminal escape/control sequences.
    import unicodedata
    return ''.join(c if not unicodedata.category(c).startswith('C') else ' ' for c in value)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Import YouTube links into the SammyTV parent review queue. Never approves videos.')
    parser.add_argument('--file', required=True, type=Path, help='UTF-8 file with one HTTPS YouTube link per line')
    parser.add_argument('--parent-member-id', help='Existing SammyTV parent UUID; optional if exactly one active parent exists')
    parser.add_argument('--dry-run', action='store_true', help='Check metadata and suggest categories without database writes')
    args = parser.parse_args(argv)
    try:
        if args.file.stat().st_size > 524288:
            raise ValueError('Use a link file smaller than 512 KB.')
        entries, invalid, duplicates = normalize_links(args.file.read_text(encoding='utf-8').splitlines())
        print(f'{len(entries)} unique videos; {duplicates} duplicate links; {len(invalid)} invalid links.', flush=True)
        for error in invalid:
            print(f'Line {error["line"]}: {error["error"]}', flush=True)
        if not entries:
            return 1
        repo = CatalogueRepository()
        parent = select_parent(repo, args.parent_member_id)
        print('Checking only; no database writes.' if args.dry_run else 'Adding pending videos; existing approvals and categories are preserved.', flush=True)

        def show(result):
            text = f'{result["outcome"].upper()} {result["video_id"]}'
            if result.get('title'):
                text += ' · ' + terminal_text(result['title'])
            if result.get('suggestions'):
                text += ' · Suggested categories: ' + ', '.join(terminal_text(s) for s in result['suggestions'])
            print(text, flush=True)
            if result.get('error'):
                print('  ' + result['error'], flush=True)
            for reason in result.get('blocked', []):
                print('  Not eligible for approval: ' + reason, flush=True)

        results = import_links(repo, parent, entries, dry_run=args.dry_run, on_result=show)
        counts = Counter(result['outcome'] for result in results)
        print('Finished: ' + ', '.join(f'{count} {outcome}' for outcome, count in sorted(counts.items())), flush=True)
        print('Review imported videos at https://www.cxms.fr/sammytv/admin', flush=True)
        return 1 if invalid or counts['failed'] else 0
    except (OSError, UnicodeError):
        print('Could not read the UTF-8 link file.', file=sys.stderr)
    except (ValueError, AccessDenied) as exc:
        print(str(exc), file=sys.stderr)
    except ModerationDenied:
        print('Parent access changed. The batch stopped; completed imports remain saved.', file=sys.stderr)
    except CatalogueUnavailable:
        print('Could not access the SammyTV database. Run on the CXMS app with its existing server configuration.', file=sys.stderr)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
