"""Width-aware text for the card page's scrollable layouts."""
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QLabel, QSizePolicy


class CardExplanation(QLabel):
    """Advertise the actual wrapped text minimum to ancestor layouts.

    QLabel's generic size hint can underestimate long rich text in a scroll
    area. This keeps sizing within Qt's layout negotiation, without fixing
    any widget or panel height.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWordWrap(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

    def minimumSizeHint(self):
        hint = super().minimumSizeHint()
        return QSize(hint.width(), max(hint.height(), self.heightForWidth(max(1, self.width()))))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if event.size().width() != event.oldSize().width():
            self.updateGeometry()
