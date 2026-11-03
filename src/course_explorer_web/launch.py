"""Restrict inherited process configuration before starting the web entry point."""

import os
import sys
from pathlib import Path
from typing import NoReturn

from pydantic import SecretStr

import course_explorer
from course_explorer.config import (
    ENVIRONMENT_ONLY_SETTINGS_SOURCE,
    SETTINGS_SOURCE_MARKER,
    AdmissionSettings,
    FeedbackIntakeSettings,
    FeedbackSettings,
    NormalizationSettings,
    SearchSettings,
    WebSettings,
    embedding_configuration_for_site,
    load_raw_database_settings,
)
from course_explorer.configuration import environment_value


def main() -> NoReturn:
    """Exec the web app with only its runtime settings and a settings-file-free process environment.

    The required settings families are composed here through the shared automatic file
    sources and serialized to their aliases. The families are the raw database,
    normalization, search, web and admission settings, the feedback application and intake
    settings, plus the embedding runtime settings when the web settings serve the embedding
    features. The child imports both packages from this package's own source directory, so a
    copied checkout supervises its own package rather than the installed one. The child carries
    the environment-only marker so the long-lived process reopens no local settings file and
    forwards no admin or worker value. A feedback request may read the feedback definition file
    through its owning service.
    """
    web_settings = WebSettings()
    embedding = embedding_configuration_for_site(web_settings)
    families = (
        load_raw_database_settings(),
        NormalizationSettings(),
        *((embedding,) if embedding is not None else ()),
        SearchSettings(),
        web_settings,
        AdmissionSettings(),
        FeedbackSettings(),
        FeedbackIntakeSettings(),
    )
    environment = {
        name: value for name, value in os.environ.items() if name in {"HOME", "PATH", "LANG"}
    }
    # The source directory comes from the package this process loaded, so the child reads the
    # package this launcher runs.
    environment["PYTHONPATH"] = str(Path(course_explorer.__file__).resolve().parent.parent)
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
    # glibc reads MALLOC_ARENA_MAX at process start, and the router and forked workers inherit this
    # supervisor environment, so the setting enters here rather than in the unit file.
    environment["MALLOC_ARENA_MAX"] = str(web_settings.web_malloc_arena_max)
    os.execve(
        sys.executable,
        [sys.executable, "-m", "course_explorer_web"],
        environment,
    )


if __name__ == "__main__":
    main()
