"""Commandes Flask personnalisees (init-db, seed, reset-db)."""
from datetime import datetime

import click

from app.extensions import db


def _write_backup_log(status, details):
    import os

    from app.services.backup import backup_dir

    path = os.path.join(backup_dir(), "automatic_backup.log")
    with open(path, "a", encoding="utf-8") as log_file:
        log_file.write(f"{datetime.now().astimezone().isoformat()} [{status}] {details}\n")


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

    @app.cli.command("backup-db")
    @click.option("--label", default="auto", show_default=True)
    def backup_db(label):
        """Cree une sauvegarde SQLite verifiee et applique la retention."""
        from app.services.backup import create_backup, purge_old_backups

        try:
            backup = create_backup(label=label)
            if not backup["valid"]:
                _write_backup_log("ERREUR", f"Intégrité invalide : {backup['filename']}")
                raise click.ClickException(
                    f"La sauvegarde {backup['filename']} a echoue au controle d'integrite."
                )
            removed = purge_old_backups()
        except (OSError, RuntimeError) as exc:
            _write_backup_log("ERREUR", str(exc))
            raise click.ClickException(f"Sauvegarde impossible : {exc}") from exc

        _write_backup_log(
            "OK",
            f"{backup['filename']} ({backup['size']} octets); {removed} ancienne(s) copie(s) supprimée(s)",
        )
        click.echo(
            f"Sauvegarde verifiee : {backup['filename']} "
            f"({backup['size']} octets, SHA-256 {backup['sha256']})."
        )
        click.echo(f"Anciennes sauvegardes supprimees par retention : {removed}.")

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
