"""Restrict inherited process configuration before starting the web entry point."""

import os
import sys
from typing import NoReturn

from pydantic import SecretStr

from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    EmbeddingSettings,
    NormalizationSettings,
    SearchSettings,
    WebSettings,
    load_raw_database_settings,
)
from course_explorer.configuration import environment_value


def main() -> NoReturn:
    """Exec the web app with only its runtime settings and a file-free process environment.

    The required settings families are composed here through the shared automatic file
    sources and serialized to their aliases. A site whose web settings disable embedding features
    composes no embedding family, so its child needs no embedding hub artifact. The child carries
    the environment-only marker so the long-lived process reads no local file and forwards no
    admin/worker value.
    """
    web_settings = WebSettings()
    families = (
        load_raw_database_settings(),
        NormalizationSettings(),
        *((EmbeddingSettings(),) if web_settings.embeddings_enabled else ()),
        SearchSettings(),
        web_settings,
    )
    environment = {
        name: value for name, value in os.environ.items() if name in {"HOME", "PATH", "LANG"}
    }
    for settings in families:
        for name, field in type(settings).model_fields.items():
            alias = field.validation_alias
            if not isinstance(alias, str):
                continue
            value = getattr(settings, name)
            if isinstance(value, SecretStr):
                value = value.get_secret_value()
            environment[alias] = environment_value(value)
    environment[SETTINGS_SOURCE_MARKER] = ENVIRONMENT_ONLY_SETTINGS_SOURCE
    os.execve(
        sys.executable,
        [sys.executable, "-m", "course_explorer_web"],
        environment,
    )


if __name__ == "__main__":
    main()
