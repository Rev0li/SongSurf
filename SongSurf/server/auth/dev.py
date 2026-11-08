"""
Mode développement : utilisateur local, sans porte (jamais en production).
"""

def dev_user() -> dict:
    return {'sub': 'dev', 'uid': 'dev-user-local', 'role': 'admin'}
