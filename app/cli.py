"""Commandes Flask personnalisees (init-db, seed, reset-db)."""
import click

from app.extensions import db


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Cree les tables de la base de donnees."""
        import app.models  # noqa: F401  (charge les modeles)

        db.create_all()
        click.echo("Tables creees.")

    @app.cli.command("seed")
    def seed():
        """Insere les permissions, les roles et le compte administrateur."""
        from app.services.seed import seed_all

        user, created = seed_all()
        if created:
            click.echo(f"Administrateur « {user.username} » cree.")
        else:
            click.echo(f"Administrateur « {user.username} » existe deja.")
        click.echo("Permissions et roles en place.")

    @app.cli.command("reset-db")
    @click.confirmation_option(prompt="Effacer TOUTES les donnees de la base ?")
    def reset_db():
        """Reinitialise la base : suppression, creation et seed."""
        import app.models  # noqa: F401

        db.drop_all()
        db.create_all()
        from app.services.seed import seed_all

        seed_all()
        click.echo("Base reinitialisee et donnees de reference creees.")
