"""Exact user-approved V2 insertion-anchor revision; retained hashes stay intact."""
OLD = "if($('.controls'))$('.hero')?.after(r);return r}"
NEW = "if($('.controls'))$('#metrics')?.after(r);return r}"


def revise_anchor(source):
    if source.count(OLD) != 1:
        raise ValueError('Expected exactly one original V2 research anchor')
    return source.replace(OLD, NEW, 1)


def original_anchor(data):
    if data.count(NEW.encode()) != 1:
        raise ValueError('Approved V2 research anchor missing or altered')
    return data.replace(NEW.encode(), OLD.encode(), 1)
