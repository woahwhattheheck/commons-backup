# SPDX-License-Identifier: Apache-2.0
"""Copy retained observation edges, then borrow the certified own-unit pair.

Equivalent to deepcopy(obs) followed by replacing farms[player] and private
for the native plain-dict/list observation graph. Unlike a shallow copy this
keeps every retained mutable object detached. A shared memo preserves aliases
and cycles, including retained aliases into the otherwise discarded subgraphs.
The selected pair is intentionally borrowed, exactly as by the predecessor.
No module cache, cross-call state, policy choice or deadline is introduced.
"""
from copy import deepcopy


def selected_unit_snapshot(obs, player, pair):
    """Return a fresh snapshot; unusual root containers use the old operation.

    Native observations have string keys and JSON-shaped descendants. Standard
    deepcopy is retained for descendants, including Struct-like dictionaries.
    As with any copy-elision optimization, side effects of custom __deepcopy__
    methods reachable ONLY from discarded input edges are outside this native
    data contract. No such objects occur in the authenticated runtime fixtures.
    """
    index = int(player)
    if (type(obs) is not dict or type(obs.get('farms')) is not list
            or type(pair) not in (tuple, list) or len(pair) != 2
            or not -len(obs['farms']) <= index < len(obs['farms'])):
        post = deepcopy(obs)
        post['farms'][index], post['private'] = pair
        return post

    farms = obs['farms']
    index %= len(farms)
    post, copied_farms = {}, []
    # Register only the containers that survive the old root-edge replacement.
    # Do NOT map the discarded own farm/private to the new pair: other retained
    # aliases to those old objects must still receive ordinary detached copies.
    memo = {id(obs): post, id(farms): copied_farms}
    for key, value in obs.items():
        copied_key = deepcopy(key, memo)
        if key == 'private':
            post[copied_key] = pair[1]
        elif key == 'farms':
            for offset, farm in enumerate(farms):
                copied_farms.append(pair[0] if offset == index
                                    else deepcopy(farm, memo))
            post[copied_key] = copied_farms
        else:
            post[copied_key] = deepcopy(value, memo)
    # The predecessor adds private even if the input did not contain it.
    if 'private' not in obs:
        post['private'] = pair[1]
    return post
