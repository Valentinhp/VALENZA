"""Interfaz de escritorio de demostración para SGCCC.

The application module is loaded lazily so ``python -m sgccc.gui.app`` does
not import it once through the package and then a second time for execution.
"""

from importlib import import_module

__all__ = ["MainWindow", "create_application"]


def __getattr__(name: str):
    if name in __all__:
        module = import_module(".app", __name__)
        return getattr(module, name)
    raise AttributeError(name)
