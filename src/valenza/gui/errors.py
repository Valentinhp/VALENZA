"""User-facing storage errors, with technical context kept out of the UI."""
import logging
import traceback

from valenza.persistence.database import DATABASE_ERRORS


def user_error(error):
    if isinstance(error, DATABASE_ERRORS):
        # Do not log SQL text, parameters, amounts or personal database paths.
        frames = traceback.extract_tb(error.__traceback__)
        locations = ', '.join(f'{frame.name}:{frame.lineno}' for frame in frames)
        logging.getLogger(__name__).error('Storage failure (%s), calls: %s', type(error).__name__, locations)
        return 'No se pudo guardar el cambio. Conserva lo capturado y vuelve a intentarlo.'
    return str(error)
