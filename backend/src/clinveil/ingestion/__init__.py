"""Ingestion: safe, deterministic discovery of input files and byte-level decoding.

Every input file is untrusted. Discovery never follows a symlink out of the input
root, never reads a file above the size cap, and yields files in a fixed order.
Phase 1 adds content sniffing (do not trust extensions: JSON behind ``.csv``) and
base64 attachment extraction.
"""
