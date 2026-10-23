"""The cloud half of retrieval: chunk -> embedding -> Tiger Cloud.

This package owns the write path to Postgres only. It may never import
``sloth_drawer.storage`` (RULES.md 3.1a): the *enforcement* of the cloud
boundary is that the code that writes to ``manual_chunks`` cannot even see
the device registry or the service log, so no identifier can reach the cloud
by an accident of convenience. The import-direction test checks this.
"""
