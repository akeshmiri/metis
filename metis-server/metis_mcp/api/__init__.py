"""
The HTTP API surface.

**Imported only when it is configured**, the same way `metis_mcp.write` is. N-8's
guarantee is that a read-only deployment is read-only *by construction* rather
than by routing, and a router that merely declines to expose a write path is a
routing decision — one refactor away from not being true.
"""
