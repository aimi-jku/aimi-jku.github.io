import os
import re
import requests
import yaml
from pathlib import Path

# set API access environment variables
api_key = os.environ['API_KEY']
base_url = os.environ['BASE_URL']
members = os.environ.get('MEMBERS')

# helper function for getting author(s) from a publication
def get_authors(pub_json):
    authors = [f"{author['name'].get('lastName')}, {author['name'].get('firstName')}" for author in pub_json.get('contributors', [])]
    return ' and '.join(authors)

# helper function for getting title (and optionally subtitle) from a publication
def get_title(pub_json):
    title = pub_json['title']['value']
    subtitle = pub_json.get('subTitle', {}).get('value')
    if subtitle:
        return f'{title}: {subtitle}'
    return title

# helper function for getting the year
def get_year(pub_json):
    for status in pub_json.get('publicationStatuses', []):
        if status.get('current'):
            return status.get('publicationDate').get('year')
    return None

# helper function for generating key for entry, according to convention "authorYEARtitle"
def gen_key(record):
    authors = get_authors(record)
    last = re.sub(r'[^a-z]', '', authors.split(',')[0].lower()) if authors else 'anon'
    word = re.sub(r'[^a-z0-9]', '', get_title(record).lower())[:8]
    return f"{last}{get_year(record)}{word}"
    
# helper function for extracting fields for papers.bib from JSON
def get_fields(pub_json):
    # check type of research output (journal VS conference submission)
    submission_type = pub_json.get('typeDiscriminator')
    add_fields = {}
    if submission_type == 'ContributionToJournal': # journal entry
        add_fields = {
        'entry_type': 'article',
        'volume': pub_json.get('volume'),
        'pages': pub_json.get('pages'),
        'number': pub_json.get('journalNumber'),
        'journal': pub_json.get('journalAssociation', {}).get('title', {}).get('title')
        }
    elif submission_type == 'ContributionToBookAnthology':
        add_fields = {
            'entry_type': 'inproceedings',
            'booktitle': pub_json.get('hostPublicationTitle', {}).get('value')
        }
    else:
        add_fields = {
            'entry_type': 'misc'
        }

    return {
        'key': gen_key(pub_json),
        'author': get_authors(pub_json),
        'title': get_title(pub_json),
        'year': get_year(pub_json),
        **add_fields,
    }

# helper function for generating BIBTEX from values
def to_bibtex(fields):
    entry_type = fields.pop("entry_type")
    key = fields.pop("key")
    lines = [f"@{entry_type}{{{key},"]
    lines.append("  bibtex_show = {true},")
    lines.append("  selected = {true},")
    for name, value in fields.items():
        if value: # skiping empty fields
            lines.append(f"  {name} = {{{value}}},")
    lines.append("}")
    return "\n".join(lines)

###############################################################################
# fetch all group members
if members:
    members_yaml = yaml.safe_load(members)
else:
    stream = open('./_data/members.yml')
    members_yaml = yaml.safe_load(stream)

# set up request variables
REQUEST_HEADERS = {
    'api-key': api_key
}

all_uuids = set()
# request and filter dependents to ResearchOutputs
for member in members_yaml['groupmembers']:
    # fetch all dependents
    r = requests.get(f"{base_url}/persons/{member['pure_id']}/dependents", headers=REQUEST_HEADERS)
    output = r.json().get('items', [])

    # filter dependents to which ones are publications (=research outputs), get the UUIDs and deduplicate them
    all_uuids.update([i['uuid'] for i in output if i.get('systemName') == 'ResearchOutput'])

# fetch details for each publication across all members
PUB_REQUEST_BODY = {
    'uuids': list(all_uuids),
    'size': 500
}
r = requests.post(f'{base_url}/research-outputs/search', headers=REQUEST_HEADERS, json=PUB_REQUEST_BODY)

# parse paper details into bibtex entries and create papers.bib
bibtex_entries = [to_bibtex(get_fields(rec)) for rec in r.json().get("items", [])]
Path("_bibliography/papers.bib").write_text("\n\n".join(bibtex_entries), encoding="utf-8")