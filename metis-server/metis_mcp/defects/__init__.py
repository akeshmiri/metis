"""Reading a failure before filing it.

`classify` is the whole module family for now, and deliberately: filing already
worked — `publishing/tracker_write.JiraWriter` was ported from the same practice
and checks for an existing issue before it creates one. What was missing was the
step in front of it, which is pure and testable and needs no network.
"""
