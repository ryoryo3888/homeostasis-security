"""Reverse only Rio's approved full-width V2 turn-card layout addition."""
STYLE = '''<!-- HOMEOSTASIS_V2_TURN_WIDTH -->
<style id="v2TurnWidth">
#homeostasisResearchLayer .rn-turns{display:flex;flex-wrap:wrap}
#homeostasisResearchLayer .rn-turns::before{flex:0 0 100%}
#homeostasisResearchLayer .rn-turns>.rn-turn{flex:1 1 205px}
</style>
'''


def add_turn_width(html):
    if html.count('</head>') != 1 or 'HOMEOSTASIS_V2_TURN_WIDTH' in html:
        raise ValueError('Missing head boundary or duplicate turn-width revision')
    return html.replace('</head>', STYLE + '</head>', 1)


def original_turn_width(data):
    if data.count(STYLE.encode()) != 1:
        raise ValueError('Approved V2 turn-width revision missing or altered')
    return data.replace(STYLE.encode(), b'', 1)
