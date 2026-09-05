"""Talking to Indico's Editing module as an editor, from the editor's own machine.

JACoW's Indico already runs an editing service (``OpenReferee JACoW``) in the one
service slot an event has, so this agent cannot be hooked in there. The route
that is open is the one an editor already has: their own credential against the
editing REST API. Pull the papers down, work offline, push the result back.

Three modules:

* :mod:`~src.indico_client.tags` — JACoW's editorial tag vocabulary, and which
  of the agent's checks map onto which code. The mapping is the point: editors
  already classify every correction they make, by hand, from this list.
* :mod:`~src.indico_client.models` — the shapes the API actually returns,
  pinned against real payloads from a real conference.
* :mod:`~src.indico_client.client` — the HTTP client.
"""
