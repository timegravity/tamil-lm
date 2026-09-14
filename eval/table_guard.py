"""Missing-result rule for every table renderer (ruling 2026-09-12): a result key that should exist but is absent fails the run
with an error, never a blank or "missing" cell next to a verdict. A cell may only be empty of a number when the producer wrote an
explicit reason string (for example "not run: architecture not in the pinned transformers"), and that string is what is rendered.

  need(d, "a", "b")            -> d["a"]["b"], raising MissingResult (with the path) when any step is absent or None
  first_of(d, ("x", "y"), what)-> the first present key, raising when none is present
  cell(v, what, fmt="{:.3f}")  -> formatted number, or a reason string passed through, raising on None
"""
class MissingResult(RuntimeError):
    pass

def need(d, *keys, what=""):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur and cur[k] is not None:
            cur = cur[k]
        else:
            raise MissingResult(f"missing result key {'/'.join(map(str, keys))}{(' in ' + what) if what else ''}")
    return cur

def first_of(d, keys, what=""):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            return d[k]
    raise MissingResult(f"none of the keys {list(keys)} present{(' in ' + what) if what else ''}")

def cell(v, what="", fmt=None):
    if v is None:
        raise MissingResult(f"missing value for {what}")
    if isinstance(v, str):
        return v   # an explicit reason written by the producer
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, float) and fmt:
        return fmt.format(v)
    return str(v)
