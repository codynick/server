from CodyNick import event


def clear():
    event('dashboard_clear')


class Card:
    def __init__(self, kind, title, value=0, **options):
        self.title = str(title)
        self.kind = str(kind)
        event('card', title=self.title, card_type=self.kind, value=value, options=options)

    def set(self, value):
        event('card', title=self.title, card_type=self.kind, value=value)
