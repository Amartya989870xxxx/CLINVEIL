"""Security boundary helpers: secret handling, path containment, PII-free errors/logs.

Rule of the package: nothing in here (or anywhere) may format raw record content,
file names or the secret into stdout, stderr, logs, reports or exception messages.
"""
