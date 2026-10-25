from CodyNick import event


class Stage:
    def __init__(self):
        self.x = 0
        self.y = 0
        event('sprite', x=0, y=0, speech='')

    def go_to(self, x, y):
        self.x, self.y = float(x), float(y)
        event('sprite', x=self.x, y=self.y)

    def say(self, text):
        event('sprite', speech=str(text))
