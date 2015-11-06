#!/usr/bin/env python

import re
import os
import sys
try:
    import json
except ImportError:
    import simplejson as json
import socket
import requests
import ConfigParser

parser = ConfigParser.ConfigParser()
parser.read([os.path.join(sys.path[0], 'wiki-irccat.conf')])
config = dict(parser.items('wiki-irccat'))

url = config['url']
short_url = config.get('short_url', url)
revid_file = config.get('revid_file', os.path.join(sys.path[0], 'revid.txt'))
namespaces = config.get('namespaces', '0,1').split(',')
irccat = config.get('irccat', 'irccat')
irccat_port = int(config.get('irccat_port', '12345'))
channel = config.get('channel')

def ellipsize(s, maxlen=80):
    if len(s) > maxlen:
        # + 1 in case it cuts perfectly at a word boundary
        end = s.rfind(' ', 0, maxlen - len('...') + 1)
        s = s[:end]

        # Fix letters that look bad before an ellipsis
        if s[-1] in (' .,;:-+=&?!'):
            s += ' ' # Yes, I know this breaks MAXLEN

        s += '...'
    return s

def format_comment(comment):
    # Format section like the mediawiki history page
    comment = re.sub(r'(?:/\* *(.*?) *\*/) *(.*) *', ur'\2 \u2192\1', unicode(comment))
    return ellipsize(comment.strip(), 40)

def read_revid_file(revid_file):
    try:
        with open(revid_file) as f:
            return int(f.read())
    except (IOError, ValueError):
        return None

def write_revid_file(revid_file, max_id):
    with open(revid_file, 'w') as f:
        f.write(str(max_id))

def load_changes():
    # Get a list of namespaces with api.php?action=query&meta=siteinfo&siprop=namespaces
    params = {
        'action':       'query',
        'prop'  :       'revisions',
        'generator':    'recentchanges',
        'grcnamespace': '|'.join(namespaces),
        'grcshow':      '!bot|!minor',
        'grclimit':     50,
        'format':       'json',
    }
    resp = requests.get(url + 'api.php', params=params, verify=False)
    data = json.loads(resp.text)
    return data['query']['pages']

def process_changes(changes, max_id):
    msgs = []

    for page_no, page in changes.items():
        if int(page_no) < 0:
            # missing page
            continue

        rev = page['revisions'][0]
        rev_id = int(rev['revid'])

        if rev.has_key('minor'):
            # grcshow doesn't seem to work
            continue

        if rev_id <= last_id:
            # should already have been shown
            continue

        max_id = max(rev_id, max_id)

        title = page['title']
        user = rev['user']
        comment = rev['comment']

        msg = []
        msg.append('%s changed %s' % (user, title))
        if comment:
            msg.append('(%s)' % format_comment(comment))

        msg.append('%s?diff=%s' % (short_url, rev_id))
        msgs.append(' '.join(msg))

    return msgs, max_id

def send_msgs(msgs):
    if not msgs:
        return

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((irccat, irccat_port))

    if channel:
        msgs[0] = channel + ' ' + msgs[0]

    for msg in msgs:
        s.send(unicode(msg + '\r\n').encode('utf-8'))

    s.close()


if __name__ == '__main__':

    last_id = read_revid_file(revid_file)
    changes = load_changes()

    msgs, max_id = process_changes(changes, last_id)

    if max_id > last_id:
        write_revid_file(revid_file, max_id)

    # after writing, to err on the side of not sending updates
    if last_id is not None:
        send_msgs(msgs)

