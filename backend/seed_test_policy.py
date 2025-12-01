"""
Wrapper script to run the Django management command `seed_test_policy`.

This allows calling:
  python backend\seed_test_policy.py --manager 3 --agent 101 --customer 456 --policy 901

It bootstraps Django and forwards arguments to the proper management command
implemented in users.management.commands.seed_test_policy.
"""

import os
import sys


def main():
    # Ensure project root is on sys.path (this file lives in <root>\backend)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    # Configure Django settings
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

    # Setup Django and run the management command
    import django

    django.setup()
    from django.core.management import execute_from_command_line

    argv = ["manage.py", "seed_test_policy", *sys.argv[1:]]
    execute_from_command_line(argv)


if __name__ == "__main__":
    main()
