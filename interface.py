import pygame
import time
from pygame_controller import Game
from pygame.locals import (
    K_0,
    K_1,
    K_2,
    K_3,
    K_4,
    K_5,
    K_6,
    K_7,
    K_8,
    K_9,
    K_UP,
    K_DOWN,
    KEYDOWN,
    QUIT,
)

class GameGUI:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Nuclear Reactor")
        self.game = Game()
        self.screen = pygame.display.set_mode([1000,1000])

        self.running = True

    def main_loop(self):
        while self.running == True:
            self.handle_input()
            self.game.update_temperature()
            if self.game.update_temperature():
                self.game.auto_scram()
                break
            status = self.game.get_status()
            print(f"Temperature: {status['temperature']}°C, Average rod depth: {status['average_rod_depth']}")
            time.sleep(1)
        pygame.quit()

    def handle_input(self):
        for event in pygame.event.get():
            if event.type == KEYDOWN and event.key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                for key in [K_0, K_1, K_2, K_3, K_4, K_5, K_6, K_7, K_8, K_9]:
                    if key == event.key:
                        current_rod = key
            elif event.type == KEYDOWN and event.key == K_UP:
                self.game.raise_rod(current_rod, 10)
            elif event.type == KEYDOWN and event.key == K_DOWN:
                self.game.lower_rod(current_rod, 10)

if __name__ == "__main__":
    gui = GameGUI()
    gui.main_loop()