"""
Aplica migraciones Alembic en producción.

Uso:
    python -m app.scripts.run_migrations

Equivalente a:
    alembic upgrade head
"""

from alembic import command
from alembic.config import Config


def main() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    print("Alembic: upgrade head completado")


if __name__ == "__main__":
    main()
