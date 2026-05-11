from nuclear import Reactor

class Game:
    def __init__(self):
        self.characters = []
        self.backgrounds = []
        self.dimensions = (15,15)
        self.start = ()
        self.exit = ()
        self.set_up()

    def set_up(self):
        self.reactor = Reactor()
        start_pos = (0, 7)
        self.player = CharacterObj("character", start_pos, "C")
        self.characters.append(self.player)

