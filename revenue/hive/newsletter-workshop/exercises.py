#!/usr/bin/env python3
"""Prepare editable practice files and check the three workshop exercises."""
import argparse
import copy
import json
from pathlib import Path

from newsletter_workflow import HERE, InputError, load_json, validate, write_new

NEW_SUBJECT = 'Mossworks: what we learned at the bench'
NEW_QUOTE = 'Review the plain-text edition before exporting email drafts.'


def solutions(starter):
    first = copy.deepcopy(starter)
    first['issue'].update(slug='edition-02', subject=NEW_SUBJECT, planned_at='2026-09-22T09:00:00-05:00')
    second = copy.deepcopy(first)
    second['subscribers'][0]['status'] = 'unsubscribed'
    third = copy.deepcopy(second)
    third['sources'].append({'id':'workspace-review','title':'Original fictional review note','url':'https://example.test/mossworks/review','text':NEW_QUOTE})
    third['issue']['sections'].append({'heading':'Read the plain-text edition','source_id':'workspace-review','quote':NEW_QUOTE,'commentary':'Open newsletter.txt before handing an issue to another person. This is an editorial workflow suggestion, not an external performance claim.'})
    return [first, second, third]


def prepare(directory: Path):
    starter = load_json((HERE / 'example.json').read_bytes())
    answers = solutions(starter)
    directory.mkdir(parents=True)  # A fresh directory keeps previous exercises intact.
    for number in range(1, 4):
        before = starter if number == 1 else answers[number - 2]
        for name, value in ((f'exercise-{number}.json', before), (f'solution-{number}.json', answers[number - 1])):
            write_new(directory / name, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode())


def check(number: int, workspace: dict):
    checked = validate(workspace)
    errors = []
    issue = workspace['issue']
    if issue['slug'] != 'edition-02' or issue['subject'] != NEW_SUBJECT or issue['planned_at'] != '2026-09-22T09:00:00-05:00':
        errors.append('Set the edition-02 slug, requested subject, and September 22 datetime.')
    if number >= 2:
        eligible = {row['email'] for row in checked['eligible']}
        excluded = {row['email']:row['reason'] for row in checked['excluded']}
        if eligible != {'sam@example.test'} or excluded.get('alex@example.test') != 'unsubscribed' or excluded.get('jo@example.test') != 'unsubscribed':
            errors.append('Unsubscribe Alex, retain Jo\'s unsubscribe, and leave only Sam eligible.')
    if number >= 3:
        matching = [s for s in issue['sections'] if s['source_id'] == 'workspace-review' and s['quote'] == NEW_QUOTE]
        if len(issue['sections']) != 4 or len(matching) != 1:
            errors.append('Add the fourth workspace-review source-linked section using the requested exact quote.')
    if errors:
        raise InputError(' '.join(errors))
    return checked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    prep = commands.add_parser('prepare'); prep.add_argument('directory', type=Path)
    test = commands.add_parser('check'); test.add_argument('exercise', type=int, choices=(1,2,3)); test.add_argument('path',type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == 'prepare':
            prepare(args.directory)
            print(f'Created three editable exercises and three worked solutions in {args.directory}')
        else:
            result = check(args.exercise, load_json(args.path.read_bytes()))
            print(f'Exercise {args.exercise} complete: valid workspace, {len(result["eligible"])} eligible unsent drafts.')
    except (InputError, OSError) as exc:
        parser.exit(2, f'ERROR: {exc}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
