"""`pickfit harvest`: collect leads (software worth reading) from many sources into runs/harvest.db.

A lead is a GitHub repository or a public web address; each source that names it adds a row, so a
tool seen in the MCP Registry, an awesome list and on HN is one lead with three sources. Leads that
already have a record or a pipeline candidate are marked `known`. `pickfit harvest feed` turns the
best new leads into submit_software rows that `pickfit watch` then reads, installs and verifies.

Sources and their terms: docs/research/harvest-sources.md.
"""
